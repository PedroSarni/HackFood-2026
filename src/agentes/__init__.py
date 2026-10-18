"""O time de agentes do bot: uma ficha por agente, um arquivo por agente, e o roteador que faz valer a ficha.

Quer melhorar um agente só? Abra `src/agentes/<id>.py`:
- `modelos`: a fila de modelos SÓ dele (None = fila padrão do src/shared/llm.py). Ex.: trocar só o modelo da
  foto é mudar `src/agentes/foto.py`, sem encostar no entendimento.
- `sistemas`: de onde vem o system prompt (fica no módulo do agente, em src/bot/, junto da lógica dele).
- `plano_b`: o que o bot faz quando ele falha ou está desligado (o fluxo já trata; a ficha só documenta).
Sem deploy, dá pra trocar a fila por variável de ambiente `AGENTE_<ID>_MODELOS="modelo:prazo:pensamento,..."`
(mesmo formato do BOT_GEMINI_MODELOS) ou, pelo dash, ligar/desligar e escolher o modelo principal
(armazém `cfg:agentes`, vale na próxima mensagem).

Quem orquestra é o código (src/bot/fluxo.py, o "Maestro"): os agentes não se chamam entre si.
`roteador()` embrulha o gerar_json da produção: descobre o agente pelo system prompt, barra quem está
desligado (ErroLLM `Desligado`, então cai no plano B de sempre) e entrega a fila de modelos do agente.
"""
import hashlib
import os
from dataclasses import dataclass, field

from src.shared.llm import ErroLLM

CHAVE_CFG = 'cfg:agentes'        # armazém (hackfood-estado): {id: {'ligado': bool, 'modelo': str}}
CHAVE_AR = 'cfg:agentes_ar'      # armazém: a ficha que está no ar (keys mascaradas, filas, versão dos prompts)
PUBLICAR_A_CADA = 300            # s: o bot republica a ficha do ar no máximo a cada 5 min


class Desligado(ErroLLM):
    """O agente está desligado no painel: o fluxo trata como falha da IA e segue pelo plano B."""


@dataclass(frozen=True)
class Agente:
    id: str
    nome: str                 # o nome de gente que aparece no dash
    cargo: str
    emoji: str
    cor: str
    bordao: str               # uma frase com a personalidade dele
    faz: str                  # o que ele faz, em uma frase
    plano_b: str              # o que acontece quando ele falha ou está desligado
    arquivos: tuple           # onde mexer pra melhorar
    tipo: str = 'ia'          # 'ia' (prompt + modelo) | 'servico' (voz/ouvido, ElevenLabs)
    keys: tuple = ('GEMINI_API_KEY', 'OPENROUTER_API_KEY')
    modelos: list | None = None   # [(modelo, prazo_s, pensamento)]; None = fila padrão do llm
    sistemas: object = None       # () -> [system prompts] (import tardio: evita import circular)
    essencial: bool = False       # desligar muda muito a conversa: o dash pede confirmação
    servico_modelo: object = None  # () -> nome do modelo, pros serviços
    extra: dict = field(default_factory=dict)
    foto: str | None = None       # arquivo em Frontend/Rascunho_Dash/images/agentes/ (sem foto = emoji)

    def prompts(self):
        try:
            return [p for p in (self.sistemas() if self.sistemas else []) if p]
        except Exception:  # noqa: BLE001 - ficha nunca derruba ninguém
            return []


def _carregar():
    from src.agentes import entendimento, foto, grupo, ouvido, relevancia, tutor, voz
    return [m.FICHA for m in (entendimento, foto, relevancia, grupo, tutor, voz, ouvido)]


TODOS = _carregar()
POR_ID = {a.id: a for a in TODOS}
SECRETS = {'GEMINI_API_KEY': 'hackathon-gemini', 'OPENROUTER_API_KEY': 'hackathon-openrouter',
           'ELEVENLABS_API_KEY': 'hackathon-elevenlabs'}
