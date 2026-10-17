"""O que o Bot precisa do mundo, num objeto só: WhatsApp, armazém, iFood, Gemini, relógio.

Em produção (`contexto_producao`) cada peça é a de verdade. Nos testes a mesma interface é
montada com fakes (tests/fakes.py), e o fluxo não percebe a diferença.

Modo mock (secret `hackathon-ifood` com IFOOD_MOCK=1): o iFood vira o McpFake e o login
pula o OAuth. Serve pra demo e pro time trabalhar enquanto o agente está em análise.
"""
import os
import time

from src.bot.ifood import Ifood, PrecisaLogin
from src.bot.recorrencia import Recorrencias
from src.shared import geocoder, ifood_mcp, llm, scribe


def _cfg(nome):
    v = os.environ.get(nome, '')
    return '' if v == 'PREENCHER' else v


def modo_mock(estado=None):
    """Mock ligado pelo secret (IFOOD_MOCK=1) OU pelo interruptor do armazém (scripts/modo.py),
    que vale na hora, sem deploy: plano B se o iFood barrar a gente no meio da apresentação."""
    if _cfg('IFOOD_MOCK') in ('1', 'true', 'sim'):
        return True
    try:
        return bool(estado is not None and estado.get('cfg:mock'))
    except Exception:  # noqa: BLE001 - armazém fora do ar não liga o mock sozinho
        return False


class Contexto:
    def __init__(self, wpp, armazem, chamador_mcp, gerar_json, link_login, iniciar_rastreio,
                 recorrencias, agora=time.time, revogar=None, dormir=time.sleep, geocoder=None,
                 agendar_lembrete=None, transcritor=None):
        self.wpp = wpp
        self.armazem = armazem
        self._chamador = chamador_mcp       # (wa_id) -> função chamar(tool, **args)
        self._gerar_json = gerar_json
        self._link_login = link_login
        self._iniciar_rastreio = iniciar_rastreio
        self.recorrencias = recorrencias
        self.agora = agora
        self._revogar = revogar
        self.dormir = dormir
        self._geocoder = geocoder       # (texto) -> endereço canônico | None (só resolve CEP)
        self._agendar_lembrete = agendar_lembrete  # (wa_id, quando) -> dispara o lembrete nessa hora
        self._transcritor = transcritor  # (mime, bytes) -> texto (Scribe); None = o Gemini ouve o áudio

    def ifood(self, wa_id):
        return Ifood(self._chamador(wa_id))

    def normalizar_endereco(self, texto):
        return self._geocoder(texto) if self._geocoder else None

    def logado(self, wa_id):
        return bool(self.armazem.get(f'tok:{wa_id}'))

    def llm(self, sistema, partes, esquema):
        return self._gerar_json(sistema, partes, esquema)

    def baixar_midia(self, media_id):
        return self.wpp.baixar_midia(media_id)

    def transcrever(self, mime, dados):
        """Áudio -> texto (Scribe). None = desligado ou falhou: aí o Gemini ouve o áudio, como antes."""
        if not self._transcritor:
            return None
        try:
            return self._transcritor(mime, dados)
        except Exception as e:  # noqa: BLE001 - plano B é o Gemini ouvir
            print(f'scribe falhou: {e!r}')
            return None

    def link_login(self, wa_id):
        return self._link_login(wa_id)

    def agendar_lembrete(self, wa_id, quando):
        """Modo demo: o cron de 15 min é lento pra apresentação, então dispara na hora certa."""
        try:
            if self._agendar_lembrete:
                self._agendar_lembrete(wa_id, quando)
        except Exception as e:  # noqa: BLE001 - o cron de 15 min pega de qualquer jeito
            print(f'agendar lembrete falhou: {e!r}')

    def iniciar_rastreio(self, wa_id, pedido_id):
        try:
            self._iniciar_rastreio(wa_id, pedido_id)
        except Exception as e:  # noqa: BLE001 - rastreio é bônus, o pedido já foi feito
            print(f'iniciar rastreio falhou: {e!r}')

    def sair(self, wa_id):
        tok = self.armazem.get(f'tok:{wa_id}')
        if tok and self._revogar:
            self._revogar(tok)
        self.armazem.pop(f'tok:{wa_id}', None)

    def apagar(self, wa_id):
        self.sair(wa_id)
        self.armazem.pop(f'u:{wa_id}', None)
        self.armazem.pop(f'mock:{wa_id}', None)
        self.armazem.pop(f'hist:{wa_id}', None)  # histórico de compras (LGPD: apagar é apagar tudo)
        self.recorrencias.remover_todas(wa_id)


