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

NUMEROS = {n: f'{n}️⃣' for n in range(1, 10)} | {10: '🔟'}  # legenda da foto: "1️⃣"


class Gravador:
    """Mesma cara do WhatsApp. Com o modo áudio ligado (`ativo()`), NADA sai na hora: texto,
    botões, cards e lista viram `falas` pro roteiro e ficam guardados como plano B. Quem pediu
    áudio recebe SÓ áudio (17/10 22h: texto + áudio juntos foi reclamação). Exceções: as fotos das
    opções de produto (numeradas, ver `carrossel`) e o link de entrar no iFood, que não tem como
    ser feito por voz. Desligado, é transparente."""

    def __init__(self, wpp, ativo):
        self._wpp = wpp
        self._ativo = ativo
        self.falas = []      # {'tipo', 'texto', 'opcoes'} na ordem em que o bot "falou"
        self.guardados = []  # (nome do método, args, kw) que não saíram: plano B se o áudio falhar

    def __getattr__(self, nome):
        return getattr(self._wpp, nome)

    def _segurar(self, metodo, tipo, texto, opcoes, *a, **kw):
        if not self._ativo():
            return getattr(self._wpp, metodo)(*a, **kw)
        self.falas.append({'tipo': tipo, 'texto': str(texto or ''), 'opcoes': [str(o) for o in opcoes or []]})
        self.guardados.append((metodo, a, kw))
        return {}

    def soltar(self, trocar=None):
        """Plano B: manda, na ordem, tudo que foi segurado (o áudio não saiu).
        trocar: {texto antigo: texto novo} pra mensagens de texto puro."""
        for metodo, a, kw in self.guardados:
            if metodo == 'texto' and trocar and a[1] in trocar:
                a = (a[0], trocar[a[1]])
            try:
                getattr(self._wpp, metodo)(*a, **kw)
            except Exception as e:  # noqa: BLE001 - uma mensagem recusada não segura as outras
                print(f'plano B do áudio: {metodo} falhou: {e!r}')
        self.guardados = []

    def texto(self, to, texto):
        return self._segurar('texto', 'texto', texto, None, to, texto)

    def botoes(self, to, texto, botoes, *a, **kw):
        return self._segurar('botoes', 'botoes', texto, [t for _, t in botoes], to, texto, botoes, *a, **kw)

    def lista(self, to, texto, rotulo, linhas, *a, **kw):
        return self._segurar('lista', 'lista', texto, [f'{t} ({d})' if d else t for _, t, d in linhas],
                             to, texto, rotulo, linhas, *a, **kw)

    def carrossel(self, to, texto, cards, *a, **kw):
        """Opções de produto: a ÚNICA coisa além do áudio (17/10 23h, pedido do Fabio): a foto de cada
        uma, numerada e sem nome/preço, sai na hora; o áudio, que vem depois, diz o que é cada número."""
        opcoes = [' · '.join(x for x in str(c[1] or '').split('\n')[:2] if x) for c in cards]
        if not self._ativo():
            return self._wpp.carrossel(to, texto, cards, *a, **kw)
        fotos = 0
        for n, (imagem, _, _) in enumerate(cards, 1):
            try:
                self._wpp.imagem(to, imagem, NUMEROS.get(n, str(n)))
                fotos += 1
            except Exception as e:  # noqa: BLE001 - sem uma foto, o áudio ainda diz as opções
                print(f'foto da opção {n} falhou: {e!r}')
        r = self._segurar('carrossel', 'opcoes', texto, opcoes, to, texto, cards, *a, **kw)
        self.falas[-1]['fotos'] = fotos == len(cards)
        return r

    def imagem(self, to, link, legenda='', *a, **kw):
        return self._segurar('imagem', 'texto', legenda, None, to, link, legenda, *a, **kw)

    def link(self, to, texto, rotulo, url, *a, **kw):
        r = self._wpp.link(to, texto, rotulo, url, *a, **kw)  # login não dá pra fazer por voz: sai sempre
        if self._ativo():
            self.falas.append({'tipo': 'link', 'texto': str(texto or ''), 'opcoes': []})
        return r


# ---------------------------------------------------------------------------- roteiro

