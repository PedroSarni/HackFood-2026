"""Entender o que a pessoa quis dizer: primeiro regras baratas, depois o Gemini.

"A IA entende, o código garante" (docs/referencias.md): o modelo só devolve uma intenção
estruturada (`ESQUEMA`); quem decide o que fazer com ela, e quem chama o MCP, é o fluxo.
Confirmar compra NUNCA sai daqui sozinho: o fluxo só aceita "sim" quando a pergunta na tela
é a do resumo do pedido.

As regras rápidas cobrem o que mais aparece com quem tem pouca prática: digitar o número da
opção em vez de tocar, responder "s"/"pode", repetir o texto do botão, "oi", "menu".
"""
import re
import unicodedata

ACOES = ['comprar', 'mais_opcoes', 'escolher', 'sim', 'nao', 'quantidade', 'endereco',
         'ver_pedido', 'finalizar', 'tirar_item', 'cancelar', 'acompanhar', 'repetir',
         'ajuda', 'saudacao', 'agradecer', 'sair', 'apagar_dados', 'parar_lembrete',
         'agendar', 'sugerir', 'grupo', 'trocar_loja', 'fora_do_escopo', 'nao_entendi']
LOJAS = ['MERCADO', 'RESTAURANTE', 'FARMACIA', 'BEBIDAS', 'PET', 'LOJA']

ESQUEMA = {
    'type': 'OBJECT',
    'properties': {
        'acao': {'type': 'STRING', 'enum': ACOES},
        'itens': {'type': 'ARRAY', 'items': {
            'type': 'OBJECT',
            'properties': {
                'termo': {'type': 'STRING', 'description': 'o produto, curto, sem quantidade'},
                'busca': {'type': 'STRING', 'description': 'o que digitar na busca do iFood pra achar ESSE produto'},
                'quantidade': {'type': 'INTEGER', 'nullable': True},
                'tipo_loja': {'type': 'STRING', 'enum': LOJAS},
                'observacao': {'type': 'STRING', 'nullable': True},
            },
            'required': ['termo', 'busca', 'tipo_loja']}},
        'numero': {'type': 'INTEGER', 'nullable': True, 'description': 'quando grupo: quantas pessoas no total'},
        'texto': {'type': 'STRING', 'nullable': True},
        'transcricao': {'type': 'STRING', 'nullable': True},
        'resposta': {'type': 'STRING', 'nullable': True},
        'hora': {'type': 'STRING', 'nullable': True, 'description': 'quando agendar: horário dito, HH:MM 24h'},
        'fechar': {'type': 'BOOLEAN', 'nullable': True,
                   'description': 'true se a pessoa pediu pra fechar o pedido junto ("quero esse e pode fechar")'},
        'pagamento': {'type': 'STRING', 'nullable': True, 'enum': ['PIX', 'VALE_REFEICAO', 'VALE_ALIMENTACAO'],
                      'description': 'como a pessoa disse que vai pagar, se disse'},
        'sobre': {'type': 'STRING', 'nullable': True,
                  'enum': ['status', 'codigo_entrega', 'previsao', 'itens', 'total', 'minimo', 'pagamento', 'endereco'],
                  'description': 'quando acompanhar: do que a pessoa perguntou sobre o pedido'},
    },
    'required': ['acao'],
}

