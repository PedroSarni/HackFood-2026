"""Cliente da WhatsApp Cloud API (Meta): mandar mensagens, baixar mídia, "digitando...".

A Meta é só o carteiro: faz POST no nosso webhook quando chega mensagem, e a gente responde
com POST na Graph API. Credenciais no secret Modal `hackathon-whatsapp` (docs/whatsapp.md).

Os limites de tamanho abaixo são da Meta. Estourar qualquer um derruba a mensagem inteira
com erro 400, então todo texto passa por `linha()` ou `bloco()` antes de sair.
"""
import os
import re
import time

import httpx

GRAPH = 'https://graph.facebook.com/v23.0'

MAX_TEXTO = 4096     # mensagem de texto comum
MAX_CORPO = 1024     # corpo de mensagem interativa (botões, lista, link)
MAX_BOTAO = 20       # título de botão de resposta
MAX_BOTOES = 3
MAX_LINHA = 24       # título de linha de lista
MAX_DESCR = 72       # descrição de linha de lista
MAX_LINHAS = 10      # linhas por lista (somando as seções)
MAX_RODAPE = 60
MAX_ID = 200         # id de botão/linha (a Meta aceita 256; folga pra prefixo)

# pausa mínima entre duas mensagens seguidas pra mesma pessoa. A Meta não garante a ordem
# de entrega; mandando em fila com um respiro, na prática chega na ordem. Mensagem com foto
# demora mais (a Meta baixa a imagem antes de entregar), por isso a pausa maior depois dela.
PAUSA = 0.35
PAUSA_FOTO = 1.1


def cfg(nome):
    """Variável de ambiente; 'PREENCHER' conta como vazio (convenção do projeto)."""
    v = os.environ.get(nome, '')
    return '' if v == 'PREENCHER' else v


def tamanho(s):
    """Tamanho como a Meta conta (UTF-16): emoji fora do plano básico vale 2 ("🔎" = 2)."""
    return len(str(s).encode('utf-16-le')) // 2


def _cortar(s, n):
    if tamanho(s) <= n:
        return s
    while s and tamanho(s) + 1 > n:
        s = s[:-1]
    return s.rstrip() + '…'


def linha(s, n):
    """Uma linha só (títulos de botão/lista): junta espaços e corta com reticências."""
    return _cortar(' '.join(str(s or '').split()), n)


def bloco(s, n):
    """Texto com quebras de linha preservadas, cortado em n caracteres."""
    return _cortar(str(s or '').strip(), n)


_LIXO = re.compile(r'[#*_~=]{2,}|[*_~]|#(?=\s|$)')


def limpar(s):
    """Nome cadastrado pela loja -> texto apresentável: tira "#######", "***" e os * _ ~ soltos
    (no WhatsApp eles viram/quebram negrito, itálico e riscado)."""
    s = _LIXO.sub(' ', str(s or ''))
    s = re.sub(r'\(\s*\)', ' ', s)  # parêntese que ficou vazio
    s = re.sub(r'\s+([,.;:)])', r'\1', ' '.join(s.split()))
    return s.strip(' -–,;:/|')


def partir(titulo, n):
    """Título que não cabe em n -> (curto, detalhe, cortou). Primeiro tenta o que está entre
    parênteses virar detalhe ("Sim, desejo sachês (maionese, ketchup)"); senão corta na palavra
    e o detalhe leva o texto inteiro, pra ninguém ficar sem saber o que escolheu."""
    titulo = ' '.join(str(titulo or '').split())
    if tamanho(titulo) <= n:
        return titulo, '', False
    m = re.match(r'^(.*?)\s*[(\[](.+?)[)\]]\s*(.*)$', titulo)
    if m and m.group(1) and tamanho(m.group(1)) <= n and not m.group(3):
        return m.group(1).rstrip(' -,:'), m.group(2).strip(), False
    curto = ''
    for palavra in titulo.split():
        prox = f'{curto} {palavra}'.strip()
        if tamanho(prox) + 1 > n:
            break
        curto = prox
    return (curto.rstrip(' -,:(') or titulo[:n - 1]) + '…', titulo, True