SISTEMA = """\
Você é o atendente de um assistente que faz pedidos no iFood pelo WhatsApp. A pessoa pediu pra ser \
respondida SÓ por ÁUDIO: ela não vai ver texto, botão nem lista, só vai OUVIR a sua nota de voz. \
Você grava UMA nota de voz que substitui todas as mensagens abaixo. A única coisa que ela VÊ são as \
fotos das opções de produto, quando houver: uma foto por opção, numerada (1, 2, 3), sem nome e sem \
preço. Quem ouve são, em geral, pessoas idosas ou com pouca prática com celular.

REGRA DE OURO: as MENSAGENS DO ASSISTENTE são a única verdade sobre o que aconteceu e qual é o \
próximo passo. Você só reconta elas em voz. O que a pessoa disse serve só pra você soar natural; \
NUNCA use isso pra adivinhar o próximo passo. Se as mensagens dizem que não entendeu, diga que não \
entendeu e repita a pergunta delas, mesmo que você ache que entendeu. Nunca pergunte nem afirme \
nada (CPF, pagamento, endereço, confirmação) que não esteja nas mensagens desta vez.

Escreva exatamente o que vai ser FALADO (o texto vai direto pra uma voz sintética):
- Soe como um atendente de verdade mandando áudio no WhatsApp: caloroso, natural, português do \
Brasil informal ("então", "tá bom?", "rapidinho", "prontinho"), sem exagero nem gíria forçada. Não \
leia as mensagens palavra por palavra: conte com as suas palavras o que elas dizem.
- PROIBIDO falar de botão, tocar, clicar, tela, card, lista, arrastar, "aqui embaixo" ou \
"escrito na mensagem": a pessoa não vê nada disso. Peça direto o que ela tem que DIZER ou fazer.
- Fotos: só quando as mensagens dizem que ela JÁ RECEBEU as fotos das opções. Aí diga que mandou \
as fotos e use o número delas ("a foto 1 é o pão francês, por sete e noventa"). Fora isso, nunca \
fale de foto.
- Quando houver escolha, diga as opções em voz e pergunte qual ela quer: "é no Centro ou no Jardim \
São Paulo?", "quer 1, 2 ou 3?", "quer fechar o pedido, pedir mais alguma coisa ou tirar um item?". \
Produtos: numere e diga nome curto e preço de cada um ("o primeiro é o pão francês, por sete e \
noventa; o segundo..."), e pergunte qual ela quer, dizendo que pode falar o número ou o nome. Se \
houver opção de ver mais, diga que ela pode pedir outras opções.
- Menu inicial: diga só que você faz as compras do iFood e pergunte o que ela quer pedir hoje.
- Resumo do pedido: os itens, o total e a forma de pagamento, e pergunte se pode fazer o pedido.
- Pedido feito: diga o número do pedido e o código de entrega soletrando dígito por dígito \
("o código de entrega é quatro, oito, dois, um") e que é pra falar esse código pro entregador.
- Link de entrar no iFood: é a única coisa que chega na tela; diga pra ela abrir o link que você \
mandou, entrar na conta e voltar aqui.
- Varie o começo: não abra com a mesma palavra da fala anterior (ela vem no contexto) e não \
comece toda fala com "Olha" ou "Entendido".
- Se a pessoa ESCREVEU ou FALOU algo, pode reagir a isso numa frase curta, sem prometer nada. Não \
interprete o que ela disse (número, quantidade, escolha) e não "confirme" nada além do que as \
mensagens dizem: "quero o segundo" não é "duas unidades".
- Endereço: fale só a rua e o número (o número em algarismos: "Rua das Flores, 120").
- Dinheiro por extenso do jeito que se fala: "R$ 12,90" -> "doze e noventa", "R$ 5,00" -> "cinco \
reais". Só dinheiro vai por extenso: quantidade, número de casa e minutos ficam em algarismos.
- Nunca leia URL, emoji, asterisco nem símbolo.
- Termine com a pergunta ou o pedido do que ela faz agora e lembre, variando o jeito, que ela pode \
responder por áudio ou escrevendo. EXCEÇÃO: na etapa "cpf" o CPF só vale ESCRITO (por segurança): \
peça pra escrever os números, nunca pra falar.
- Curto: até 4 frases, no máximo 450 caracteres (até 650 se estiver dizendo opções de produto). \
Termine sempre a frase: nada de texto cortado.
- Fale sem marcar o seu gênero (nada de "obrigado/obrigada", "cansado/cansada").
- Nunca invente produto, preço, quantidade, prazo ou passo que não esteja nas mensagens. Nunca \
diga que fez algo que as mensagens não dizem.
Responda só o JSON do esquema."""