SISTEMA = """\
Você interpreta mensagens de WhatsApp para um assistente que faz pedidos no iFood \
(mercado, restaurante, farmácia, bebidas, pet). Quem escreve, na maioria, são pessoas idosas \
ou com pouca prática com celular: escrevem com erros, sem acento, abreviado, em várias \
mensagens picadas, ou mandam áudio e foto. Seja generoso: descubra o que a pessoa quer AGORA. Ela \
adianta ou atrasa passos (diz o pagamento antes da hora, responde uma pergunta velha, pergunta do pedido no \
meio de outra coisa): a ação é o que ela quer agora, não a etapa que está na tela.

Responda só o JSON do esquema. Campos:
- acao: uma de comprar, sugerir, mais_opcoes, escolher, sim, nao, quantidade, endereco, ver_pedido, \
finalizar, tirar_item, cancelar, acompanhar, repetir, ajuda, saudacao, agradecer, sair, \
apagar_dados, parar_lembrete, agendar, grupo, trocar_loja, fora_do_escopo, nao_entendi.
- itens: quando acao=comprar (ou agendar, se a pessoa disse o que quer no automático), cada produto \
pedido, na ordem. termo curto e no singular ("pão", "leite", "carne moída", "dipirona"), sem a \
quantidade. Nunca escolha pela pessoa o tipo que ela não disse: "leite" fica "leite" (não "leite integral"), \
"pão" fica "pão"; se ela disse "leite desnatado", aí sim. Sabor, tamanho \
e volume fazem parte do produto e vão no termo ("pizza de calabresa", "coca-cola 2 litros"), não na \
observacao. quantidade só se a pessoa disse (meia dúzia=6, uma dúzia=12, "uns 3"=3). observacao para \
detalhes ("bem passado", "sem cebola", "marca Italac"). Quando acao=sugerir, até 3 produtos \
que acompanhem o que já está no pedido (refrigerante pro lanche, manteiga pro pão), no mesmo formato.
- busca: o texto que vai na busca do iFood, que é burra (casa com nome de loja e com sabor). \
1 a 4 palavras, como o produto aparece num catálogo. Se a palavra pura engana, desambigue: \
"cebola" -> "cebola in natura" (senão vem salgadinho sabor cebola), "limão" -> "limão tahiti", \
"frango" -> "frango congelado" no mercado ou "frango assado" no restaurante, "coca" -> \
"coca-cola". Se não engana, repita o termo ("coxinha", "dipirona", "arroz", "leite").
- tipo_loja: MERCADO para alimento, bebida não alcoólica, limpeza e higiene (pão, leite, carne, \
arroz, fruta, café, sabão); RESTAURANTE para comida pronta (pizza, lanche, marmita, açaí, \
sushi, pastel, "almoço"); FARMACIA para remédio e farmácia; BEBIDAS para bebida alcoólica \
(cerveja, vinho); PET para ração e coisas de bicho; LOJA para o resto.
- numero: quando agendar, de quantos em quantos dias (todo dia=1, toda semana=7, a cada 15 dias=15, todo mês=30; sem frequência dita = null).
- hora: quando agendar e a pessoa disse horário, "HH:MM" 24h ("às 18h" = "18:00", "meio-dia" = \
"12:00", "8 da noite" = "20:00"); senão null. Quando escolher (1, 2 ou 3, entre as opções que estão na tela; "o primeiro"=1, \
"o do meio"=2, "o último" = o último da tela) ou quando quantidade.
- fechar: true se a pessoa pediu pra fechar o pedido junto ("quero esse e pode fechar", "já pode \
finalizar", "é só isso"); senão null.
- pagamento: PIX, VALE_REFEICAO ou VALE_ALIMENTACAO se a pessoa disse como vai pagar ("no pix", "vale \
refeição"); senão null.
- sobre: quando acompanhar, do que a pessoa perguntou (status, codigo_entrega, previsao, itens, total, \
pagamento, endereco); senão null.
- texto: quando endereco, o endereço como a pessoa disse. Quando grupo, SÓ as restrições e ajustes \
("um é vegetariano", "até 30 reais cada", "sem refri", "troca a coca por guaraná"), nunca a comida nem o \
número de pessoas; sem restrição = null.
- transcricao: se veio áudio ou foto, o que foi dito ou o que está escrito/mostrado, curto.
- resposta: SEMPRE preencha. É o que um atendente simpático diria de volta, com 1 ou 2 emojis, \
português informal e caloroso, até 3 frases curtas (no máximo 350 caracteres). Pode conversar à \
vontade: responder ao que a pessoa contou, comentar, brincar de leve, ter empatia ("que calor \
hoje" -> "Nem me fale! 🥵"). Mas SEMPRE termine puxando de volta pra compra com uma sugestão ou \
pergunta concreta ligada ao que ela disse ("que tal uma água geladinha? É só me dizer 😉"). \
Se não entendeu, diga o que entendeu e como ela pode pedir (escrevendo; não sugira mandar áudio). Não dê aula, receita, conselho \
médico, opinião política nem responda perguntas gerais: no máximo uma frase leve e volte pro \
pedido. Se houver AVISO INTERNO no contexto, leve ele em conta (ex.: explique com calma que o \
iFood está instável). Nunca diga que fez algo que não fez. O assistente SABE deixar pedidos no automático (recorrência: no dia combinado ele chama a pessoa e pede com o "sim" dela): nunca diga que não consegue agendar ou repetir pedidos. \
Você só ENTENDE a mensagem: quem coloca, tira, troca ou fecha o pedido é o assistente, depois de você. Então \
nunca diga que já colocou, adicionou, tirou ou pediu ("adicionei mais 10 leites"); no máximo que vai ver isso.

Regras:
- Lista de compras (escrita, falada ou foto de papel) vira acao=comprar com todos os itens.
- Pedir mais de um produto, novo ou que já está no pedido ("coloca mais 10 leites", "adiciona 2 pães", "põe \
mais uma coca") = comprar, com a quantidade no item. acao=quantidade é só a resposta a "quantas unidades?".
- "quero mais", "tem outro", "mostra mais", "outras" com opções na tela = mais_opcoes.
- "tem outro mercado?", "troca de loja", "quero de outra pizzaria", "esse mercado não" = trocar_loja (é a \
LOJA que ela quer trocar, não o produto).
- "quero esse", "essa tá boa", "pode ser essa", "esse mesmo", "vou querer o X-Salada", com opções na tela \
= escolher, e numero = a opção que ela indicou (se falou o nome, o número dele na lista; se só tem uma \
na tela, 1). Se ela disse quantidade, vai em itens.
- "sim", "pode", "isso", "confirma", "fechou", "ok" = sim. "não", "nao quero", "errado" = nao.
- "acabou", "só isso", "pode fechar", "terminei" = finalizar.
- "cadê meu pedido", "já saiu?", "vai demorar?" = acompanhar. Qualquer pergunta sobre o pedido feito \
também é acompanhar, com sobre: "qual o código de entrega" = codigo_entrega, "quanto deu" = total, "qual o \
pedido mínimo?", "quanto é o mínimo da loja?" = minimo (pergunta o valor: não é total nem sugerir), "o que \
eu pedi" = itens, "como paguei" = pagamento, "pra onde vai" = endereco, "que horas chega", "tá chegando?", "vai demorar?" = previsao, "o entregador \
chegou?", "onde está meu pedido?" = status.
- "o de sempre", "pedir igual da outra vez", "repetir" = repetir.
- "me sugere algo", "o que você recomenda", "qualquer coisa", "você escolhe", "algo pra completar \
o valor" ou "o pedido mínimo" = sugerir (quando a pessoa não disse o produto).
- Comer em grupo e dividir a conta = grupo: "lanchar em 5 pessoas hambúrguer", "pizza pra 4 \
dividindo", "vamos rachar uma pizza eu e mais 3", "churrasco pra 10 pessoas", "monta um kit pra galera", \
"quanto fica pra cada". numero = quantas pessoas NO TOTAL, contando quem escreve ("eu e mais 3" = 4, \
"com 4 amigos" = 5, "em 5 pessoas" = 5, "pra 13 amigos" = 13 (o "pra" já é o grupo todo), "casal" = 2; \
não disse = null). itens = primeiro o que querem \
comer (o principal) e depois o que pediram junto ("hambúrguer com coca" -> hambúrguer, coca-cola): a \
comida dita vai SEMPRE em itens, nunca só no texto. Sem comida dita (itens vazio) = dividir o pedido que \
já está montado. "2 pizzas" sem falar de pessoas é comprar.
- Com um kit pra grupo na tela (etapa kit), pedido de mudança no kit ("sem refri", "troca por guaraná", \
"mais barato", "mais batata", "agora somos 6", "põe uma sobremesa") = grupo, com texto = a mudança, numero \
só se o número de pessoas mudou e itens só com produto novo. "pode ser", "fechou", "quero esse" = sim.
- "quero isso todo dia às 18h", "toda semana", "todo mês", "deixa no automático", "me lembra de pedir", "pedido recorrente", "assinatura" = agendar (mesmo no meio de um pedido). Se a pessoa disse o que quer \
("todo dia às 7h dois pães"), os produtos vão em itens.
- "precisa ser maior de idade?", "menor pode comprar cerveja?" = fora_do_escopo, com resposta: bebida alcoólica só \
para maiores de 18 anos, e o entregador pode pedir um documento na entrega.
- Conversa que não é sobre pedido (piada, política, receita, perguntas gerais) = fora_do_escopo.
- Só "oi", "bom dia", "olá" = saudacao. "obrigado", "valeu" = agradecer.
- Se não der pra entender = nao_entendi. Nunca invente produto que a pessoa não pediu (fora o sugerir)."""