def chamador_real(armazem, wa_id):
    """Função chamar(tool, **args) com o token da pessoa, renovando quando precisa.
    Token recusado no meio do caminho: renova uma vez e tenta de novo."""
    cid, segredo = _cfg('IFOOD_CLIENT_ID'), _cfg('IFOOD_CLIENT_SECRET')

    def tokens_validos(forcar=False):
        tok = armazem.get(f'tok:{wa_id}')
        if not tok:
            raise PrecisaLogin()
        if forcar or ifood_mcp.precisa_renovar(tok):
            if not tok.get('refresh_token'):
                armazem.pop(f'tok:{wa_id}', None)
                raise PrecisaLogin()
            try:
                novo = ifood_mcp.renovar(cid, segredo, tok['refresh_token'])
            except ifood_mcp.SemAutorizacao:
                armazem.pop(f'tok:{wa_id}', None)
                raise PrecisaLogin() from None
            novo.setdefault('refresh_token', tok['refresh_token'])  # quando não rotaciona
            armazem[f'tok:{wa_id}'] = novo
            tok = novo
        return tok

    def chamar(ferramenta, **args):
        # disjuntor COMPARTILHADO: se qualquer container viu o firewall do iFood barrar, todos param
        # (cada container tem o seu IP e o seu freio; sem isso os outros seguiam batendo na porta)
        try:
            barrado_ate = float(armazem.get('ifood_bloqueado_ate') or 0)
        except Exception:  # noqa: BLE001
            barrado_ate = 0
        if barrado_ate > ifood_mcp._freio['bloqueado_ate']:
            ifood_mcp._freio['bloqueado_ate'] = barrado_ate
        tok = tokens_validos()
        try:
            try:
                return ifood_mcp.ClienteMCP(tok['access_token']).chamar(ferramenta, **args)
            except ifood_mcp.SemAutorizacao:
                tok = tokens_validos(forcar=True)
                return ifood_mcp.ClienteMCP(tok['access_token']).chamar(ferramenta, **args)
        except ifood_mcp.ErroMCP:
            local = ifood_mcp._freio['bloqueado_ate']
            if local > barrado_ate:
                armazem['ifood_bloqueado_ate'] = local
            raise

    return chamar


def contexto_producao(estado, wpp, wa_id=None, origem=None):
    """`origem` marca as mensagens no diário do painel ('rastreio' = aviso de status do pedido)."""
    import modal

    from src import app as modulo_app
    from src.shared import painel
    from src.shared.mcp_fake import McpFake

    diario = painel.diario_producao()
    wpp = painel.EspiaoWhatsApp(wpp, diario, origem)
    rec = Recorrencias(modal.Dict.from_name('hackfood-recorrencias', create_if_missing=True))
    def chamador(wid):  # decide a cada uso: o interruptor do modo demo vale sem deploy
        if modo_mock(estado):
            return painel.espiar_mcp(McpFake(armazem=estado, chave=f'mock:{wid}').chamar, diario, wid)
        return painel.espiar_mcp(chamador_real(estado, wid), diario, wid)

    def rastrear(wid, pedido_id):
        # pelo nome no app publicado: no container o app roda como `app` e este `src.app` é uma 2ª cópia
        # que o Modal não hidratou ("Function has not been hydrated", rastreio nunca começava)
        modal.Function.from_name(modulo_app.APP, 'acompanhar_pedido').spawn(wid, pedido_id)

    def lembrar(wid, quando):
        modal.Function.from_name(modulo_app.APP, 'lembrete_na_hora').spawn(wid, quando)

    def revogar(tok):
        if not modo_mock(estado):
            ifood_mcp.revogar(_cfg('IFOOD_CLIENT_ID'), _cfg('IFOOD_CLIENT_SECRET'),
                              tok.get('refresh_token') or tok.get('access_token', ''))

    ctx = Contexto(wpp=wpp, armazem=estado, chamador_mcp=chamador,
                    gerar_json=lambda s, p, e: llm.gerar_json(s, p, e),
                    link_login=modulo_app.novo_link_login, iniciar_rastreio=rastrear,
                    recorrencias=rec, revogar=revogar, geocoder=geocoder.normalizar,
                    agendar_lembrete=lembrar, transcritor=scribe.transcrever if scribe.ligado() else None)
    ctx.diario = diario
    return ctx
