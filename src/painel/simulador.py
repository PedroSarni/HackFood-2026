"""Clientes de mentira conversando com o Bot DE VERDADE (fluxo, textos, MCP falso), só nesta máquina.

Serve pra ver o dash mexer sem WhatsApp e sem gastar o MCP real. Usa os fakes dos testes
(tests/fakes.py: WhatsApp que valida as regras da Meta, Gemini de regras fixas, McpFake) e os
mesmos espiões da produção (src/shared/painel.py), então o caminho até o dash é o mesmo.

Primeiro preenche os últimos 7 dias num relógio adiantado (o gráfico já nasce com histórico),
depois segue ao vivo, um cliente novo a cada poucos segundos.
As rotinas automáticas rodam também, com as mesmas funções que o src/app.py chama: quem cala leva a
cutucada com 1 min e perde o carrinho aos 5, quem repete a compra pode ligar o lembrete de recompra
e o cron dos lembretes passa a cada 15 min (no histórico, no relógio adiantado).
Nada disso vai pro modal.Dict do bot: o diário simulado fica num dict em memória.
"""
import copy
import random
import threading
import time

from src import agentes
from src.shared import painel
from tests.fakes import Armazem, Mundo

PRIMEIROS = ['Dona Cida', 'Seu Antônio', 'Marina', 'Pedro', 'Ana', 'Lucas', 'Beatriz', 'Rafael', 'Juliana', 'Bruno',
             'Camila', 'Seu Zé', 'Dona Lurdes', 'Gabriel', 'Luiza', 'Felipe', 'Dona Neide', 'Seu Jorge', 'Carla', 'Tiago']
SOBRENOMES = ['Costa', 'Almeida', 'Oliveira', 'Santos', 'Lima', 'Souza', 'Rocha', 'Ferreira', 'Alves', 'Martins']
NOMES = [f'{p} {SOBRENOMES[i * 7 % len(SOBRENOMES)]}' if not p.startswith(('Dona', 'Seu')) else p
         for i, p in enumerate(PRIMEIROS)] + [f'{p} {s}' for p in PRIMEIROS[2:11] for s in SOBRENOMES[:4]]
ITENS = ['quero pao', 'quero leite', 'preciso de carne', 'quero uma pizza', 'preciso de dipirona']
CPF = '529.982.247-25'
VARREDURA = 15 * 60   # s: o cron dos lembretes (src/app.py, LEMBRETES_MIN)


