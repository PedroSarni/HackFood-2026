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
from src.shared import geocoder, ifood_mcp, llm


def _cfg(nome):
    v = os.environ.get(nome, '')
    return '' if v == 'PREENCHER' else v


def modo_mock():
    return _cfg('IFOOD_MOCK') in ('1', 'true', 'sim')


class Contexto:
    def __init__(self, wpp, armazem, chamador_mcp, gerar_json, link_login, iniciar_rastreio,
                 recorrencias, agora=time.time, revogar=None, dormir=time.sleep, geocoder=None):
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

    def link_login(self, wa_id):
        return self._link_login(wa_id)

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
        tok = tokens_validos()
        try:
            return ifood_mcp.ClienteMCP(tok['access_token']).chamar(ferramenta, **args)
        except ifood_mcp.SemAutorizacao:
            tok = tokens_validos(forcar=True)
            return ifood_mcp.ClienteMCP(tok['access_token']).chamar(ferramenta, **args)

    return chamar


def contexto_producao(estado, wpp, wa_id=None):
    import modal

    from src import app as modulo_app
    from src.shared.mcp_fake import McpFake

    rec = Recorrencias(modal.Dict.from_name('hackfood-recorrencias', create_if_missing=True))
    if modo_mock():
        def chamador(wid):
            return McpFake(armazem=estado, chave=f'mock:{wid}').chamar
    else:
        def chamador(wid):
            return chamador_real(estado, wid)

    def rastrear(wid, pedido_id):
        modulo_app.acompanhar_pedido.spawn(wid, pedido_id)

    def revogar(tok):
        if not modo_mock():
            ifood_mcp.revogar(_cfg('IFOOD_CLIENT_ID'), _cfg('IFOOD_CLIENT_SECRET'),
                              tok.get('refresh_token') or tok.get('access_token', ''))

    return Contexto(wpp=wpp, armazem=estado, chamador_mcp=chamador,
                    gerar_json=lambda s, p, e: llm.gerar_json(s, p, e),
                    link_login=modulo_app.novo_link_login, iniciar_rastreio=rastrear,
                    recorrencias=rec, revogar=revogar, geocoder=geocoder.normalizar)
