"""Modo áudio: quem PEDIU ("me responde por áudio") passa a ouvir o atendente, não a ler.

Liga só com pedido explícito (`pediu_audio`), vale pra sessão e desliga sozinho no fim dela:
pedido feito, 30 min sem falar (IDLE_MAX do fluxo), "sair", ou quando a pessoa pede texto de volta
(`pediu_texto`). Mora em `u['voz']`.

Como funciona numa rodada (src/bot/fluxo.py):
- o `Gravador` embrulha o WhatsApp. Texto solto NÃO sai: vira fala. Botões, cards, lista e link
  saem na hora (são o que a pessoa toca) e o texto deles também vira fala;
- no fim da rodada, `roteiro` pede pro Gemini reescrever tudo como um atendente falaria num áudio
  de WhatsApp: curto, sem emoji nem asterisco, valor por extenso, sem ler lista de botão feito robô,
  e terminando com o que fazer agora ("me manda um áudio ou escreve");
- a fala vira nota de voz na ElevenLabs (src/shared/voz.py) e vai por último, como quem manda as
  fotos e depois grava explicando.
Deu errado em qualquer passo: os textos guardados saem escritos, na ordem. Ninguém fica sem resposta.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------- pedido da pessoa

_AUDIO = r'(?:audios?|voz|mensage(?:m|ns) de voz|gravacao|gravando)'
# verbo dirigido ao bot (imperativo, infinitivo ou "quero que você ...") + "por/em/de áudio"
PEDE_AUDIO = re.compile(
    r'\b(?:me |pode |podia |poderia |consegue |da pra |quero que (?:voce |vc |vce |tu )?(?:me )?)?'
    r'(?:respond(?:e|a|er|ia)|fal(?:a|e|ar)(?: comigo)?|mand(?:a|e|ar)|envi(?:a|e|ar)|grav(?:a|e|ar)'
    r'|explic(?:a|e|ar)|convers(?:a|e|ar)(?: comigo)?|me atend(?:e|a|er))'
    r'(?: (?:pra|para|a) mim| comigo| me| tudo| isso| as respostas| a resposta)?'
    r' (?:por|em|de|com|no|num|via|so por|so em|so de)? ?(?:um |uma )?' + _AUDIO + r'\b'
    r'|\bprefiro (?:ouvir|escutar|(?:por |em |de )?' + _AUDIO + r')\b'
    r'|\b(?:responde|resposta|respostas|fala|manda)s? (?:so )?(?:por |em |de )?' + _AUDIO + r'\b'
    r'|\b(?:pode ser|quero|queria|prefiro) (?:a resposta |as respostas |resposta )?(?:por|em) ' + _AUDIO + r'\b'
    r'|\bme (?:manda|mande|envia|envie) (?:um |uns )?' + _AUDIO + r'\b'
    r'|\bmodo (?:de )?' + _AUDIO + r'\b')
# "posso mandar áudio?", "vou te mandar um áudio": quem manda é a PESSOA, não é pedido de resposta
PESSOA_MANDA = re.compile(r'\b(?:posso|vou|vo|consigo|da pra eu|deixa eu|eu (?:posso|vou|mando|mandei|gravo|gravei)'
                          r'|mandei|gravei|te mandei|ja mandei|aceita|aceitam|ouve|ouviu|escuta|escutou|entende)\b'
                          r'(?: te| lhe| voce| vc)?(?: (?:mandar|enviar|gravar|falar|um|uns|o|meu|por))*'
                          r'(?: (?:um|uns|o|meu))? ' + _AUDIO + r'\b')
PEDE_TEXTO = re.compile(
    r'\b(?:para|pare|parar|chega|sem mais|nao (?:precisa|quero|gosto|manda|mande|mandar|envia|responde|responda'
    r'|consigo ouvir|da pra ouvir|posso ouvir|to conseguindo ouvir))(?: (?:de|mais|me|mandar|responder|com|por|em|o|os|esse|esses))*'
    r' ' + _AUDIO + r'\b'
    r'|\b(?:volta|volte|voltar|pode|prefiro|responde|responda|me responde|me responda|quero|manda|mande)'
    r'(?: (?:a|pra|por|em|o|so|no|de))* (?:escrever|escrevendo|escrito|texto|mensagem escrita|ler)\b'
    r'|\bpor escrito\b')


def _limpo_com_mapa(s):
    """Minúsculo, sem acento, pontuação vira um espaço só. Devolve também, pra cada caractere do
    limpo, a posição dele no original: o que casou no limpo dá pra recortar do texto da pessoa."""
    limpo, mapa = [], []
    for i, c in enumerate(str(s or '')):
        c = (unicodedata.normalize('NFKD', c.lower())[:1] or c)
        if not ('a' <= c <= 'z' or c.isdigit()):
            c = ' '
        if c == ' ' and (not limpo or limpo[-1] == ' '):
            continue
        limpo.append(c)
        mapa.append(i)
    while limpo and limpo[-1] == ' ':
        limpo.pop()
        mapa.pop()
    return ''.join(limpo), mapa


def _limpo(s):
    return _limpo_com_mapa(s)[0]


def pediu_texto(texto):
    return bool(PEDE_TEXTO.search(_limpo(texto)))


def pediu_audio(texto):
    t = _limpo(texto)
    return bool(t and not PEDE_TEXTO.search(t) and not PESSOA_MANDA.search(t) and PEDE_AUDIO.search(t))


ENCHIMENTO = {'', 'e', 'pfv', 'pf', 'por favor', 'favor', 'obrigado', 'obrigada', 'ok', 'oi', 'ola', 'ta', 'tá',
              'bom dia', 'boa tarde', 'boa noite', 'agora', 'a partir de agora', 'daqui pra frente', 'tambem',
              'sim', 'pode', 'so', 'mesmo', 'oi tudo bem', 'tudo bem', 'aqui', 'pra mim', 'para mim', 'comigo',
              'podia', 'poderia', 'consegue', 'voce', 'vc', 'oi pode', 'ola pode'}


def resto_do_pedido(texto, padrao):
    """Tira o trecho que casou (pedido de áudio ou de texto) e devolve o que sobra, ou '' se o
    que sobra é só enchimento ("por favor", "oi"). "quero pão e me responde por áudio" -> "quero pão"."""
    s = str(texto or '')
    limpo, mapa = _limpo_com_mapa(s)
    m = padrao.search(limpo)
    if not m:
        return s.strip()
    inicio, fim = mapa[m.start()], mapa[m.end() - 1] + 1
    resto = ' '.join((s[:inicio] + ' ' + s[fim:]).split()).strip(' ,.;!?-')
    resto = re.sub(r'^(?:e|mas|ai|aí)\s+|\s+(?:e|mas)$', '', resto, flags=re.I).strip(' ,.;!?-')
    return '' if _limpo(resto) in ENCHIMENTO else resto


# ---------------------------------------------------------------------------- gravador

class Gravador:
    """Mesma cara do WhatsApp. Com o modo áudio ligado (`ativo()`), texto solto fica guardado e
    o resto sai na hora; tudo vira `falas` pro roteiro. Desligado, é transparente."""

    def __init__(self, wpp, ativo):
        self._wpp = wpp
        self._ativo = ativo
        self.falas = []      # {'tipo', 'texto', 'opcoes', 'fica'} na ordem em que o bot "falou"
        self.guardados = []  # (to, texto) que não saíram: plano B se o áudio falhar

    def __getattr__(self, nome):
        return getattr(self._wpp, nome)

    def _anotar(self, tipo, texto, opcoes=None, fica=False):
        self.falas.append({'tipo': tipo, 'texto': str(texto or ''), 'opcoes': list(opcoes or []), 'fica': fica})

    def texto(self, to, texto, fica=False):
        """fica=True: sai escrito mesmo no modo áudio (número do pedido, código de entrega)."""
        if not self._ativo():
            return self._wpp.texto(to, texto)
        self._anotar('texto', texto, fica=fica)
        if fica:
            return self._wpp.texto(to, texto)
        self.guardados.append((to, texto))
        return {}

    def botoes(self, to, texto, botoes, *a, **kw):
        r = self._wpp.botoes(to, texto, botoes, *a, **kw)
        if self._ativo():
            self._anotar('botoes', texto, [t for _, t in botoes])
        return r

    def lista(self, to, texto, rotulo, linhas, *a, **kw):
        r = self._wpp.lista(to, texto, rotulo, linhas, *a, **kw)
        if self._ativo():
            self._anotar('lista', texto, [t for _, t, _ in linhas])
        return r

    def carrossel(self, to, texto, cards, *a, **kw):
        r = self._wpp.carrossel(to, texto, cards, *a, **kw)
        if self._ativo():
            self._anotar('cards', texto, [' · '.join(x for x in str(c[1] or '').split('\n')[:2] if x) for c in cards])
        return r

    def link(self, to, texto, rotulo, url, *a, **kw):
        r = self._wpp.link(to, texto, rotulo, url, *a, **kw)
        if self._ativo():
            self._anotar('link', texto, [rotulo])
        return r

    def imagem(self, to, link, legenda='', *a, **kw):
        r = self._wpp.imagem(to, link, legenda, *a, **kw)
        if self._ativo() and legenda:
            self._anotar('foto', legenda)
        return r


# ---------------------------------------------------------------------------- roteiro

SISTEMA = """\
Você é o atendente de um assistente que faz pedidos no iFood pelo WhatsApp. A pessoa pediu pra ser \
respondida por ÁUDIO, então você vai gravar UMA nota de voz no lugar das mensagens escritas abaixo. \
Quem ouve são, em geral, pessoas idosas ou com pouca prática com celular.