class MundoAnotado(Mundo):
    """Mundo dos testes com os espiões da produção (src/bot/contexto.py e src/app.py).
    `agora` fixo por padrão (testes); `ao_vivo()` passa a seguir o relógio de verdade."""

    def __init__(self, diario_dic=None, nome=None, **kw):
        self._fixo = None
        super().__init__(**kw)
        self.nome = nome
        self.calado = False   # esperando o protocolo de quem calou: não conta como conversa ativa
        self.painel = diario_dic if diario_dic is not None else Armazem()
        self.diario = painel.Diario(self.painel, agora=lambda: self.agora, intervalo=None)
        self.ctx.wpp = painel.EspiaoWhatsApp(self.wpp, self.diario)
        mcp = self.mcp
        self.ctx._chamador = lambda wid: painel.espiar_mcp(mcp.chamar, self.diario, wid)
        # o interruptor do dash vale na demo também: a config mora no próprio dict da demo (cfg:agentes)
        cfg = lambda: agentes.config(self.painel)  # noqa: E731
        pular = lambda ag: self.diario.anotar(self.wa, 'ia', agente=ag, ok=False, ms=0, erro='desligado')  # noqa: E731
        self.ctx._gerar_json = agentes.roteador(painel.espiar_ia(self.llm, self.diario, self.wa), cfg, pular)
        if self.ctx._transcritor:
            self.ctx._transcritor = agentes.so_se_ligado(
                painel.espiar_servico(self.ctx._transcritor, self.diario, self.wa, 'ouvido', 'fake'), 'ouvido', cfg)
        if self.ctx._locutor:
            self.ctx._locutor = agentes.so_se_ligado(
                painel.espiar_servico(self.ctx._locutor, self.diario, self.wa, 'voz', 'fake'), 'voz', cfg)
        Bot, mundo = self.Bot, self

        class BotAnotado(Bot):
            def processar(self, wa_id, msgs):
                if mundo.nome and msgs:
                    msgs[-1]['_nome'] = mundo.nome
                titulos = mundo.titulos()
                for msg in msgs:  # o fake manda o id como título; no WhatsApp vem o texto do botão
                    r = (msg.get('interactive') or {}).get('button_reply')
                    if r and r['id'] in titulos:
                        r['title'] = titulos[r['id']]
                painel.anotar_entrada(mundo.diario, wa_id, msgs)
                return super().processar(wa_id, msgs)
        self.Bot = BotAnotado

    @property
    def agora(self):
        return self._fixo if self._fixo is not None else time.time()

    @agora.setter
    def agora(self, valor):
        self._fixo = valor

    def ao_vivo(self):
        self._fixo = None

    def esperar(self, segundos):
        if self._fixo is None:
            time.sleep(segundos)
        else:
            self._fixo += segundos

    def eventos(self):
        return [v for k, v in self.painel.items() if k.startswith('ev:')]

    def sessoes(self, depois=0):
        return painel.montar_sessoes(self.eventos(), agora=self.agora + depois)

    def titulos(self):
        t = {}
        for tipo, d in self.wpp.saida:
            if tipo == 'botoes':
                t.update(d['botoes'])
            elif tipo == 'lista':
                t.update((i, ti) for i, ti, _ in d['linhas'])
            elif tipo == 'carrossel':
                t.update(b for c in d['cards'] for b in c['botoes'])
        return t

    def tem(self, prefixo):
        return any(i.startswith(prefixo) for i in self.wpp.todos_ids())

    def rotina(self, origem):
        """O Bot com as mensagens marcadas como rotina automática (o src/app.py faz o mesmo com contexto_producao)."""
        ctx = copy.copy(self.ctx)
        ctx.wpp = painel.EspiaoWhatsApp(self.wpp, self.diario, origem)
        return self.Bot(ctx)

    def rastrear(self, pedido, ritmo):
        from src.bot.rastreio import acompanhar
        ctx = copy.copy(self.ctx)
        ctx.wpp = painel.EspiaoWhatsApp(self.wpp, self.diario, 'rastreio')
        dormir = (lambda s: time.sleep(s * ritmo / 10)) if self._fixo is None else (lambda s: self.esperar(s))
        acompanhar(ctx, self.wa, pedido, dormir=dormir, relogio=lambda: self.agora)


def _passo(m, ritmo, *msgs):
    m.wpp.limpar()
    m.enviar(*msgs)
    m.esperar(random.uniform(2, 9) * ritmo)


def _escolher(m, ritmo):
    """Toca em "Quero esse", passa pelas opções obrigatórias e escolhe a quantidade."""
    m.tocar('pick:')
    m.esperar(random.uniform(3, 8) * ritmo)
    for _ in range(3):  # opções obrigatórias (tamanho da pizza, acompanhamento...)
        if m.tem('opt:') and not m.tem('qtd:'):
            m.tocar('opt:')
    if m.tem('qtd:'):
        m.tocar(f'qtd:{random.choice([1, 1, 2, 3])}')


def _rastrear(m, ritmo):
    """O pedido saiu: acompanha o status (numa thread ao vivo; no relógio adiantado, no histórico)."""
    if not m.rastreios:
        return
    pedido_id = m.rastreios.pop()
    if m._fixo is None:
        threading.Thread(target=m.rastrear, args=(pedido_id, ritmo), daemon=True).start()
    else:
        m.rastrear(pedido_id, ritmo)


def _ligar_lembrete(m):
    """Comprou de novo o mesmo item e o bot ofereceu o lembrete de recompra: mais da metade liga."""
    ids = [i for i in m.wpp.todos_ids() if i.startswith('rec:')]
    sim = [i for i in ids if i != 'rec:0']
    if sim and random.random() < 0.6:
        m.enviar(('botao', 'rec:7' if 'rec:7' in sim and random.random() < 0.75 else random.choice(sim)))
    elif 'rec:0' in ids:
        m.enviar(('botao', 'rec:0'))


