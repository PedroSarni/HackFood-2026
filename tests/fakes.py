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


class WhatsAppFake:
    def __init__(self):
        self.saida = []   # (tipo, dados)

    def texto(self, to, texto):
        self.saida.append(('texto', {'to': to, 'texto': texto}))

    def botoes(self, to, texto, botoes, imagem=None, rodape=None):
        self.saida.append(('botoes', {'to': to, 'texto': texto, 'botoes': list(botoes), 'imagem': imagem}))

    def lista(self, to, texto, rotulo, linhas, titulo_secao='Opções', rodape=None):
        self.saida.append(('lista', {'to': to, 'texto': texto, 'linhas': list(linhas)}))

    def link(self, to, texto, rotulo, url, imagem=None, rodape=None):
        self.saida.append(('link', {'to': to, 'texto': texto, 'url': url}))

    def imagem(self, to, link, legenda=''):
        self.saida.append(('imagem', {'to': to, 'link': link}))

    def template(self, to, nome, idioma='pt_BR', componentes=None):
        self.saida.append(('template', {'to': to, 'nome': nome}))

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
        return ids

    def textos(self):
        return [d.get('texto', '') for _, d in self.saida]

    def cards(self):
        return [d for t, d in self.saida if t == 'botoes' and any(i.startswith('pick:') for i, _ in d['botoes'])]


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
        from src.bot.interpretar import normalizar
        texto = normalizar(' '.join(p[1] for p in partes[1:] if p[0] == 'texto'))
        if any(p[0] == 'arquivo' for p in partes):
            texto += ' pao'  # o "áudio" fala pão
        itens = []
        for termo, loja in (('pao', 'MERCADO'), ('leite', 'MERCADO'), ('carne', 'MERCADO'),
                            ('pizza', 'RESTAURANTE'), ('dipirona', 'FARMACIA')):
            if termo in texto:
                itens.append({'termo': termo, 'tipo_loja': loja, 'quantidade': None, 'observacao': None})
        if 'mais opcoes' in texto or 'outras' in texto:
            return {'acao': 'mais_opcoes'}, 'fake', 0.01
        if 'piada' in texto or 'presidente' in texto:
            return {'acao': 'fora_do_escopo'}, 'fake', 0.01
        if itens:
            return {'acao': 'comprar', 'itens': itens}, 'fake', 0.01
        return {'acao': 'nao_entendi'}, 'fake', 0.01


class Mundo:
    """Tudo montado pra um teste: bot + fakes. `logar()` simula o OAuth concluído."""

    def __init__(self, logado=True, wa='5516999990000'):
        from src.bot.fluxo import Bot
        self.wa = wa
        self.armazem = Armazem()
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
                            agora=lambda: self.agora)
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
