"""Cliente do MCP de consumidor do iFood (JSON-RPC 2.0 sobre HTTP) e OAuth do usuário.

Conferido na mão em 2026-10-17:
- gateway https://consumer-mcp.ifood.com.br/marketplace: sem token devolve 401 com
  `resource_metadata` apontando pro servidor de autorização (padrão de auth do MCP);
- autorização https://id.ifood.com.br (OIDC): authorize, token, revoke, PKCE S256,
  client_secret_basic ou client_secret_post;
- os hosts api-mcp.ifood.com e dev-api-mcp.ifood.com citados no llms.txt nem respondem.

O gateway devolve HTTP 200 até em erro; o erro vem no corpo, e cada domínio usa um formato
(`error` no Cart, `errors[]` no Discovery, campos na raiz no Order Tracking). `_erro_em()`
reconhece os três.
"""
import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse

import httpx

GATEWAY = 'https://consumer-mcp.ifood.com.br/marketplace'
EMISSOR = 'https://id.ifood.com.br'
# login web direto (o recomendado pra nós): o OneLink do app exige redirect via Universal/App Link
AUTORIZAR = f'{EMISSOR}/authorize'
TOKEN = f'{EMISSOR}/token'
REVOGAR = f'{EMISSOR}/revoke'
PROTOCOLO = '2025-06-18'
# amplos (roteamento) + granulares (autorização), como nos exemplos de Implementação da doc.
# Deu invalid_scope? Troque pelo secret IFOOD_ESCOPOS (ex.: só os granulares).
ESCOPOS = ('mcp.user mcp.discovery mcp.cart '
           'mcp.user.basic.read mcp.user.advanced.read mcp.user.addresses.read mcp.user.behavior.read '
           'mcp.user.addresses.write mcp.discovery.search.read mcp.discovery.browse.read '
           'mcp.discovery.recommendation.read mcp.discovery.details.read mcp.cart.read mcp.cart.write '
           'mcp.cart.checkout mcp.cart.payment mcp.orders.read')
PRAZO = 25.0
RENOVAR_ANTES = 300  # renova o access token 5 min antes de expirar (recomendação da doc)


class ErroMCP(Exception):
    """Erro de negócio ou de transporte vindo do MCP."""

    def __init__(self, codigo, mensagem='', *, tentar_de_novo=False, para_usuario='', bruto=None):
        super().__init__(f'{codigo}: {mensagem}'[:400])
        self.codigo = codigo
        self.mensagem = mensagem
        self.tentar_de_novo = tentar_de_novo
        self.para_usuario = para_usuario
        self.bruto = bruto


class SemAutorizacao(ErroMCP):
    """Token inválido, expirado ou revogado: renovar ou pedir login de novo."""


# --- leitura de resposta --------------------------------------------------------------

def _ler_sse(texto):
    """Resposta em text/event-stream: junta os `data:` de cada evento e devolve o último
    JSON-RPC que tem `result` ou `error`."""
    resp, dados = None, []
    for ln in texto.splitlines() + ['']:
        if ln.startswith('data:'):
            dados.append(ln[5:].lstrip())
        elif not ln.strip() and dados:
            try:
                j = json.loads('\n'.join(dados))
            except ValueError:
                j = None
            dados = []
            if isinstance(j, dict) and ('result' in j or 'error' in j):
                resp = j
    return resp


def _erro_em(dados):
    """Se o corpo de uma ferramenta for erro (qualquer um dos 3 formatos), devolve ErroMCP."""
    if not isinstance(dados, dict):
        return None
    e = dados.get('error')
    if isinstance(e, dict):  # Cart: {"error": {code, message, details, impact, userFriendlyMessage}}
        return ErroMCP(e.get('code') or 'ERRO', e.get('message') or '',
                       tentar_de_novo=bool(e.get('retryable')),
                       para_usuario=e.get('userFriendlyMessage') or '', bruto=dados)
    if isinstance(e, str) and e:
        return ErroMCP(e, dados.get('message') or dados.get('error_description') or '', bruto=dados)
    erros = dados.get('errors')
    if isinstance(erros, list) and erros:
        erros = erros[0] if isinstance(erros[0], dict) else {'message': str(erros[0])}
    if isinstance(erros, dict) and erros:  # User e Discovery: {"errors": {mcpCode, code, message, retryable}}
        return ErroMCP(erros.get('code') or erros.get('mcpCode') or 'ERRO', erros.get('message') or '',
                       tentar_de_novo=bool(erros.get('retryable')),
                       para_usuario=erros.get('userFriendlyMessage') or '', bruto=dados)
    if dados.get('errorType'):  # Order Tracking: campos na raiz
        return ErroMCP(dados.get('code') or dados['errorType'], dados.get('message') or '',
                       tentar_de_novo=bool(dados.get('retryable')),
                       bruto=dados)  # 'suggestion' é instrução pro agente, em inglês: nunca vai pra tela
    return None


