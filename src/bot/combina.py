"""O que acompanha o que já está no carrinho, pra sugestão do pedido mínimo: refri pro lanche,
manteiga pro pão, feijão pro arroz. Sem IA, então funciona com o Gemini fora; quando ele está no
ar e sugere algo, a sugestão dele vem antes (src/bot/fluxo.py, `sugerir`).
Nunca empurra remédio nem bebida alcoólica: farmácia e adega não ganham complemento automático.
"""
import re

from src.bot.interpretar import normalizar

# (pedaços do nome, sem acento; o que oferecer junto). Vale a 1ª regra que casar com o item.
# Pedaço de até 2 letras ("x ") só casa no começo: "X-Bacon" é lanche, "bandeja x 12" não.
COMBINA = [
    (('hamburguer', 'burger', 'burguer', 'x ', 'smash', 'lanche', 'sanduiche', 'misto', 'beirute',
      'hot dog', 'cachorro quente'), ['refrigerante', 'batata frita', 'suco']),
    (('pizza', 'calzone'), ['refrigerante', 'pizza doce']),
    (('esfiha', 'esfirra', 'pastel', 'coxinha', 'salgado', 'kibe', 'quibe'), ['refrigerante', 'suco']),
    (('pudim', 'bolo', 'sobremesa'), ['café']),
    (('marmita', 'marmitex', 'prato feito', 'pf ', 'executivo', 'parmegiana', 'feijoada', 'strogonoff',
      'sopa', 'sushi', 'temaki', 'yakisoba', 'poke'), ['refrigerante', 'suco', 'sobremesa']),
    (('pao ', 'paes', 'baguete', 'bisnaga', 'bisnaguinha', 'torrada'), ['manteiga', 'café', 'queijo']),
    (('cafe', 'cappuccino'), ['pão de queijo', 'bolo', 'leite']),
    (('leite',), ['café', 'achocolatado']),
    (('arroz',), ['feijão', 'óleo']),
    (('feijao',), ['arroz', 'farofa']),
    (('macarrao', 'espaguete', 'lasanha', 'talharim'), ['molho de tomate', 'queijo']),
    (('picanha', 'maminha', 'fraldinha', 'cupim', 'linguica', 'costela', 'coracao', 'churrasco'),
     ['carvão', 'pão de alho', 'farofa']),
    (('carne', 'picanha', 'alcatra', 'contrafile', 'linguica', 'costela', 'acem', 'patinho', 'frango'),
     ['farofa', 'refrigerante']),
]
# bebida acompanha quase tudo em loja de comida
PADRAO = {'RESTAURANTE': ['refrigerante', 'suco'], 'MERCADO': ['refrigerante']}
# a mesma categoria com outros nomes: com Guaraná 2L no carrinho, "refrigerante" já está lá
MESMA_CATEGORIA = [
    ('refrigerante', 'refri', 'guarana', 'coca', 'pepsi', 'fanta', 'sprite', 'soda', 'kuat', 'sukita',
     'schweppes', 'tubaina', 'h2oh'),
    ('suco', 'nectar', 'del valle', 'limonada'),
    ('cafe', 'cappuccino', 'capuccino', 'expresso', 'espresso'),
    ('achocolatado', 'nescau', 'toddy'),
    ('manteiga', 'margarina'),
    ('batata frita', 'fritas'),
    ('molho de tomate', 'extrato de tomate', 'pomarola'),
    ('sobremesa', 'pudim', 'mousse', 'sorvete'),
]


def _tem(pedaco, nome):
    return f' {pedaco} ' in f' {nome} '


def ja_tem(termo, nomes):
    """O carrinho já tem isso ou algo da mesma categoria? Vale pro que o código acha e pro que a IA propõe."""
    t = normalizar(termo)
    no_carrinho = [normalizar(n) for n in nomes]
    if not t or any(t in n for n in no_carrinho):
        return True
    for grupo in MESMA_CATEGORIA:
        if any(_tem(g, t) for g in grupo) and any(_tem(g, n) for g in grupo for n in no_carrinho):
            return True
    return False


# "pão pra acompanhar o café": a IA às vezes manda a justificativa junto do produto. A frase da sugestão é
# do código e não cita nada do carrinho, então o termo fica só com o produto
_JUSTIFICATIVA = re.compile(r'\s+(?:pra|para|pro|p/)\s+(?:acompanhar|combinar|ir com|ir junto|tomar com|comer com)\b.*$',
                            re.I)


def so_o_produto(termo):
    return _JUSTIFICATIVA.sub('', ' '.join(str(termo or '').split())).strip()


def complementos(nomes, tipo_loja=None):
    """Nomes do carrinho -> o que oferecer junto: 1º o que casa com cada item, depois o padrão da
    loja; sem repetir e sem o que já está no carrinho (nem outro da mesma categoria)."""
    saida = []
    for nome in nomes:
        t = normalizar(nome) + ' '
        for chaves, extras in COMBINA:
            if any(t.startswith(c) or (len(c) > 2 and f' {c}' in t) for c in chaves):
                saida += extras
                break
    termos, vistos = [], set()
    for termo in saida + PADRAO.get(tipo_loja, []):
        n = normalizar(termo)
        if n not in vistos and not ja_tem(termo, nomes):
            vistos.add(n)
            termos.append(termo)
    return termos