def normalizar(s):
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', s).split())


SIM = {'sim', 's', 'ss', 'si', 'pode', 'pode sim', 'isso', 'isso mesmo', 'ok', 'okay', 'confirmo',
       'confirma', 'confirmar', 'certo', 'claro', 'quero', 'fechou', 'beleza', 'blz', 'bora',
       'manda', 'pode mandar', 'pode fazer', 'sim pode', 'sim por favor', 'yes', 'uhum', 'aham'}
NAO = {'nao', 'n', 'nn', 'nao quero', 'nao obrigado', 'nao obrigada', 'negativo', 'errado',
       'cancela', 'nada', 'agora nao', 'deixa', 'deixa pra la'}
OI = {'oi', 'ola', 'oie', 'oii', 'opa', 'eai', 'e ai', 'bom dia', 'boa tarde', 'boa noite',
      'oi bom dia', 'oi boa tarde', 'oi boa noite', 'ola bom dia', 'ola boa tarde', 'hello', 'alo'}
VALEU = {'obrigado', 'obrigada', 'obg', 'valeu', 'vlw', 'brigado', 'brigada', 'muito obrigado',
         'muito obrigada', 'agradeco', 'deus abencoe', 'top', 'show', 'otimo', 'perfeito'}
NUMEROS = {'um': 1, 'uma': 1, 'primeiro': 1, 'primeira': 1, 'dois': 2, 'duas': 2, 'segundo': 2,
           'segunda': 2, 'tres': 3, 'terceiro': 3, 'terceira': 3, 'quatro': 4, 'cinco': 5,
           'seis': 6, 'meia duzia': 6, 'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'doze': 12,
           'uma duzia': 12, 'duzia': 12}
