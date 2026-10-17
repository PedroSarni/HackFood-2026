"""Ordem em que as ofertas aparecem pra pessoa.

AGUARDANDO a [ORDEM DE PRIORIDADE] do time (o Fabio vai mandar). Até lá a regra é neutra:
tira o que está indisponível ou repetido e mantém a ordem que o iFood devolveu (a busca dele
já leva em conta distância e relevância). Quando a regra chegar, ela entra só aqui:
`ordenar()` é o único ponto que o fluxo chama.
"""


def ordenar(ofertas, pedido):
    """ofertas: lista normalizada (src/bot/ifood.py); pedido: {termo, quantidade, tipo_loja, observacao}."""
    vistos, saida = set(), []
    for o in ofertas:
        if o.get('disponivel') is False:
            continue
        chave = (o.get('loja_id'), (o.get('nome') or '').strip().lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(o)
    return saida