def _decidir_lembrete(m, ritmo):
    """O lembrete chegou ("Podemos pedir?"): a pessoa pede, deixa pra outro dia ou desliga."""
    if not m.tem('lem:'):
        return None
    r = random.random()
    m.tocar('lem:pedir:' if r < 0.6 else 'lem:hoje:' if r < 0.85 else 'lem:parar:')
    if r >= 0.6:
        return 'respondeu o lembrete'
    m.esperar(random.uniform(2, 6) * ritmo)
    if m.estado().get('fase') == 'confirmar' and m.tem('ok:'):  # o preço mudou: o bot mostra o resumo antes
        m.tocar('ok:')
    _rastrear(m, ritmo)
    return 'pediu pelo lembrete'


def _responder_lembrete(m, ritmo):
    """Lembrete que venceu com a janela de 24h fechada: o "oi" da pessoa traz o lembrete, e ela responde."""
    if not m.ctx.recorrencias.vencido_sem_aviso(m.wa):
        return None
    _passo(m, ritmo, random.choice(['oi', 'bom dia', 'boa tarde']))
    return _decidir_lembrete(m, ritmo) or 'só oi'


def jornada(m, ritmo=1.0, sorte=None):
    """Uma conversa com final sorteado: compra, abandono, cancelamento, só um oi..."""
    r = sorte if sorte is not None else random.random()
    u = m.armazem.get(f'u:{m.wa}')
    if u and u.get('carrinho'):
        # carrinho de outra visita: o bot guarda pra sempre e trava a busca na loja dele
        # ("Não achei pizza no Drogaria Saúde"). Aqui ele expira em silêncio, como um cancelar.
        u.update({'carrinho': None, 'fila': [], 'escolha': None, 'atual': None, 'pendente': None, 'fase': 'inicio'})
        m.armazem[f'u:{m.wa}'] = u
    lembrete = _responder_lembrete(m, ritmo)
    if lembrete:
        return lembrete
    if r < 0.06:
        _passo(m, ritmo, random.choice(['bom dia', 'oi', 'boa tarde']))
        return 'só oi'
    pedido = ('audio', f'm{random.randint(1, 999)}') if r < 0.14 else random.choice(ITENS)
    _passo(m, ritmo, pedido)
    if m.estado().get('fase') in ('endereco', 'novo_endereco') or m.tem('cand:'):
        _passo(m, ritmo, 'Rua das Flores, 120, São Carlos')
        _passo(m, ritmo, ('botao', next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('cand:'))))
        if m.tem('compl_nao'):
            _passo(m, ritmo, ('botao', 'compl_nao'))
    if not m.wpp.cards() and not m.tem('pick:'):
        return 'não achou'
    if random.random() < 0.25 and m.tem('mais:'):
        m.tocar('mais:')
        m.esperar(random.uniform(3, 8) * ritmo)
    if not m.tem('pick:'):
        return 'sem cards'
    _escolher(m, ritmo)
    m.esperar(random.uniform(3, 10) * ritmo)
    if 0.14 <= r < 0.26:
        return 'largou o carrinho'
    if 0.26 <= r < 0.32:  # some 40 min e volta pra fechar (vira recuperada)
        m.esperar(40 * 60 if m._fixo is not None else 0)
    if not m.tem('fim'):
        return 'sem finalizar'
    m.tocar('fim')
    m.esperar(random.uniform(2, 6) * ritmo)
    for _ in range(3):  # abaixo do pedido mínimo: aceita a sugestão do bot e tenta fechar de novo
        if m.estado().get('fase') != 'mais' or not m.tem('sugerir'):
            break
        m.tocar('sugerir')
        if not m.tem('pick:'):
            break
        _escolher(m, ritmo)
        if m.tem('fim'):
            m.tocar('fim')
    if m.estado().get('fase') == 'pagamento':
        m.tocar('pag:0')
    if 0.32 <= r < 0.38:
        return 'parou no pagamento'
    if m.estado().get('fase') == 'cpf':
        _passo(m, ritmo, CPF)
    if 0.38 <= r < 0.42:
        m.tocar('cancelar')
        return 'cancelou'
    if not m.tem('ok:'):
        return 'sem resumo'
    m.tocar('ok:')
    if m.tem('rec:'):
        m.esperar(random.uniform(2, 6) * ritmo)
        _ligar_lembrete(m)
    _rastrear(m, ritmo)
    return 'comprou'


