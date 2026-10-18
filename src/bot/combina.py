"""O que acompanha o que já está no carrinho, pra sugestão do pedido mínimo: refri pro lanche,
manteiga pro pão, feijão pro arroz. Sem IA, então funciona com o Gemini fora; quando ele está no
ar e sugere algo, a sugestão dele vem antes (src/bot/fluxo.py, `sugerir`).
Nunca empurra remédio nem bebida alcoólica: farmácia e adega não ganham complemento automático.
"""
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
    (('carne', 'picanha', 'alcatra', 'contrafile', 'linguica', 'costela', 'acem', 'patinho', 'frango'),
     ['farofa', 'refrigerante']),
]
# bebida acompanha quase tudo em loja de comida
PADRAO = {'RESTAURANTE': ['refrigerante', 'suco'], 'MERCADO': ['refrigerante']}


def complementos(nomes, tipo_loja=None):
    """Nomes do carrinho -> o que oferecer junto: 1º o que casa com cada item, depois o padrão da
    loja; sem repetir e sem o que já está no carrinho."""
    no_carrinho = ' | '.join(normalizar(n) for n in nomes)
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
        if n not in vistos and n not in no_carrinho:
            vistos.add(n)
            termos.append(termo)
    return termos