_por_sistema = None


def do_sistema(sistema):
    """Qual agente mandou este system prompt ('outro' se ninguém)."""
    global _por_sistema
    if _por_sistema is None:
        _por_sistema = {p: a.id for a in TODOS for p in a.prompts()}
    return _por_sistema.get(sistema, 'outro')


# --- configuração viva (dash) ---------------------------------------------------------------

def config(armazem):
    try:
        cfg = armazem.get(CHAVE_CFG) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:  # noqa: BLE001 - armazém fora: todo mundo ligado, fila da ficha
        return {}


def ligado(cfg, agente_id):
    return (cfg.get(agente_id) or {}).get('ligado', True) is not False


def definir(armazem, agente_id, ligado=None, modelo=None, limpar_modelo=False):
    """Liga/desliga ou troca o modelo principal de um agente. Devolve a config nova."""
    if agente_id not in POR_ID:
        raise KeyError(agente_id)
    cfg = dict(config(armazem))
    item = dict(cfg.get(agente_id) or {})
    if ligado is not None:
        item['ligado'] = bool(ligado)
    if limpar_modelo:
        item.pop('modelo', None)
    elif modelo:
        item['modelo'] = str(modelo)[:80]
    cfg[agente_id] = item
    armazem[CHAVE_CFG] = cfg
    return cfg


def _fila_texto(bruto):
    saida = []
    for parte in bruto.split(','):
        nome, _, resto = parte.strip().partition(':')
        prazo, _, pensamento = resto.partition(':')
        if nome:
            saida.append((nome, float(prazo or 8), pensamento))
    return saida


def fila(agente, cfg=None, pedida=None, env=os.environ):
    """A fila de modelos que vale pra este agente agora: env `AGENTE_<ID>_MODELOS` > ficha > a que o código
    pediu (`pedida`, ex.: o roteiro da voz tem pressa) > padrão do llm. O modelo principal escolhido no
    dash vai pra frente e o resto fica de reserva."""
    from src.shared import llm
    a = POR_ID.get(agente)
    bruto = env.get(f'AGENTE_{agente.upper()}_MODELOS', '') if a else ''
    base = (_fila_texto(bruto) if bruto and bruto != 'PREENCHER' else None) or (a and a.modelos) or pedida \
        or llm._modelos()
    base = [tuple(m) for m in base]
    principal = ((cfg or {}).get(agente) or {}).get('modelo')
    if principal and principal != base[0][0]:
        prazo = next((m[1] for m in base if m[0] == principal), base[0][1])
        base = [(principal, prazo, '')] + [m for m in base if m[0] != principal]
    return base


def roteador(gerar, cfg, ao_pular=None):
    """gerar(sistema, partes, esquema, **kw) com a ficha valendo: desligado não chama a IA; ligado usa a fila dele.
    `cfg`: a config (produção lê uma vez por mensagem) ou uma função que a lê a cada chamada (demo do dash)."""
    def gerar_roteado(sistema, partes, esquema, **kw):
        cfg_agora = cfg() if callable(cfg) else cfg
        agente = do_sistema(sistema)
        if agente in POR_ID and not ligado(cfg_agora, agente):
            if ao_pular:
                try:
                    ao_pular(agente)
                except Exception:  # noqa: BLE001
                    pass
            raise Desligado(f'{agente} desligado no painel')
        if agente in POR_ID and POR_ID[agente].tipo == 'ia':
            kw['modelos'] = fila(agente, cfg_agora, kw.get('modelos'))
        return gerar(sistema, partes, esquema, **kw)
    return gerar_roteado


# --- o que o dash mostra ----------------------------------------------------------------------

def chave_mascarada(nome, env=os.environ):
    v = env.get(nome, '')
    ok = bool(v) and v != 'PREENCHER'
    return {'nome': nome, 'secret': SECRETS.get(nome), 'configurada': ok, 'final': ('····' + v[-4:]) if ok else None}