ESQUEMA = {'type': 'OBJECT', 'properties': {'fala': {'type': 'STRING'}}, 'required': ['fala']}
# fila própria: o áudio é a resposta inteira, então não dá pra esperar o lite oscilar até 7 s.
# Medido em 17/10 22h: 3.5-flash-lite 0,9 s estável; 3.1-lite de 0,9 a 7 s; 3.8-flash dando 503.
MODELOS_ROTEIRO = [('gemini-3.5-flash-lite', 3.0, ''), ('gemini-3.1-flash-lite', 3.0, '')]
MAX_FALA = 800
CONVITE = 'Pode me responder mandando um áudio ou escrevendo, tá bom?'
CONVITE_CPF = 'O CPF, por segurança, me escreve aqui com os números, tá bom?'
ROTULOS = {'texto': 'Mensagem', 'botoes': 'Pergunta com respostas prontas',
           'lista': 'Pergunta com lista de respostas', 'opcoes': 'Opções de produto, na ordem',
           'link': 'Link de entrar no iFood (a única coisa que aparece na tela)'}


def _para_llm(falas):
    blocos = []
    for i, f in enumerate(falas, 1):
        b = f'{i}. {ROTULOS.get(f["tipo"], "Mensagem")}:\n{f["texto"][:900]}'
        if f['opcoes']:
            ops = [re.sub(r'~[^~\n]+~', '', o)[:90] for o in f['opcoes'][:10]]  # sem o preço antigo riscado
            if f['tipo'] == 'opcoes':  # produto: numerado, a pessoa escolhe dizendo "o segundo"
                if f.get('fotos'):
                    b += '\n(Ela JÁ RECEBEU uma foto de cada opção, numerada assim, sem nome nem preço.)'
                b += '\nOpções: ' + ' | '.join(f'{n}) {o}' for n, o in enumerate(ops, 1))
            else:  # resposta pronta: só o texto ("1, 2 ou 3" já são números; "Não tem" não precisa)
                b += '\nRespostas possíveis: ' + ' | '.join(ops)
        blocos.append(b)
    return '\n\n'.join(blocos)


def roteiro(llm, falas, disse='', etapa='', antes=''):
    """As mensagens da rodada -> o texto de UMA nota de voz. Sem o Gemini, `roteiro_simples`.
    antes: a fala do áudio anterior, pra não repetir o mesmo começo toda vez."""
    if not falas:
        return ''
    contexto = ['MENSAGENS DO ASSISTENTE (a única verdade; ela NÃO vai ver, você conta em voz), na ordem:',
                _para_llm(falas),
                '--- só pra soar natural, não decide nada ---',
                f'O que a pessoa acabou de mandar: {disse[:300] if disse else "(escolheu uma das opções)"}',
                f'Fala do áudio anterior: {antes[:200]}' if antes else 'Este é o primeiro áudio da conversa.',
                f'Etapa da conversa: {etapa or "inicio"}.']
    try:
        dados, _modelo, _seg = llm(SISTEMA, [('texto', '\n\n'.join(contexto))], ESQUEMA, modelos=MODELOS_ROTEIRO)
        fala = ' '.join(str((dados or {}).get('fala') or '').split()) if isinstance(dados, dict) else ''
    except Exception as e:  # noqa: BLE001 - sem Gemini ainda dá pra falar o texto limpo
        print(f'roteiro do áudio falhou: {e!r}')
        fala = ''
    fotos = any(f.get('fotos') for f in falas)
    fala = _sem_tela(_reais_falados(_falavel(fala)), etapa, fotos)  # "R$" escapou: a voz soletraria
    return _caber(fala) if len(fala) >= 15 else roteiro_simples(falas, etapa)


_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]')
# a pessoa só ouve: frase que manda tocar/olhar alguma coisa na tela não serve (o Gemini às vezes escapa)
_TELA = re.compile(r'\b(?:bot(?:ao|ão|oes|ões)|toqu\w*|toca\w*|clic\w*|tela|cards?|arrast\w*'
                   r'|aqui embaixo|abaixo|escrito na mensagem|na mensagem escrita)\b', re.I)
_FOTO = re.compile(r'\b(?:fotos?|fotinhos?|imagens?)\b', re.I)  # só vale na rodada em que as fotos foram
_FRASES = re.compile(r'[^.!?]+[.!?]*')


