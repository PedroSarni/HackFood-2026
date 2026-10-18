"""Fakes pros testes: WhatsApp que só anota, armazém em memória, Gemini de mentirinha."""
from src.bot.contexto import Contexto
from src.bot.recorrencia import Recorrencias
from src.shared.mcp_fake import McpFake


class Armazem(dict):
    """dict com a mesma cara do modal.Dict que o código usa (put com skip_if_exists)."""

    def put(self, chave, valor, skip_if_exists=False):
        if skip_if_exists and chave in self:
            return False
        self[chave] = valor
        return True


class Fila:
    def __init__(self):
        self.partes = {}

    def put(self, v, partition=None):
        self.partes.setdefault(partition, []).append(v)

    def get_many(self, n, block=True, partition=None):
        p = self.partes.get(partition, [])
        saida, self.partes[partition] = p[:n], p[n:]
        return saida


def erro_meta(p):
    """As regras da Meta pra mensagem enviada (as que já derrubaram a gente ou podem derrubar).
    Devolve o motivo do 400, ou None se a Meta aceitaria."""
    from src.shared.whatsapp import tamanho
    tipo = p.get('type')
    if tipo == 'text':
        corpo = p['text']['body']
        return 'texto vazio' if not corpo.strip() else ('texto > 4096' if tamanho(corpo) > 4096 else None)
    if tipo == 'image':
        return None if p['image'].get('link', '').startswith('https://') else 'imagem sem https'
    if tipo == 'template':
        return None
    if tipo != 'interactive':
        return f'tipo desconhecido {tipo}'
    it = p['interactive']
    corpo = it['body']['text']
    if not corpo.strip() or tamanho(corpo) > 1024:
        return 'body vazio ou > 1024'
    if it.get('footer') and tamanho(it['footer']['text']) > 60:
        return 'footer > 60'
    if it['type'] == 'button':
        bts = it['action']['buttons']
        if not 1 <= len(bts) <= 3:
            return 'botões fora de 1..3'
        titulos = [b['reply']['title'] for b in bts]
        ids = [b['reply']['id'] for b in bts]
        if any(not t or tamanho(t) > 20 for t in titulos):
            return f'título de botão > 20: {titulos}'
        if len({t.lower() for t in titulos}) != len(titulos):
            return f'Duplicate button title: {titulos}'
        if len(set(ids)) != len(ids) or any(len(i) > 256 for i in ids):
            return 'id de botão repetido ou > 256'
        return None
    if it['type'] == 'carousel':
        cards = it['action']['cards']
        if not 2 <= len(cards) <= 10:
            return 'carrossel fora de 2..10 cards'
        if [c['card_index'] for c in cards] != list(range(len(cards))):
            return 'card_index fora de ordem'
        if any(not (c.get('header') or {}).get('image', {}).get('link', '').startswith('https://') for c in cards):
            return 'card sem foto https'
        if any(tamanho(c['body']['text']) > 160 or c['body']['text'].count('\n') > 2 for c in cards):
            return 'texto do card > 160 ou > 2 quebras'
        if len({len(c['action']['buttons']) for c in cards}) != 1:
            return 'cards com número diferente de botões'
        bts = [b['quick_reply'] for c in cards for b in c['action']['buttons']]
        if any(not b['title'] or tamanho(b['title']) > 20 for b in bts) or len({b['id'] for b in bts}) != len(bts):
            return 'botão do card > 20 ou id repetido'
        return None
    if it['type'] == 'list':
        act = it['action']
        if not act['button'] or tamanho(act['button']) > 20:
            return 'rótulo da lista > 20'
        rows = [r for s in act['sections'] for r in s['rows']]
        if not 1 <= len(rows) <= 10:
            return 'linhas fora de 1..10'
        if any(tamanho(r['title']) > 24 or tamanho(r.get('description', '')) > 72 for r in rows):
            return 'linha de lista grande demais'
        if len({r['id'] for r in rows}) != len(rows) or len({r['title'].lower() for r in rows}) != len(rows):
            return 'linha de lista repetida'
        return None
    if it['type'] == 'cta_url':
        par = it['action']['parameters']
        if tamanho(par['display_text']) > 20 or not par['url'].startswith(('https://', 'http://')):
            return 'cta_url inválido'
        return None
    return f'interativa desconhecida {it["type"]}'