COMANDOS = {
    'menu': 'inicio', 'inicio': 'inicio', 'comecar': 'inicio', 'voltar': 'inicio',
    'ajuda': 'ajuda', 'socorro': 'ajuda', 'como funciona': 'ajuda',
    'cancelar': 'cancelar', 'cancela tudo': 'cancelar', 'parar': 'cancelar',
    'cancelar pedido': 'cancelar', 'cancelar o pedido': 'cancelar', 'cancelar compra': 'cancelar',
    'cancelar a compra': 'cancelar', 'quero cancelar': 'cancelar', 'desistir': 'cancelar',
    'sair': 'sair', 'deslogar': 'sair', 'desconectar': 'sair',
    'apagar meus dados': 'apagar_dados', 'apagar dados': 'apagar_dados',
    'excluir meus dados': 'apagar_dados',
    'parar lembrete': 'parar_lembrete', 'parar lembretes': 'parar_lembrete',
    'meu pedido': 'acompanhar',
    'mudar': 'mudar', 'alterar': 'mudar', 'mudar pedido': 'mudar', 'mudar o pedido': 'mudar',
}
# "cancelar o pedido", "quero cancelar", "cancela tudo" (com erro de digitação no fim, "pediod"); "cancela a
# coca" NÃO casa: tirar um item fica com o Gemini
# "troca de mercado", "quero outro mercado", "muda de loja", "tem outra pizzaria?" (o produto, "outra pizza", não)
TROCAR_LOJA = re.compile(r'\b(?:troca\w*|muda\w*|outr[oa]s?)\b(?: \w+){0,2} (?:mercado|supermercado|loja|restaurante|'
                         r'pizzaria|lanchonete|farmacia|padaria)s?\b')