Escreva exatamente o que vai ser FALADO (o texto vai direto pra uma voz sintética):
- Soe como um atendente de verdade mandando áudio no WhatsApp: caloroso, natural, português do \
Brasil informal ("então", "tá bom?", "rapidinho", "prontinho"), sem exagero nem gíria forçada. Não \
leia as mensagens palavra por palavra: conte com as suas palavras o que elas dizem.
- Varie o começo: não abra com a mesma palavra da fala anterior (ela vem no contexto) e não \
comece toda fala com "Olha" ou "Entendido".
- Se a pessoa ESCREVEU ou FALOU algo, responda primeiro a isso, numa frase curta. Se ela só tocou \
num botão, não comente o toque nem "confirme" o que ela escolheu além do que as mensagens dizem.
- Cards com foto: diga que mandou as opções com foto, quantas são e cite no máximo duas \
(nome curto e preço). Botões: cite o nome dos botões só quando ajuda ("é só tocar em Finalizar pedido").
- Endereço: fale só a rua e o número (o número em algarismos: "Rua das Flores, 120"); se precisa \
escolher entre parecidos, diga o que muda (o bairro).
- Resumo de pedido: fale os itens, o total e a forma de pagamento, sem ler cada linha de taxa.
- Dinheiro por extenso do jeito que se fala: "R$ 12,90" -> "doze e noventa", "R$ 5,00" -> "cinco \
reais", "R$ 112,35" -> "cento e doze e trinta e cinco". Só dinheiro vai por extenso: quantidade, \
número de casa e minutos ficam em algarismos ("3 pães", "40 a 55 minutos").
- Nunca leia URL, CPF, emoji, asterisco nem símbolo. Onde estiver "(fica escrito na mensagem)", \
diga só que está escrito na mensagem, sem tentar adivinhar o que é.
- SEMPRE termine dizendo o que a pessoa faz agora e que ela pode responder mandando um áudio ou \
escrevendo (e tocando no botão, quando houver). Varie o jeito de dizer. EXCEÇÃO: na etapa "cpf" \
o CPF só vale ESCRITO (por segurança): peça pra escrever os números, nunca pra mandar áudio.
- Curto: de 1 a 4 frases, no máximo 420 caracteres. Se tiver muita coisa, priorize a última \
pergunta e o que a pessoa precisa decidir.
- Fale sem marcar o seu gênero (nada de "obrigado/obrigada", "cansado/cansada").
- Nunca invente produto, preço, quantidade, prazo ou passo que não esteja nas mensagens. Nunca \
diga que fez algo que as mensagens não dizem.
Responda só o JSON do esquema."""

ESQUEMA = {'type': 'OBJECT', 'properties': {'fala': {'type': 'STRING'}}, 'required': ['fala']}
# fila própria: o áudio é a resposta inteira, então não dá pra esperar o lite oscilar até 7 s.
# Medido em 17/10 22h: 3.5-flash-lite 0,9 s estável; 3.1-lite de 0,9 a 7 s; 3.8-flash dando 503.
MODELOS_ROTEIRO = [('gemini-3.5-flash-lite', 3.0, ''), ('gemini-3.1-flash-lite', 3.0, '')]
MAX_FALA = 600
CONVITE = 'Pode me responder mandando um áudio ou escrevendo, tá bom?'
CONVITE_CPF = 'O CPF, por segurança, me escreve aqui com os números, tá bom?'
ROTULOS = {'texto': 'Mensagem', 'botoes': 'Mensagem com botões', 'lista': 'Mensagem com lista de opções',
           'cards': 'Cards com foto (a pessoa arrasta pro lado e toca em "Quero esse")',
           'link': 'Mensagem com botão que abre um site', 'foto': 'Foto com legenda'}
# o que vai escrito de propósito (número do pedido, código de entrega): o Gemini lia "D mil e três"
# mesmo com a regra no prompt, então o código nem chega nele
_CODIGO = re.compile(r'\*[^*\n]*\d[^*\n]*\*')


def _para_llm(falas):
    blocos = []
    for i, f in enumerate(falas, 1):
        texto = _CODIGO.sub('(fica escrito na mensagem)', f['texto']) if f.get('fica') else f['texto']
        b = f'{i}. {ROTULOS.get(f["tipo"], "Mensagem")}:\n{texto[:900]}'
        if f['opcoes']:
            b += '\nOpções: ' + ' | '.join(o[:90] for o in f['opcoes'][:10])
        blocos.append(b)
    return '\n\n'.join(blocos)


def roteiro(llm, falas, disse='', etapa='', antes=''):
    """As mensagens da rodada -> o texto de UMA nota de voz. Sem o Gemini, `roteiro_simples`.
    antes: a fala do áudio anterior, pra não repetir o mesmo começo toda vez."""
    if not falas:
        return ''
    contexto = [f'Etapa da conversa: {etapa or "inicio"}.',
                f'Fala do áudio anterior: {antes[:200]}' if antes else 'Este é o primeiro áudio da conversa.',
                f'O que a pessoa acabou de mandar: {disse[:300] if disse else "(tocou num botão)"}',
                'Mensagens que o assistente ia mandar escritas, na ordem:', _para_llm(falas)]
    try:
        dados, _modelo, _seg = llm(SISTEMA, [('texto', '\n\n'.join(contexto))], ESQUEMA, modelos=MODELOS_ROTEIRO)
        fala = ' '.join(str((dados or {}).get('fala') or '').split()) if isinstance(dados, dict) else ''
    except Exception as e:  # noqa: BLE001 - sem Gemini ainda dá pra falar o texto limpo
        print(f'roteiro do áudio falhou: {e!r}')
        fala = ''
    fala = _falavel(fala)
    return fala[:MAX_FALA] if len(fala) >= 15 else roteiro_simples(falas, etapa)


_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]')


def _falavel(s):
    """Tira o que a voz leria errado: emoji, *negrito*, _itálico_, ~riscado~, links, marcadores."""
    s = _EMOJI.sub(' ', str(s or ''))
    s = re.sub(r'https?://\S+', ' ', s)
    s = re.sub(r'[*_~#•|]', ' ', s)
    s = re.sub(r'\b(\d+)\s*[-–]\s*(\d+)(\s*min)', r'\1 a \2\3', s)  # '40-55 min': a voz lia 'menos'
    s = re.sub(r'\b(\d)️?⃣', r'\1.', s)
    return ' '.join(s.split())


def _reais_falados(s):
    """'R$ 12,90' -> '12 reais e 90' (o TTS lê número; "R$" ele soletra)."""
    def troca(m):
        inteiro, cent = m.group(1).replace('.', ''), (m.group(2) or '00')
        r = f'{int(inteiro)} rea{"l" if int(inteiro) == 1 else "is"}'
        return r + (f' e {int(cent)}' if int(cent) else '')
    return re.sub(r'R\$\s*([\d.]+)(?:,(\d{2}))?', troca, s)


def roteiro_simples(falas, etapa=''):
    """Plano B sem Gemini: o texto das mensagens, limpo pra voz, com o convite no fim."""
    convite = CONVITE_CPF if etapa == 'cpf' else CONVITE
    partes = []
    for f in falas:
        texto = _CODIGO.sub('na mensagem escrita', f['texto']) if f.get('fica') else f['texto']
        t = _reais_falados(_falavel(texto))
        if f['tipo'] == 'cards':
            t = f'Te mandei {len(f["opcoes"])} opções com foto. ' + t
        t = t.rstrip(' :,;')
        if t:
            partes.append(t if t[-1] in '.!?' else t + '.')  # "?" fica: a voz entoa como pergunta
    fala = ' '.join(partes)
    if len(fala) > MAX_FALA - len(convite) - 1:
        fala = fala[:MAX_FALA - len(convite) - 1].rsplit(' ', 1)[0].rstrip(',;:') + '...'
    return f'{fala} {convite}'.strip()