def _resultado(res):
    """result de tools/call -> dict do domínio (structuredContent ou o JSON do content)."""
    dados = res.get('structuredContent')
    if dados is None:
        textos = [c.get('text', '') for c in res.get('content') or [] if c.get('type') == 'text']
        txt = ''.join(textos)
        try:
            dados = json.loads(txt) if txt else {}
        except ValueError:
            dados = {'texto': txt}
    erro = _erro_em(dados)
    if erro:
        raise erro
    if res.get('isError'):
        raise ErroMCP('ERRO_FERRAMENTA', json.dumps(dados, ensure_ascii=False)[:300], bruto=dados)
    return dados


# --- cliente JSON-RPC -----------------------------------------------------------------

# --- freio: nunca mais derrubar o iFood ------------------------------------------------
# 17/10 ~18h30: ~50 chamadas em poucos minutos (scripts de teste) e o firewall (Akamai) do iFood
# barrou o IP de saída do Modal por ~20 min: 403 "Access Denied" até sem token, bot inteiro fora.
# 1) ritmo: no máximo ~3 chamadas/s por processo (rajada vira fila, não martelada);
# 2) disjuntor: viu o 403 do Akamai, para de chamar por PAUSA_BLOQUEIO e falha na hora (insistir
#    enquanto está barrado é o que estica o bloqueio). 403 nunca entra em retry.
INTERVALO_MIN = 0.35
PAUSA_BLOQUEIO = 300
_FREIO_LOCK = threading.Lock()
_freio = {'proxima': 0.0, 'bloqueado_ate': 0.0}


def _esperar_vez():
    if time.time() < _freio['bloqueado_ate']:
        falta = int(_freio['bloqueado_ate'] - time.time())
        raise ErroMCP('HTTP_403', f'iFood barrou a gente (firewall); pausa de mais {falta}s sem chamar',
                      tentar_de_novo=False)
    with _FREIO_LOCK:
        agora = time.time()
        espera = _freio['proxima'] - agora
        _freio['proxima'] = max(agora, _freio['proxima']) + INTERVALO_MIN
    if espera > 0:
        time.sleep(espera)


def _ver_bloqueio(r):
    if r.status_code == 403 and 'Access Denied' in r.text:
        _freio['bloqueado_ate'] = time.time() + PAUSA_BLOQUEIO
        print(f'iFood (Akamai) barrou: sem chamadas por {PAUSA_BLOQUEIO}s')


_SESSOES = {}  # hash do token -> (Mcp-Session-Id, quando): evita initialize a cada chamada
_SESSOES_LOCK = threading.Lock()
SESSAO_VALIDADE = 600


