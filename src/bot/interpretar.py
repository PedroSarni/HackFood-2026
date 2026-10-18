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
         'agendar', 'sugerir', 'fora_do_escopo', 'nao_entendi']
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
        'numero': {'type': 'INTEGER', 'nullable': True},
        'texto': {'type': 'STRING', 'nullable': True},
        'transcricao': {'type': 'STRING', 'nullable': True},
        'resposta': {'type': 'STRING', 'nullable': True},
        'hora': {'type': 'STRING', 'nullable': True, 'description': 'quando agendar: horário dito, HH:MM 24h'},
    },
    'required': ['acao'],
}

SISTEMA = """\
Você interpreta mensagens de WhatsApp para um assistente que faz pedidos no iFood \
(mercado, restaurante, farmácia, bebidas, pet). Quem escreve, na maioria, são pessoas idosas \
ou com pouca prática com celular: escrevem com erros, sem acento, abreviado, em várias \
mensagens picadas, ou mandam áudio e foto. Seja generoso: descubra o que a pessoa quer AGORA.

Responda só o JSON do esquema. Campos:
- acao: uma de comprar, sugerir, mais_opcoes, escolher, sim, nao, quantidade, endereco, ver_pedido, \
finalizar, tirar_item, cancelar, acompanhar, repetir, ajuda, saudacao, agradecer, sair, \
apagar_dados, parar_lembrete, agendar, fora_do_escopo, nao_entendi.
- itens: quando acao=comprar, cada produto pedido, na ordem. termo curto e no singular \
("pão francês", "leite integral", "carne moída", "dipirona"), sem a quantidade. \
quantidade só se a pessoa disse (meia dúzia=6, uma dúzia=12, "uns 3"=3). observacao para \
detalhes ("bem passado", "sem cebola", "marca Italac"). Quando acao=sugerir, até 3 produtos \
que combinem com o que já está no pedido, no mesmo formato.
- busca: o texto que vai na busca do iFood, que é burra (casa com nome de loja e com sabor). \
1 a 4 palavras, como o produto aparece num catálogo. Se a palavra pura engana, desambigue: \
"cebola" -> "cebola in natura" (senão vem salgadinho sabor cebola), "limão" -> "limão tahiti", \
"frango" -> "frango congelado" no mercado ou "frango assado" no restaurante, "coca" -> \
"coca-cola". Se não engana, repita o termo ("coxinha", "dipirona", "arroz").
- tipo_loja: MERCADO para alimento, bebida não alcoólica, limpeza e higiene (pão, leite, carne, \
arroz, fruta, café, sabão); RESTAURANTE para comida pronta (pizza, lanche, marmita, açaí, \
sushi, pastel, "almoço"); FARMACIA para remédio e farmácia; BEBIDAS para bebida alcoólica \
(cerveja, vinho); PET para ração e coisas de bicho; LOJA para o resto.
- numero: quando agendar, de quantos em quantos dias (todo dia=1, toda semana=7, a cada 15 dias=15, todo mês=30; sem frequência dita = null).
- hora: quando agendar e a pessoa disse horário, "HH:MM" 24h ("às 18h" = "18:00", "meio-dia" = \
"12:00", "8 da noite" = "20:00"); senão null. Quando escolher (1, 2 ou 3, entre as opções que estão na tela; "o primeiro"=1, \
"o do meio"=2, "o último" = o último da tela) ou quando quantidade.
- texto: quando endereco, o endereço como a pessoa disse.
- transcricao: se veio áudio ou foto, o que foi dito ou o que está escrito/mostrado, curto.
- resposta: SEMPRE preencha. É o que um atendente simpático diria de volta, com 1 ou 2 emojis, \
português informal e caloroso, até 3 frases curtas (no máximo 350 caracteres). Pode conversar à \
vontade: responder ao que a pessoa contou, comentar, brincar de leve, ter empatia ("que calor \
hoje" -> "Nem me fale! 🥵"). Mas SEMPRE termine puxando de volta pra compra com uma sugestão ou \
pergunta concreta ligada ao que ela disse ("que tal uma água geladinha? É só me dizer 😉"). \
Se não entendeu, diga o que entendeu e como ela pode pedir (escrevendo; não sugira mandar áudio). Não dê aula, receita, conselho \
médico, opinião política nem responda perguntas gerais: no máximo uma frase leve e volte pro \
pedido. Se houver AVISO INTERNO no contexto, leve ele em conta (ex.: explique com calma que o \
iFood está instável). Nunca diga que fez algo que não fez. O assistente SABE deixar pedidos no automático (recorrência: no dia combinado ele chama a pessoa e pede com o "sim" dela): nunca diga que não consegue agendar ou repetir pedidos.

Regras:
- Lista de compras (escrita, falada ou foto de papel) vira acao=comprar com todos os itens.
- "quero mais", "tem outro", "mostra mais", "outras" com opções na tela = mais_opcoes.
- "sim", "pode", "isso", "confirma", "fechou", "ok" = sim. "não", "nao quero", "errado" = nao.
- "acabou", "só isso", "pode fechar", "terminei" = finalizar.
- "cadê meu pedido", "já saiu?", "vai demorar?" = acompanhar.
- "o de sempre", "pedir igual da outra vez", "repetir" = repetir.
- "me sugere algo", "o que você recomenda", "qualquer coisa", "você escolhe", "algo pra completar \
o valor" ou "o pedido mínimo" = sugerir (quando a pessoa não disse o produto).
- "quero isso todo dia às 18h", "toda semana", "todo mês", "deixa no automático", "me lembra de pedir", "pedido recorrente", "assinatura" = agendar (mesmo no meio de um pedido).
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
    'sair': 'sair', 'deslogar': 'sair', 'desconectar': 'sair',
    'apagar meus dados': 'apagar_dados', 'apagar dados': 'apagar_dados',
    'excluir meus dados': 'apagar_dados',
    'parar lembrete': 'parar_lembrete', 'parar lembretes': 'parar_lembrete',
    'meu pedido': 'acompanhar', 'cade meu pedido': 'acompanhar',
}


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


def regra_rapida(texto):
    """Intenção sem LLM, ou None. Devolve dict no mesmo formato do ESQUEMA."""
    t = normalizar(texto)
    if not t:
        return None
    if t in COMANDOS:
        return {'acao': COMANDOS[t]}
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
    dados['resposta'] = ' '.join(str(dados.get('resposta') or '').split())[:500] or None
    return dados