def _sem_tela(fala, etapa='', fotos=False):
    """Tira as frases que falam de botão/tela (e de foto, se nenhuma foi mandada); se sumiu o
    convite pra responder, põe de volta."""
    frases = [f.strip() for f in _FRASES.findall(fala) if f.strip()]
    boas = [f for f in frases if not _TELA.search(f) and (fotos or not _FOTO.search(f))]
    if len(boas) == len(frases):
        return fala
    fala = ' '.join(boas)
    if fala and not re.search(r'[áa]udio|escrev', fala, re.I):
        fala += ' ' + (CONVITE_CPF if etapa == 'cpf' else CONVITE)
    return fala


def _caber(fala, limite=MAX_FALA):
    """Corta no fim de uma frase, nunca no meio de uma palavra (áudio terminando cortado)."""
    if len(fala) <= limite:
        return fala
    corte = fala[:limite]
    fim = max(corte.rfind('. '), corte.rfind('? '), corte.rfind('! '))
    return corte[:fim + 1] if fim > limite // 2 else corte.rsplit(' ', 1)[0] + '.'


def _falavel(s):
    """Tira o que a voz leria errado: emoji, *negrito*, _itálico_, ~riscado~, links, marcadores."""
    s = re.sub(r'\b(\d)️?⃣', r'\1.', str(s or ''))  # "1️⃣" -> "1."
    s = _EMOJI.sub(' ', s)
    s = re.sub(r'https?://\S+', ' ', s)
    s = re.sub(r'~[^~\n]+~', ' ', s)  # preço antigo riscado: falado, parecia um segundo preço
    s = re.sub(r'[*_~#•|]', ' ', s)
    s = re.sub(r'([^.!?:;,\s])[ \t]*\n\s*', r'\1. ', s.strip())  # quebra de linha = pausa: vira ponto
    s = re.sub(r'\s*\n\s*', ' ', s)
    s = re.sub(r'\s*·\s*', ', ', s)
    s = re.sub(r'\b(\d+)\s*[-–]\s*(\d+)(\s*min)', r'\1 a \2\3', s)  # "40-55 min": a voz lia "menos"
    return ' '.join(s.split())


def _reais_falados(s):
    """'R$ 12,90' -> '12 reais e 90' (o TTS lê número; "R$" ele soletra)."""
    def troca(m):
        inteiro, cent = m.group(1).replace('.', ''), (m.group(2) or '00')
        r = f'{int(inteiro)} rea{"l" if int(inteiro) == 1 else "is"}'
        return r + (f' e {int(cent)}' if int(cent) else '')
    return re.sub(r'R\$\s*([\d.]+)(?:,(\d{2}))?', troca, s)


ORDINAIS = ['primeiro', 'segundo', 'terceiro', 'quarto', 'quinto', 'sexto', 'sétimo', 'oitavo', 'nono', 'décimo']


def roteiro_simples(falas, etapa=''):
    """Plano B sem Gemini: o texto das mensagens, limpo pra voz e sem falar de tela, as opções
    ditas em voz e o convite no fim."""
    convite = CONVITE_CPF if etapa == 'cpf' else CONVITE
    partes = []
    for f in falas:
        t = _sem_tela(_reais_falados(_falavel(f['texto'])), etapa)
        if f['tipo'] == 'opcoes':
            itens = [f'o {ORDINAIS[i]}, {_reais_falados(_falavel(o))}' for i, o in enumerate(f['opcoes'][:len(ORDINAIS)])]
            t = (('Te mandei as fotos. ' if f.get('fotos') else '') + f'Achei {len(itens)} opções: '
                 + '; '.join(itens) + '. Qual você quer? Pode falar o número ou o nome.')
        elif f['opcoes'] and f['tipo'] in ('botoes', 'lista') and len(f['opcoes']) > 1:
            ops = [_falavel(o) for o in f['opcoes']]
            t += ' Você quer ' + ', '.join(ops[:-1]) + ' ou ' + ops[-1] + '?'
        t = t.replace(convite, '').rstrip(' :,;')
        if t:
            partes.append(t if t[-1] in '.!?' else t + '.')  # "?" fica: a voz entoa como pergunta
    fala = _caber(' '.join(partes), MAX_FALA - len(convite) - 1)
    return f'{fala} {convite}'.strip()