def titulos_unicos(titulos, n):
    """A Meta recusa a mensagem inteira se dois botões (ou linhas) tiverem o mesmo título
    (erro 131009 "Duplicate button title"). Corta no limite e numera os repetidos."""
    saida, vistos = [], set()
    for t in titulos:
        base = linha(t, n) or '…'
        cand, k = base, 2
        while cand.lower() in vistos:
            sufixo = f' {k}'
            cand = linha(base, n - tamanho(sufixo)).rstrip('…').rstrip() + sufixo
            k += 1
        vistos.add(cand.lower())
        saida.append(cand)
    return saida


class ErroWhatsApp(Exception):
    def __init__(self, status, corpo):
        super().__init__(f'graph {status}: {str(corpo)[:300]}')
        self.status = status
        self.corpo = corpo


class WhatsApp:
    """Manda mensagens pra um número. Uma instância por rodada de conversa."""

    def __init__(self, token=None, phone_id=None, http=None, pausa=PAUSA):
        self.token = token if token is not None else cfg('WHATSAPP_TOKEN')
        self.phone_id = phone_id if phone_id is not None else cfg('WHATSAPP_PHONE_ID')
        self.http = http or httpx.Client(timeout=30)
        self.pausa = pausa
        self._livre_em = 0.0  # monotonic: quando a próxima mensagem pode sair

    # --- baixo nível -------------------------------------------------------------------

    def graph(self, metodo, caminho, **kw):
        """Chamada na Graph API com 3 tentativas pra erro passageiro (429/5xx/rede)."""
        kw.setdefault('headers', {})['Authorization'] = f'Bearer {self.token}'
        for tentativa in range(3):
            try:
                r = self.http.request(metodo, f'{GRAPH}/{caminho}', **kw)
            except httpx.TransportError:
                if tentativa == 2:
                    raise
                time.sleep(0.5 * (tentativa + 1))
                continue
            if r.status_code in (429, 500, 502, 503) and tentativa < 2:
                time.sleep(0.5 * (tentativa + 1))
                continue
            if r.status_code >= 400:
                print(f'graph {metodo} {caminho} -> {r.status_code}: {r.text[:400]}')
                raise ErroWhatsApp(r.status_code, r.text)
            return r.json() if r.content else {}

    def _mandar(self, to, payload, pausa=None):
        espera = self._livre_em - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        corpo = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': to}
        corpo.update(payload)
        try:
            return self.graph('POST', f'{self.phone_id}/messages', json=corpo)
        finally:
            if self.pausa:  # pausa=0 desliga todas (testes)
                self._livre_em = time.monotonic() + (self.pausa if pausa is None else pausa)

    # --- mensagens ---------------------------------------------------------------------

    def texto(self, to, texto):
        return self._mandar(to, {'type': 'text',
                                 'text': {'body': bloco(texto, MAX_TEXTO), 'preview_url': False}})

    def botoes(self, to, texto, botoes, imagem=None, rodape=None):
        """botoes: [(id, título)], no máximo 3. imagem: URL pública (JPG/PNG) do cabeçalho."""
        if not botoes:
            return self.texto(to, texto)
        botoes = botoes[:MAX_BOTOES]
        titulos = titulos_unicos([t for _, t in botoes], MAX_BOTAO)
        inter = {'type': 'button',
                 'body': {'text': bloco(texto, MAX_CORPO)},
                 'action': {'buttons': [
                     {'type': 'reply', 'reply': {'id': str(i)[:MAX_ID], 'title': t}}
                     for (i, _), t in zip(botoes, titulos)]}}
        if imagem:
            inter['header'] = {'type': 'image', 'image': {'link': imagem}}
        if rodape:
            inter['footer'] = {'text': linha(rodape, MAX_RODAPE)}
        return self._mandar(to, {'type': 'interactive', 'interactive': inter},
                            pausa=PAUSA_FOTO if imagem else None)

    def lista(self, to, texto, rotulo, linhas, titulo_secao='Opções', rodape=None):
        """linhas: [(id, título, descrição)], no máximo 10. rotulo: texto do botão que abre."""
        linhas = linhas[:MAX_LINHAS]
        titulos = titulos_unicos([t for _, t, _ in linhas], MAX_LINHA)
        rows = [{'id': str(i)[:MAX_ID], 'title': t, **({'description': linha(d, MAX_DESCR)} if d else {})}
                for (i, _, d), t in zip(linhas, titulos)]
        inter = {'type': 'list',
                 'body': {'text': bloco(texto, MAX_CORPO)},
                 'action': {'button': linha(rotulo, MAX_BOTAO),
                            'sections': [{'title': linha(titulo_secao, MAX_LINHA), 'rows': rows}]}}
        if rodape:
            inter['footer'] = {'text': linha(rodape, MAX_RODAPE)}
        return self._mandar(to, {'type': 'interactive', 'interactive': inter})

    def link(self, to, texto, rotulo, url, imagem=None, rodape=None):
        """Botão que abre um site (login do iFood, por exemplo)."""
        inter = {'type': 'cta_url',
                 'body': {'text': bloco(texto, MAX_CORPO)},
                 'action': {'name': 'cta_url',
                            'parameters': {'display_text': linha(rotulo, MAX_BOTAO), 'url': url}}}
        if imagem:
            inter['header'] = {'type': 'image', 'image': {'link': imagem}}
        if rodape:
            inter['footer'] = {'text': linha(rodape, MAX_RODAPE)}
        return self._mandar(to, {'type': 'interactive', 'interactive': inter})

    def imagem(self, to, link, legenda=''):
        img = {'link': link}
        if legenda:
            img['caption'] = bloco(legenda, MAX_CORPO)
        return self._mandar(to, {'type': 'image', 'image': img}, pausa=PAUSA_FOTO)

    def template(self, to, nome, idioma='pt_BR', componentes=None):
        """Mensagem fora da janela de 24h: só com template aprovado pela Meta."""
        tpl = {'name': nome, 'language': {'code': idioma}}
        if componentes:
            tpl['components'] = componentes
        return self._mandar(to, {'type': 'template', 'template': tpl})

    # --- outros ------------------------------------------------------------------------

    def digitando(self, mid):
        """Marca a mensagem como lida e liga o "digitando..." (dura até 25 s ou até a próxima
        mensagem nossa). Nunca quebra a conversa: falhou, segue sem."""
        if not mid:
            return False
        try:
            self.graph('POST', f'{self.phone_id}/messages',
                       json={'messaging_product': 'whatsapp', 'status': 'read', 'message_id': mid,
                             'typing_indicator': {'type': 'text'}})
            return True
        except Exception as e:  # noqa: BLE001 - indicador é enfeite
            print(f'digitando falhou: {e!r}')
            return False

    def baixar_midia(self, media_id, max_bytes=16 * 1024 * 1024):
        """Áudio/foto recebidos: a Meta dá uma URL temporária que exige o mesmo token."""
        info = self.graph('GET', media_id)
        r = self.http.get(info['url'], headers={'Authorization': f'Bearer {self.token}'},
                          timeout=60, follow_redirects=True)
        r.raise_for_status()
        if len(r.content) > max_bytes:
            raise ValueError(f'mídia grande demais: {len(r.content)} bytes')
        mime = (info.get('mime_type') or r.headers.get('content-type') or '').split(';')[0]
        return mime, r.content

    def apontar_webhook(self, url, verify_token):
        """Troca o webhook SÓ deste número (override_callback_uri). A Meta faz um GET de
        verificação na URL nova antes de aceitar."""
        return self.graph('POST', self.phone_id, json={
            'webhook_configuration': {'override_callback_uri': url, 'verify_token': verify_token}})
