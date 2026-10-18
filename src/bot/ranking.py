"""Ordem em que as ofertas aparecem pra pessoa.

AGUARDANDO a [ORDEM DE PRIORIDADE] do time (o Fabio vai mandar). Até lá a regra é neutra:
tira o que está indisponível ou repetido e mantém a ordem que o iFood devolveu (a busca dele
já leva em conta distância e relevância). Quando a regra chegar, ela entra só aqui:
`ordenar()` é o único ponto que o fluxo chama.
"""


# 18/10: "pão de queijo" trouxe o "Pão de Queijo Waffle" na frente do tradicional. Quem pede o produto simples
# quer o simples: variação (waffle, air fryer, recheado, mini, zero, sabor...) desce; "tradicional"/"original"
# sobe; empate mantém a ordem do iFood. Só vale quando a pessoa NÃO pediu a variação ("pão de queijo waffle").
VARIACOES = ('waffle', 'air fryer', 'airfryer', 'recheado', 'recheada', 'sabor', 'mini', 'zero', 'light', 'diet',
             'integral', 'vegano', 'vegana', 'sem lactose', 'sem gluten', 'kit', 'combo', 'chips', 'snack', 'palito',
             'bolinha', 'croissant', 'folhado', 'gourmet', 'premium',
             'especial', 'artesanal', 'doce', 'apimentado', 'picante', 'defumado', 'trufado', 'crocante')
SIMPLES = ('tradicional', 'original', 'classico', 'classica')


def _normal(s):
    import unicodedata
    t = unicodedata.normalize('NFKD', str(s or '').lower())
    return ' ' + ' '.join(''.join(c for c in t if not unicodedata.combining(c)).replace('-', ' ').split()) + ' '


def _peso(nome, termo):
    n, t = _normal(nome), _normal(termo)
    variacoes = sum(1 for v in VARIACOES if f' {v} ' in n and f' {v} ' not in t)
    simples = any(f' {v} ' in n for v in SIMPLES)
    return (variacoes, 0 if simples else 1)


def ordenar(ofertas, pedido):
    """ofertas: lista normalizada (src/bot/ifood.py); pedido: {termo, quantidade, tipo_loja, observacao}.
    Tira indisponível e repetido; se o 1º é uma variação, o produto simples sobe pra frente; o resto é a ordem do iFood."""
    vistos, saida = set(), []
    for o in ofertas:
        if o.get('disponivel') is False:
            continue
        chave = (o.get('loja_id'), (o.get('nome') or '').strip().lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(o)
    termo = (pedido or {}).get('termo') or ''
    # só mexe se o 1º é uma variação: o 1º produto simples sobe pra frente, o resto fica na ordem do iFood
    if len(saida) > 1 and _peso(saida[0].get('nome'), termo)[0] > 0:
        melhor = min(range(len(saida)), key=lambda i: _peso(saida[i].get('nome'), termo) + (i,))
        if melhor:
            saida.insert(0, saida.pop(melhor))
    return saida