def versao_prompt(textos):
    return hashlib.sha256('\n\n'.join(textos).encode()).hexdigest()[:8] if textos else None


def _modelos_de(a, cfg=None, env=os.environ):
    if a.tipo == 'servico':
        try:
            return [{'modelo': a.servico_modelo(), 'prazo': None, 'pensamento': ''}]
        except Exception:  # noqa: BLE001
            return []
    pedida = a.extra.get('fila_do_codigo')() if a.extra.get('fila_do_codigo') else None
    return [{'modelo': m, 'prazo': p, 'pensamento': t} for m, p, t in fila(a.id, cfg, pedida, env)]


def foto_do_ar(env=os.environ):
    """O que está valendo dentro do container: as keys (só os 4 finais), as filas e a versão de cada prompt.
    O servidor local do dash não tem as keys do Modal: lê esta foto do armazém."""
    return {'quando': None, 'agentes': {a.id: {'keys': [chave_mascarada(k, env) for k in a.keys],
                                               'modelos': _modelos_de(a, None, env),
                                               'prompt': versao_prompt(a.prompts())} for a in TODOS}}


def publicar_ar(armazem, agora):
    """Republica a foto do ar se a última tem mais de 5 min (uma leitura por mensagem, uma escrita a cada 5 min)."""
    try:
        atual = armazem.get(CHAVE_AR) or {}
        if agora - float(atual.get('quando') or 0) < PUBLICAR_A_CADA:
            return
        foto = foto_do_ar()
        foto['quando'] = agora
        armazem[CHAVE_AR] = foto
    except Exception as e:  # noqa: BLE001 - ficha é bônus
        print(f'agentes: publicar a ficha do ar falhou: {e!r}')


def conhecidos():
    """Modelos que dá pra escolher como principal no dash (os que já rodam no bot)."""
    from src.shared import llm
    nomes = [m[0] for m in llm.MODELOS] + [f'openrouter:{m}' for m in llm.OPENROUTER_MODELOS]
    return list(dict.fromkeys(nomes))


def fichas(cfg=None, ar=None):
    """Tudo de cada agente pro dash. `ar` = foto do ar (keys/filas do container); sem ela, usa o ambiente local."""
    cfg = cfg or {}
    ar_ag = (ar or {}).get('agentes') or {}
    saida = []
    for a in TODOS:
        prompts = a.prompts()
        do_ar = ar_ag.get(a.id) or {}
        local = _modelos_de(a, cfg)
        saida.append({
            'id': a.id, 'nome': a.nome, 'cargo': a.cargo, 'emoji': a.emoji, 'foto': a.foto, 'cor': a.cor, 'bordao': a.bordao,
            'faz': a.faz, 'planoB': a.plano_b, 'arquivos': list(a.arquivos), 'tipo': a.tipo, 'essencial': a.essencial,
            'ligado': ligado(cfg, a.id), 'modeloEscolhido': (cfg.get(a.id) or {}).get('modelo'),
            'modelos': local, 'modelosNoAr': do_ar.get('modelos'),
            'keys': do_ar.get('keys') or [chave_mascarada(k) for k in a.keys], 'keysDoAr': bool(do_ar.get('keys')),
            'prompts': prompts, 'versaoPrompt': versao_prompt(prompts), 'versaoNoAr': do_ar.get('prompt'),
        })
    return {'agentes': saida, 'conhecidos': conhecidos(), 'arQuando': (ar or {}).get('quando')}


def so_se_ligado(fn, agente_id, cfg):
    """Serviço (voz/ouvido) com interruptor lido a cada uso: desligado levanta, e o Contexto cai no plano B."""
    def fn_ligado(*a, **kw):
        if not ligado(cfg() if callable(cfg) else cfg, agente_id):
            raise Desligado(f'{agente_id} desligado no painel')
        return fn(*a, **kw)
    return fn_ligado