# "qual é o código de entrega?", "a senha do entregador", "código pro motoboy"
CODIGO_ENTREGA = re.compile(r'\b(?:codigo|senha|cod)\b(?: \w+){0,3} (?:entrega|entregador|motoboy|confirmacao)\b')
CANCELAR = re.compile(r'^(?:quero |pode |por favor )?cancel(?:a|ar)(?: (?:o|a|meu|minha|esse|essa))?'
                      r'(?: (?:pedi\w*|compra|tudo|isso|carrinho))?$')


def numero_em(texto):
    """'2', '2.', 'o 2', 'dois', 'o segundo', '10 unidades' -> int; None se não for número."""
    t = normalizar(texto)
    if not t:
        return None
    m = re.fullmatch(r'(?:o |a |opcao |numero |quero o |quero a )?(\d{1,3})(?: unidades?| un| pacotes?)?', t)
    if m:
        return int(m.group(1))
    t = re.sub(r'^(o|a|quero o|quero a|quero|opcao) ', '', t)
    return NUMEROS.get(t)


def hora_em(texto):
    """'às 7h', '7 horas', '7h30', '19:30', '8 da noite', 'meio-dia' -> 'HH:MM'; None se não disse hora.
    Rede de segurança do agendar: o Gemini às vezes devolve hora=None pra "todo dia as 7h"."""
    t = unicodedata.normalize('NFKD', str(texto or '').lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    if re.search(r'\bmeio[ -]dia\b', t):
        return '12:00'
    m = (re.search(r'\b(\d{1,2}):(\d{2})\b', t)
         or re.search(r'\b(\d{1,2}) ?(?:horas|hora|hrs|hs|h)(\d{2})?\b', t)
         or re.search(r'\b(\d{1,2})()(?= (?:da|de) (?:manha|tarde|noite)\b)', t))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h < 12 and re.match(r' (?:da|de) (?:tarde|noite)\b', t[m.end():]):
        h += 12
    return f'{h:02d}:{mi:02d}' if h < 24 and mi < 60 else None


def regra_rapida(texto):
    """Intenção sem LLM, ou None. Devolve dict no mesmo formato do ESQUEMA."""
    t = normalizar(texto)
    if not t:
        return None
    if t in COMANDOS:
        return {'acao': COMANDOS[t]}
    if t in ('cade meu pedido', 'cade o meu pedido', 'cade o pedido'):  # é o que já saiu, não o carrinho (U21)
        return {'acao': 'acompanhar', 'sobre': 'status'}
    if CANCELAR.match(t):
        return {'acao': 'cancelar'}
    if CODIGO_ENTREGA.search(t):  # importante demais pra depender do Gemini
        return {'acao': 'acompanhar', 'sobre': 'codigo_entrega'}
    if TROCAR_LOJA.search(t):
        return {'acao': 'trocar_loja'}
    if t in SIM:
        return {'acao': 'sim'}
    if t in NAO:
        return {'acao': 'nao'}
    if t in OI:
        return {'acao': 'saudacao'}
    if t in VALEU:
        return {'acao': 'agradecer'}
    n = numero_em(texto)
    if n is not None:
        return {'acao': 'numero', 'numero': n}
    return None


# "me sugere algo", "algo que complete esse valor": dá pra pegar sem o Gemini. As ambíguas
# ("tanto faz", "qualquer coisa") ficam com ele: com cards na tela podem ser "qualquer um desses".
SUGESTAO = re.compile(r'\b(?:sugest|suger|sugir|recomend)\w*'
                      r'|\bcomplet\w* (?:o |a |esse |essa |este |esta )?(?:valor|pedido|minimo|total)\b'
                      r'|\b(?:bater|chegar|atingir|fechar) (?:o |no |ao |a )?(?:valor|minimo)\b')


def pede_sugestao(texto):
    return bool(SUGESTAO.search(normalizar(texto)))


# "qual o valor minimo de pedido na drogaria?" é pergunta, não pedido de sugestão: o Gemini mandava pra
# "quanto deu" e a pessoa recebia o carrinho (R$ 18,89) como se fosse o mínimo (R$ 20), duas vezes (18/10).
_MINIMO = re.compile(r'\bminim[oa]\b')
_PERGUNTA = re.compile(r'^(?:qual|quanto|quantos|tem|existe|precisa|e)\b|\b(?:qual|quanto|valor)\b')


def pergunta_minimo(texto):
    t = normalizar(texto)
    return bool(_MINIMO.search(t)) and not SUGESTAO.search(t) and ('?' in str(texto) or bool(_PERGUNTA.search(t)))


# --- endereço e complemento falados ------------------------------------------------------------
# Quem fala não dita o endereço, conta: "pode mandar pra minha casa, que é na Rua Adolfo Catani, 676"
# ia inteiro pro geocode e virou o nome da rua (17/10 22h21); "eu moro no apartamento quatorze."
# virou o complemento. Aqui sai só o dado.

_LOGRADOURO_TXT = re.compile(r'\b(?:rua|r\.|av\.?|avenida|travessa|tv\.|pra[çc]a|alameda|al\.|rodovia|rod\.'
                             r'|estrada|largo|viela|servid[ãa]o)(?=[\s.,])', re.I)
_UNIDADES = {'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3, 'quatro': 4, 'cinco': 5, 'seis': 6,
             'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'onze': 11, 'doze': 12, 'treze': 13, 'quatorze': 14,
             'catorze': 14, 'quinze': 15, 'dezesseis': 16, 'dezessete': 17, 'dezoito': 18, 'dezenove': 19,
             'vinte': 20, 'trinta': 30, 'quarenta': 40, 'cinquenta': 50, 'sessenta': 60, 'setenta': 70,
             'oitenta': 80, 'noventa': 90, 'cem': 100, 'cento': 100, 'duzentos': 200, 'trezentos': 300,
             'quatrocentos': 400, 'quinhentos': 500, 'seiscentos': 600, 'setecentos': 700, 'oitocentos': 800,
             'novecentos': 900}


def numero_falado(palavras):
    """'trinta e dois' -> 32, 'cento e quatro' -> 104, 'mil e vinte' -> 1020; None se não for número."""
    total, parcial, achou = 0, 0, False
    for p in normalizar(palavras).split():
        if p == 'e' and achou:
            continue
        if p == 'mil':
            total += (parcial or 1) * 1000
            parcial, achou = 0, True
        elif p in _UNIDADES:
            parcial += _UNIDADES[p]
            achou = True
        else:
            return None
    return total + parcial if achou else None


def so_endereco(texto):
    """'pode mandar pra minha casa, que é na Rua X, 676' -> 'Rua X, 676'. Sem rua/avenida na frase
    (só o CEP, por exemplo), devolve o texto como veio."""
    s = ' '.join(str(texto or '').split()).strip(' .!')
    m = _LOGRADOURO_TXT.search(s)
    return s[m.start():].strip(' .!') if m and m.start() > 0 else s


_NUM_FALADO = (r'(?:\d+[a-z]?|[a-z]{1,2}-?\d+[a-z]?(?=\W|$)|[a-z](?=\W|$)|(?:(?:zero|uma?|duas|dois|tres|quatro|cinco|seis|sete|oito|nove|dez|onze'
               r'|doze|treze|quatorze|catorze|quinze|dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta'
               r'|cinquenta|sessenta|setenta|oitenta|noventa|cem|cento|duzentos|trezentos|quatrocentos|quinhentos'
               r'|seiscentos|setecentos|oitocentos|novecentos|mil)(?: e |\s)?)+)')
_PECA = re.compile(r'\b(apartamento|apto|ap|bloco|bl|casa|sala|andar|torre|lote|lt|quadra|qd|kitnet|edificio|predio)'
                   r'\.?\s*(?:numero |n )?(' + _NUM_FALADO + r')?')
_NOME_PECA = {'apartamento': 'Apto', 'apto': 'Apto', 'ap': 'Apto', 'bloco': 'Bloco', 'bl': 'Bloco', 'casa': 'Casa',
              'sala': 'Sala', 'andar': 'Andar', 'torre': 'Torre', 'lote': 'Lote', 'lt': 'Lote', 'quadra': 'Quadra',
              'qd': 'Quadra', 'kitnet': 'Kitnet', 'edificio': 'Edifício', 'predio': 'Prédio'}
_ORDINAL = ['primeiro', 'segundo', 'terceiro', 'quarto', 'quinto', 'sexto', 'setimo', 'oitavo', 'nono', 'decimo']
_ENCHIMENTO_COMPL = re.compile(r'^(?:(?:eu |a gente )?(?:moro|mora|fico|fica)(?: no| na| em)?|e o|e a|e no|e na|e|o|a'
                               r'|no|na|tem|sim|sim tem|fica no|fica na)\s+')


def so_complemento(texto):
    """'eu moro no apartamento quatorze.' -> 'Apto 14'; 'bloco b apartamento trinta e dois' ->
    'Bloco B, Apto 32'; 'casa dos fundos' -> 'Casa dos fundos'. Sem peça conhecida, tira só o
    enchimento do começo ('é o 14 B' -> '14 B')."""
    bruto = ' '.join(str(texto or '').split()).strip(' .!')
    t = normalizar(bruto)
    pecas = []
    for m in _PECA.finditer(t):
        nome, num = _NOME_PECA[m.group(1)], (m.group(2) or '').strip()
        if num and not re.fullmatch(r'\d+[a-z]?|[a-z]{1,2}-?\d+[a-z]?|[a-z]', num):  # "casa j4" (18/10 virou só "Casa")
            num = str(numero_falado(num) or num)
        pecas.append(f'{nome} {num.upper()}' if num else nome)
    m = re.search(r'\b(\d+|primeiro|segundo|terceiro|quarto|quinto|sexto|setimo|oitavo|nono|decimo)o? andar\b', t)
    if m:  # "segundo andar" -> "2º andar" (o _PECA só pega número DEPOIS da palavra)
        n = m.group(1) if m.group(1).isdigit() else str(_ORDINAL.index(m.group(1)) + 1)
        pecas = [p for p in pecas if p != 'Andar'] + [f'{n}º andar']
    if 'fundos' in t.split():
        pecas.append('Fundos')
    if pecas:
        return ', '.join(dict.fromkeys(pecas))
    sem = _ENCHIMENTO_COMPL.sub('', t)
    return bruto if sem == t else (bruto[len(bruto) - len(sem):] if bruto.lower().endswith(sem) else sem)


def igual_a_botao(texto, titulos):
    """A pessoa digitou o texto de um dos botões na tela? Devolve o índice ou None."""
    t = normalizar(texto)
    if not t:
        return None
    for i, titulo in enumerate(titulos):
        b = normalizar(titulo)
        if b and (t == b or (len(t) >= 4 and t in b and len(t) >= len(b) * 0.6)):
            return i
    return None


def opcao_dita(texto, titulos):
    """Quem responde falando diz frase, não o botão: "é no centro" pra "1 · Centro", "pode ser no
    pix" pra "PIX". Vale se o nome de UMA opção (3+ letras, sem o número da frente) aparece inteiro
    na frase. Com "não" na frase, ou mais de uma opção citada, devolve None (o Gemini decide)."""
    t = f' {normalizar(texto)} '
    if not t.strip() or len(t.split()) > 8 or ' nao ' in t:
        return None
    achadas = []
    for i, titulo in enumerate(titulos):
        nucleo = re.sub(r'^\d+\s+', '', normalizar(titulo))
        if len(nucleo) >= 3 and f' {nucleo} ' in t:
            achadas.append(i)
    return achadas[0] if len(achadas) == 1 else None


def cpf_em(texto):
    """CPF de 11 dígitos com dígitos verificadores válidos; None se não for."""
    d = re.sub(r'\D', '', str(texto or ''))
    if len(d) != 11 or d == d[0] * 11:
        return None
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return None
    return d


def contexto_para_llm(estado):
    """O pedaço do estado que ajuda o modelo a entender respostas curtas ("o segundo", "sim")."""
    linhas = [f'Etapa atual da conversa: {estado.get("fase") or "inicio"}.']
    perg = estado.get('pergunta') or {}
    if perg.get('texto'):
        linhas.append(f'Última pergunta do assistente: {perg["texto"][:300]}')
    if perg.get('titulos'):
        linhas.append('Opções na tela, na ordem: ' + ' | '.join(
            f'{i}. {t}' for i, t in enumerate(perg['titulos'], 1)))
    kit = estado.get('kit') or {}
    if estado.get('fase') == 'kit' and kit.get('linhas'):
        linhas.append(f'Kit na tela pra {kit.get("pessoas")} pessoas ({(kit.get("tema") or {}).get("termo")}): '
                      + ', '.join(f'{lin["qtd"]}x {lin["nome"]}' for lin in kit['linhas']))
    ultimo = (estado.get('pedidos') or [None])[0]
    if ultimo:  # sem isso "qual o código?" no meio de outra coisa não tinha a que se referir
        linhas.append(f'Último pedido já feito (pode estar a caminho): {ultimo.get("resumo") or "—"}.')
    car = estado.get('carrinho') or {}
    if car.get('itens'):
        linhas.append('Já no pedido: ' + ', '.join(f'{i["qtd"]}x {i["nome"]}' for i in car['itens']))
        falta = (car.get('minimo') or 0) - (car.get('subtotal') or 0)
        if falta > 0.005:
            linhas.append(f'Faltam R$ {falta:.2f} pro pedido mínimo da loja.')
    return '\n'.join(linhas)


def interpretar(llm, estado, partes, aviso=None):
    """partes: [('texto', str) | ('arquivo', mime, bytes)] na ordem em que chegaram.
    aviso: algo que o atendente precisa saber agora (ex.: o iFood está instável)."""
    contexto = contexto_para_llm(estado) + (f'\nAVISO INTERNO: {aviso}' if aviso else '')
    entrada = [('texto', contexto + '\n\nMensagens da pessoa, na ordem:')]
    entrada += partes
    dados, _modelo, _seg = llm(SISTEMA, entrada, ESQUEMA)
    if not isinstance(dados, dict) or dados.get('acao') not in ACOES:
        return {'acao': 'nao_entendi'}
    itens = []
    for it in dados.get('itens') or []:
        termo = ' '.join(str(it.get('termo') or '').split())[:60]
        if not termo:
            continue
        qtd = it.get('quantidade')
        busca = ' '.join(str(it.get('busca') or '').split())[:60] or termo
        itens.append({'termo': termo, 'busca': busca,
                      'quantidade': qtd if isinstance(qtd, int) and 0 < qtd <= 99 else None,
                      'tipo_loja': it.get('tipo_loja') if it.get('tipo_loja') in LOJAS else 'MERCADO',
                      'observacao': (it.get('observacao') or '')[:140] or None})
    dados['itens'] = itens[:15]
    if dados['acao'] == 'comprar' and not itens:
        dados['acao'] = 'nao_entendi'
    n = dados.get('numero')
    dados['numero'] = n if isinstance(n, int) and not isinstance(n, bool) else None
    dados['resposta'] = ' '.join(str(dados.get('resposta') or '').split())[:500] or None
    if dados['acao'] == 'agendar' and not dados.get('hora'):
        dados['hora'] = hora_em(' '.join(p[1] for p in partes if p[0] == 'texto'))
    return dados