def _concluir(m, ritmo):
    """Voltou depois da cutucada: segue de onde parou até o pedido sair (ou desiste de novo)."""
    for passo in range(6):
        fase = m.estado().get('fase')
        if fase == 'confirmar' and m.tem('ok:'):
            m.tocar('ok:')
            _rastrear(m, ritmo)
            return 'voltou e comprou'
        if fase == 'cpf':
            _passo(m, ritmo, CPF)
        elif fase == 'pagamento' and m.tem('pag:'):
            m.tocar('pag:0')
        elif m.tem('fim'):
            m.tocar('fim')
        elif passo == 0:
            _passo(m, ritmo, random.choice(['voltei', 'oi, tô aqui', 'pera, cheguei']))
        else:
            break
        m.esperar(random.uniform(2, 6) * ritmo)
    return 'voltou'


def calar(m, ritmo=1.0, volta=0.35):
    """O protocolo de quem calou (src/app.py, pessoa_calada), com as mesmas funções do Bot: aos FOLLOWUP_SEG a
    cutucada, aos ABANDONO_SEG o carrinho esquecido. Parte de quem é cutucado volta e tenta fechar o pedido."""
    from src.bot.fluxo import ABANDONO_SEG, FOLLOWUP_SEG
    marca = m.estado().get('ultima_msg')
    if not marca:
        return None
    m.calado = True
    try:
        m.esperar(max(0.0, marca + FOLLOWUP_SEG - m.agora))
        if m.rotina('followup').followup(m.wa, marca) and random.random() < volta:
            m.esperar(random.uniform(15, 100) * min(ritmo, 1.0))   # antes dos 5 min: o carrinho continua lá
            return _concluir(m, ritmo)
        m.esperar(max(0.0, marca + ABANDONO_SEG - m.agora))
        return 'carrinho esquecido' if m.rotina('abandono').abandonar_carrinho(m.wa, marca) else None
    finally:
        m.calado = False


def varrer(dic, clientes, quando=None, ocupados=(), anotar=True, antes=None):
    """O cron dos lembretes (src/app.py, lembretes) na demo: avisa quem tem lembrete vencido (as mesmas funções de
    src/bot/recorrencia.py) e anota a passada no diário. Quem está no meio de uma conversa fica pra próxima.
    `anotar=False` só anota se a contagem mudou desde `antes` (o histórico não precisa de 2.880 passadas iguais)."""
    from src.bot.recorrencia import Recorrencias, agenda, disparar_vencidos
    quando = quando or time.time()
    total = {'janela': 0, 'template': 0, 'adiado': 0, 'erro': 0}
    for m in list(clientes):
        if m.wa in ocupados or not Recorrencias(m.recs_dic, agora=lambda: quando).vencido_sem_aviso(m.wa):
            continue   # nada vencido: o relógio da pessoa fica onde está
        antes = m._fixo
        if antes is not None:   # histórico: o relógio de cada cliente só anda pra frente
            if antes > quando:
                continue
            m.agora = quando
        cont = disparar_vencidos(m.armazem, painel.EspiaoWhatsApp(m.wpp, m.diario, 'lembrete'),
                                 dic_rec=m.recs_dic, agora=quando, so=m.wa)
        for k, v in cont.items():
            total[k] = total.get(k, 0) + v
        if antes is not None and not (cont.get('janela') or cont.get('template')):
            m._fixo = antes   # só adiou: nada chegou pra pessoa, e ela pode puxar conversa (e ver o lembrete)
        elif cont.get('janela') and antes is not None and random.random() < 0.6:
            m.esperar(random.uniform(60, 900))   # avisada dentro da janela: às vezes já responde
            _decidir_lembrete(m, 0.2)
    if anotar or total != antes:
        juntos = {m.wa: m.recs_dic.get(m.wa) for m in list(clientes) if m.recs_dic.get(m.wa)}
        painel.anotar_varredura(painel.Diario(dic, agora=lambda: quando, intervalo=None), total, VARREDURA,
                                agenda(juntos, quando))
    return total


def _cliente(dic, n):
    m = MundoAnotado(diario_dic=dic, nome=NOMES[n % len(NOMES)], wa=f'55169{n:08d}')
    m._fixo = None  # o Mundo dos testes nasce com relógio parado em 2027; aqui ainda não tem relógio
    return m


def guardar_clientes(clientes):
    """O que cada cliente simulado já viveu (armazém do bot, iFood falso e lembretes), pro cache da demo: sem
    isso, quem volta do cache não acha o pedido que o lembrete quer refazer."""
    return [{'wa': m.wa, 'nome': m.nome, 'armazem': dict(m.armazem), 'recs': dict(m.recs_dic)} for m in clientes]