class WhatsAppFake:
    """Passa pelo código de verdade (src/shared/whatsapp.py: cortes, títulos únicos) e valida o
    JSON final com as regras da Meta. O que a Meta recusaria aqui vira o mesmo ErroWhatsApp 400."""

    def __init__(self):
        import httpx

        from src.shared.whatsapp import WhatsApp
        self.saida = []   # (tipo, dados), já no formato que chegou na "Meta"
        self.recusadas = []

        def meta(req):
            import json
            p = json.loads(req.content)
            if p.get('status') == 'read':
                return httpx.Response(200, json={'success': True})
            erro = erro_meta(p)
            if erro:
                self.recusadas.append((erro, p))
                return httpx.Response(400, json={'error': {'code': 131009, 'message': erro}})
            self.saida.append(_simplificar(p))
            return httpx.Response(200, json={'messages': [{'id': f'wamid.out{len(self.saida)}'}]})
        self._real = WhatsApp(token='t', phone_id='p', http=httpx.Client(transport=httpx.MockTransport(meta)), pausa=0)

    def texto(self, to, texto):
        return self._real.texto(to, texto)

    def botoes(self, to, texto, botoes, imagem=None, rodape=None):
        return self._real.botoes(to, texto, botoes, imagem=imagem, rodape=rodape)

    def carrossel(self, to, texto, cards):
        return self._real.carrossel(to, texto, cards)

    def lista(self, to, texto, rotulo, linhas, titulo_secao='Opções', rodape=None):
        return self._real.lista(to, texto, rotulo, linhas, titulo_secao=titulo_secao, rodape=rodape)

    def link(self, to, texto, rotulo, url, imagem=None, rodape=None):
        return self._real.link(to, texto, rotulo, url, imagem=imagem, rodape=rodape)

    def imagem(self, to, link, legenda=''):
        return self._real.imagem(to, link, legenda)

    def template(self, to, nome, idioma='pt_BR', componentes=None):
        return self._real.template(to, nome, idioma, componentes)

    def digitando(self, mid):
        return True

    def baixar_midia(self, media_id):
        return 'audio/ogg', b'OggS-falso-' + media_id.encode()

    # --- ajudas pros testes ---

    def limpar(self):
        self.saida = []

    def ultimos_botoes(self):
        for tipo, d in reversed(self.saida):
            if tipo == 'botoes':
                return d['botoes']
            if tipo == 'lista':
                return [(i, t) for i, t, _ in d['linhas']]
        return []

    def todos_ids(self):
        ids = []
        for tipo, d in self.saida:
            if tipo == 'botoes':
                ids += [i for i, _ in d['botoes']]
            elif tipo == 'lista':
                ids += [i for i, _, _ in d['linhas']]
            elif tipo == 'carrossel':
                ids += [i for c in d['cards'] for i, _ in c['botoes']]
        return ids

    def textos(self):
        return [d.get('texto', '') for _, d in self.saida]

    def cards(self):
        saida = []
        for t, d in self.saida:
            if t == 'carrossel':
                saida += d['cards']
            elif t == 'botoes' and any(i.startswith('pick:') for i, _ in d['botoes']):
                saida.append(d)
        return saida


def _simplificar(p):
    """JSON da Meta -> (tipo, dados) que os testes leem."""
    to = p.get('to')
    if p['type'] == 'text':
        return 'texto', {'to': to, 'texto': p['text']['body']}
    if p['type'] == 'image':
        return 'imagem', {'to': to, 'link': p['image']['link']}
    if p['type'] == 'template':
        return 'template', {'to': to, 'nome': p['template']['name']}
    it = p['interactive']
    if it['type'] == 'button':
        return 'botoes', {'to': to, 'texto': it['body']['text'],
                          'botoes': [(b['reply']['id'], b['reply']['title']) for b in it['action']['buttons']],
                          'imagem': (it.get('header') or {}).get('image', {}).get('link')}
    if it['type'] == 'carousel':
        return 'carrossel', {'to': to, 'texto': it['body']['text'], 'cards': [
            {'texto': c['body']['text'], 'imagem': c['header']['image']['link'],
             'botoes': [(b['quick_reply']['id'], b['quick_reply']['title']) for b in c['action']['buttons']]}
            for c in it['action']['cards']]}
    if it['type'] == 'list':
        rows = [r for s in it['action']['sections'] for r in s['rows']]
        return 'lista', {'to': to, 'texto': it['body']['text'],
                         'linhas': [(r['id'], r['title'], r.get('description', '')) for r in rows]}
    return 'link', {'to': to, 'texto': it['body']['text'], 'url': it['action']['parameters']['url']}