class ClienteMCP:
    def __init__(self, token, url=GATEWAY, http=None):
        self.token = token
        self.url = url
        self.http = http or httpx.Client(timeout=PRAZO)
        self._chave = hashlib.sha256(token.encode()).hexdigest()[:16]
        self._id = 0
        self.versao = PROTOCOLO

    def _cabecalhos(self, sessao):
        h = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json',
             'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': self.versao}
        if sessao:
            h['Mcp-Session-Id'] = sessao
        return h

    def _post(self, corpo, sessao):
        _esperar_vez()
        try:
            r = self.http.post(self.url, json=corpo, headers=self._cabecalhos(sessao))
        except httpx.TimeoutException as e:
            raise ErroMCP('TIMEOUT', str(e), tentar_de_novo=True) from e
        except httpx.TransportError as e:
            raise ErroMCP('REDE', str(e), tentar_de_novo=True) from e
        _ver_bloqueio(r)
        if r.status_code == 401:
            raise SemAutorizacao('AUTHENTICATION_REQUIRED', r.headers.get('www-authenticate', '')[:300])
        return r

    def _sessao(self, nova=False):
        with _SESSOES_LOCK:
            s = _SESSOES.get(self._chave)
            if s and not nova and time.time() - s[1] < SESSAO_VALIDADE:
                self.versao = s[2]
                return s[0]
        self.versao = PROTOCOLO
        r = self._post({'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
                        'params': {'protocolVersion': PROTOCOLO, 'capabilities': {},
                                   'clientInfo': {'name': 'hackfood-bot', 'version': '1.0'}}}, None)
        if r.status_code >= 400:
            raise ErroMCP(f'HTTP_{r.status_code}', r.text[:300], tentar_de_novo=r.status_code >= 500)
        sessao = r.headers.get('mcp-session-id') or ''
        try:
            j = _ler_sse(r.text) if 'text/event-stream' in r.headers.get('content-type', '') else r.json()
            self.versao = ((j or {}).get('result') or {}).get('protocolVersion') or PROTOCOLO
        except ValueError:
            pass
        self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, sessao)
        with _SESSOES_LOCK:
            _SESSOES[self._chave] = (sessao, time.time(), self.versao)
        return sessao

    def rpc(self, metodo, params=None):
        """Uma chamada JSON-RPC. Sessão expirada (404/400 de sessão) refaz o initialize uma vez."""
        for tentativa in range(2):
            sessao = self._sessao(nova=tentativa > 0)
            self._id += 1
            r = self._post({'jsonrpc': '2.0', 'id': self._id, 'method': metodo,
                            'params': params or {}}, sessao)
            if r.status_code in (400, 404) and tentativa == 0 and sessao:
                continue
            if r.status_code >= 400:
                raise ErroMCP(f'HTTP_{r.status_code}', r.text[:300], tentar_de_novo=r.status_code >= 500)
            tipo = r.headers.get('content-type', '')
            j = _ler_sse(r.text) if 'text/event-stream' in tipo else r.json()
            if not j:
                raise ErroMCP('RESPOSTA_VAZIA', r.text[:200], tentar_de_novo=True)
            if 'error' in j:
                e = j['error'] or {}
                msg = e.get('message') or ''
                if tentativa == 0 and sessao and 'session' in msg.lower():
                    continue
                raise ErroMCP(f'RPC_{e.get("code")}', msg, bruto=j)
            return j.get('result') or {}
        raise ErroMCP('SESSAO', 'sessão MCP recusada duas vezes', tentar_de_novo=True)

    def chamar(self, ferramenta, **argumentos):
        """tools/call -> dict do domínio. Erro de negócio vira ErroMCP; passageiro tenta 2x."""
        args = {k: v for k, v in argumentos.items() if v is not None}
        for tentativa in range(2):
            try:
                return _resultado(self.rpc('tools/call', {'name': ferramenta, 'arguments': args}))
            except SemAutorizacao:
                raise
            except ErroMCP as e:
                if not e.tentar_de_novo or tentativa == 1:
                    raise
                time.sleep(1.5)

    def ferramentas(self):
        return self.rpc('tools/list').get('tools', [])


# --- OAuth do usuário (Authorization Code + PKCE, cliente confidencial) ----------------

def pkce():
    """(code_verifier, code_challenge S256)"""
    verificador = secrets.token_urlsafe(64)[:96]
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b'=').decode()
    return verificador, desafio


def url_login(client_id, redirect_uri, state, desafio, escopos=None, extras=None):
    q = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect_uri,
         'scope': escopos or ESCOPOS, 'state': state, 'code_challenge': desafio,
         'code_challenge_method': 'S256'}
    q.update(extras or {})
    return f'{AUTORIZAR}?{urllib.parse.urlencode(q, quote_via=urllib.parse.quote)}'


def _pedir_token(http, client_id, client_secret, dados):
    # client_secret_post, como na doc (corpo form-encoded; JSON é recusado)
    dados = {**dados, 'client_id': client_id, 'client_secret': client_secret}
    r = http.post(TOKEN, data=dados, headers={'Accept': 'application/json'}, timeout=PRAZO)
    try:
        j = r.json()
    except ValueError:
        j = {'error': f'HTTP {r.status_code}', 'error_description': r.text[:200]}
    if r.status_code >= 400 or 'access_token' not in j:
        raise SemAutorizacao(j.get('error') or f'HTTP_{r.status_code}', j.get('error_description') or '', bruto=j)
    j['expira_em'] = time.time() + float(j.get('expires_in') or 3600)
    return j


def trocar_codigo(client_id, client_secret, codigo, verificador, redirect_uri, http=None):
    return _pedir_token(http or httpx.Client(), client_id, client_secret, {
        'grant_type': 'authorization_code', 'code': codigo, 'redirect_uri': redirect_uri,
        'code_verifier': verificador})


def renovar(client_id, client_secret, refresh_token, http=None):
    return _pedir_token(http or httpx.Client(), client_id, client_secret, {
        'grant_type': 'refresh_token', 'refresh_token': refresh_token})


def revogar(client_id, client_secret, token, http=None):
    """Revogar o refresh token derruba também os access tokens derivados dele."""
    try:
        (http or httpx.Client()).post(REVOGAR, data={'token': token, 'client_id': client_id,
                                                     'client_secret': client_secret}, timeout=PRAZO)
    except httpx.HTTPError as e:
        print(f'revogar falhou: {e!r}')


def precisa_renovar(tokens, agora=None):
    return (agora or time.time()) > float(tokens.get('expira_em') or 0) - RENOVAR_ANTES