def restaurar_clientes(dic, salvos, desvio):
    """Os clientes do cache, com o relógio trazido pra hoje (última mensagem e vencimento dos lembretes)."""
    clientes = []
    for s in salvos or []:
        m = MundoAnotado(diario_dic=dic, nome=s['nome'], wa=s['wa'])
        m._fixo = None
        m.armazem.update(s['armazem'])
        u = m.armazem.get(f'u:{m.wa}')
        if isinstance(u, dict) and u.get('ultima_msg'):
            u['ultima_msg'] = float(u['ultima_msg']) + desvio
        for wa, recs in (s.get('recs') or {}).items():
            m.recs_dic[wa] = [{**r, 'proximo': float(r.get('proximo') or 0) + desvio} for r in recs]
        clientes.append(m)
    return clientes


def preencher_historico(dic, dias=7, conversas=60, semente=17, clientes=None, progresso=None):
    """Conversas espalhadas nos últimos `dias`, no relógio adiantado (roda bem mais rápido que o real).
    O relógio de cada cliente só anda pra frente: conversa nova começa depois que a anterior acabou.
    O cron dos lembretes passa a cada 15 min no mesmo relógio, entre uma conversa e outra."""
    random.seed(semente)
    agora = time.time()
    clientes = clientes or [_cliente(dic, n) for n in range(len(NOMES))]
    inicios = sorted(agora - random.uniform(0.05, dias) * 86400 for _ in range(conversas))
    cron, antes = agora - dias * 86400, None
    for n, inicio in enumerate(inicios):
        while cron <= inicio:
            antes = varrer(dic, clientes, cron, anotar=False, antes=antes)
            cron += VARREDURA
        m = random.choice(clientes)
        if m._fixo is not None and inicio < m._fixo + painel.INATIVIDADE + 60:
            continue  # esse cliente ainda está "no meio" da conversa anterior
        m.agora = inicio
        try:
            jornada(m, ritmo=0.2)
            calar(m, ritmo=0.2)
        except Exception as e:  # noqa: BLE001 - conversa simulada que tropeça não para as outras
            print(f'simulador: conversa do histórico tropeçou: {e!r}')
        if progresso:
            progresso(n + 1, len(inicios))
    while cron <= agora:   # até agora; a última passada sempre fica no diário
        antes = varrer(dic, clientes, cron, anotar=cron + VARREDURA > agora, antes=antes)
        cron += VARREDURA
    return clientes


def rodar_ao_vivo(dic, parar, clientes=None, intervalo=(6, 15), ritmo=1.0):
    """Até `parar` (threading.Event): a cada `intervalo` segundos alguém puxa conversa. Quem já
    comprou no histórico volta (recompra); de vez em quando chega gente nova. Quem cala depois
    leva a cutucada e pode perder o carrinho, e o cron dos lembretes passa a cada 15 min."""
    random.seed()
    clientes = list(clientes or [])
    for m in clientes:
        m.ao_vivo()
    ocupados, cron = {}, time.time()   # a 1ª passada do cron já na largada: o dash não espera 15 min
    while not parar.is_set():
        ocupados = {wa: (t, m) for wa, (t, m) in ocupados.items() if t.is_alive()}
        if time.time() >= cron:
            try:
                varrer(dic, clientes, ocupados=set(ocupados))
            except Exception as e:  # noqa: BLE001
                print(f'simulador: o cron dos lembretes tropeçou: {e!r}')
            cron += VARREDURA
        livres = [m for m in clientes if m.wa not in ocupados]
        if sum(1 for _, m in ocupados.values() if not m.calado) < 4:
            if not livres or random.random() < 0.2:
                m = _cliente(dic, len(clientes))
                m.ao_vivo()
                clientes.append(m)
            else:
                m = random.choice(livres)

            def conversar(m=m):
                try:
                    jornada(m, ritmo=ritmo)
                    calar(m, ritmo=ritmo)
                except Exception as e:  # noqa: BLE001
                    print(f'simulador: conversa ao vivo tropeçou: {e!r}')
            t = threading.Thread(target=conversar, daemon=True)
            t.start()
            ocupados[m.wa] = (t, m)
        parar.wait(random.uniform(*intervalo))