class LlmFake:
    """Regras fixas no lugar do Gemini: o suficiente pra exercitar o fluxo."""

    def __init__(self):
        self.chamadas = 0
        self.falhar = False
        self.resposta = None   # força uma resposta específica

    def __call__(self, sistema, partes, esquema):
        from src.shared.llm import ErroLLM
        self.chamadas += 1
        if self.falhar:
            raise ErroLLM('fake fora do ar')
        if self.resposta is not None:
            return self.resposta, 'fake', 0.01
        if 'manter' in esquema['properties']:  # filtro de relevância: mantém tudo, na ordem
            n = sum(1 for linha in partes[0][1].split('\n') if linha[:1].isdigit())
            return {'manter': list(range(n))}, 'fake', 0.01
        if 'acao' not in esquema['properties']:  # o tutor de erros (src/bot/tutor.py)
            return {'texto': '[tutor] Calma, o iFood deu uma travadinha 😅 Toque em Tentar de novo.'}, 'fake', 0.01
        from src.bot.interpretar import normalizar
        texto = normalizar(' '.join(p[1] for p in partes[1:] if p[0] == 'texto'))
        if any(p[0] == 'arquivo' for p in partes):
            texto += ' pao'  # o "áudio" fala pão
        itens = []
        for termo, loja in (('pao', 'MERCADO'), ('leite', 'MERCADO'), ('carne', 'MERCADO'),
                            ('pizza', 'RESTAURANTE'), ('dipirona', 'FARMACIA'), ('burger', 'RESTAURANTE')):
            if termo in texto:
                itens.append({'termo': termo, 'tipo_loja': loja, 'quantidade': None, 'observacao': None})
        if 'mais opcoes' in texto or 'outras' in texto:
            return {'acao': 'mais_opcoes'}, 'fake', 0.01
        if 'piada' in texto or 'presidente' in texto:
            return {'acao': 'fora_do_escopo', 'resposta': '[fala] Haha 😄 piada eu não sei, mas pedido eu faço!'}, 'fake', 0.01
        if 'ta ai' in texto:
            return {'acao': 'saudacao', 'resposta': '[fala] Tô aqui sim! 😊 O iFood tá instável, mas já volta.'}, 'fake', 0.01
        if itens:
            return {'acao': 'comprar', 'itens': itens}, 'fake', 0.01
        return {'acao': 'nao_entendi'}, 'fake', 0.01


class Mundo:
    """Tudo montado pra um teste: bot + fakes. `logar()` simula o OAuth concluído."""

    def __init__(self, logado=True, wa='5516999990000', transcritor=None):
        from src.bot.fluxo import Bot
        self.wa = wa
        self.armazem = Armazem()
        self.armazem['cfg:mock'] = True  # o Mundo é sempre o iFood falso (McpFake), como a produção com o mock ligado
        self.wpp = WhatsAppFake()
        self.llm = LlmFake()
        self.rastreios = []
        self.recs_dic = Armazem()
        self.mcp = McpFake(armazem=self.armazem, chave=f'mock:{wa}')
        self.agora = 1_800_000_000.0
        self.ctx = Contexto(wpp=self.wpp, armazem=self.armazem,
                            chamador_mcp=lambda wid: self.mcp.chamar, gerar_json=self.llm,
                            link_login=lambda wid: f'https://exemplo.test/login/{wid}',
                            iniciar_rastreio=lambda wid, pid: self.rastreios.append(pid),
                            recorrencias=Recorrencias(self.recs_dic, agora=lambda: self.agora),
                            agora=lambda: self.agora, transcritor=transcritor)
        self.Bot = Bot
        if logado:
            self.logar(avisar=False)

    def logar(self, avisar=True):
        self.armazem[f'tok:{self.wa}'] = {'access_token': 'x', 'refresh_token': 'y', 'expira_em': 9e12}
        if avisar:
            self.Bot(self.ctx).logou(self.wa)

    def enviar(self, *msgs):
        """Cada msg: str (texto), ('botao', id), ('audio', media_id), ('foto', media_id, legenda)."""
        brutas = []
        for i, m in enumerate(msgs):
            base = {'from': self.wa, 'id': f'wamid.{len(brutas)}{i}', 'timestamp': str(1_800_000_000 + i)}
            if isinstance(m, str):
                base.update({'type': 'text', 'text': {'body': m}})
            elif m[0] == 'botao':
                base.update({'type': 'interactive', 'interactive': {'type': 'button_reply',
                                                                    'button_reply': {'id': m[1], 'title': m[1]}}})
            elif m[0] == 'audio':
                base.update({'type': 'audio', 'audio': {'id': m[1], 'mime_type': 'audio/ogg; codecs=opus'}})
            elif m[0] == 'foto':
                base.update({'type': 'image', 'image': {'id': m[1], 'mime_type': 'image/jpeg',
                                                        'caption': m[2] if len(m) > 2 else ''}})
            brutas.append(base)
        self.Bot(self.ctx).processar(self.wa, brutas)
        return self.wpp.saida

    def estado(self):
        return self.armazem.get(f'u:{self.wa}') or {}

    def tocar(self, prefixo):
        """Toca no último botão cujo id começa com `prefixo`."""
        for bid in reversed(self.wpp.todos_ids()):
            if bid.startswith(prefixo):
                return self.enviar(('botao', bid))
        raise AssertionError(f'nenhum botão {prefixo!r} em {self.wpp.todos_ids()}')
