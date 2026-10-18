"""Filtro de relevância: só mostra o que é DE FATO o produto pedido.

A busca do iFood (searchOffers) casa o termo também com o nome da LOJA: pedir "coxinha" trouxe
"Espeto de Frango Empanado" da "Coxinhas Dona Nita" (17/10 18h57). Aqui o Gemini olha o pedido
da pessoa e a lista que veio, devolve só os itens que são o produto e já na ordem de relevância.
Se o Gemini falhar, um plano B por palavra: o NOME DO ITEM (não da loja) tem que conter o termo.
"""
from src.bot.interpretar import normalizar

MAX_ITENS = 25  # uma página do iFood

SISTEMA = """\
Você filtra resultados de busca de um app de delivery. A busca é burra: casa a palavra com o \
nome da LOJA também, então vem item que não tem nada a ver (pedir "coxinha" e vir "espeto de \
frango" de uma loja chamada "Coxinhas da Ana").

Devolva em `manter` os números dos itens que SÃO o produto que a pessoa pediu, do mais \
relevante pro menos relevante. Regras:
- Julgue pelo NOME DO ITEM. O nome da loja não conta como prova.
- Aceite variações do mesmo produto (sabores, tamanhos, marcas, "mini", "kit com 10", \
"combo de coxinhas"). Para "refrigerante", "coca" vale; para "remédio pra dor de cabeça", \
dipirona/paracetamol valem.
- Ingrediente não é produto com sabor dele: "cebola" é a cebola (legume), não salgadinho \
sabor cebola; "morango" é a fruta, não iogurte de morango (a não ser que ela tenha pedido isso).
- Se a pessoa pediu marca ou detalhe (observação), ponha primeiro os que batem com isso.
- Na dúvida razoável, mantenha; o que claramente é outro produto, tire.
Responda só o JSON do esquema."""

ESQUEMA = {'type': 'OBJECT',
           'properties': {'manter': {'type': 'ARRAY', 'items': {'type': 'INTEGER'}}},
           'required': ['manter']}


def _raizes(termo):
    """'pão francês' -> ['pao', 'franc']: palavras de 3+ letras, cortadas pra aceitar plural/flexão."""
    return [p[:5] if len(p) > 5 else p for p in normalizar(termo).split() if len(p) >= 3]


# sem o Gemini, a palavra pura perde o sinônimo óbvio: "refrigerante" é a Coca, "hambúrguer" é o X-Bacon
ALTERNATIVAS = {'refri': ('refri', 'coca', 'guarana', 'fanta', 'sprite', 'pepsi', 'soda'),
                'hambu': ('hambu', 'burg', 'x '), 'lanch': ('lanch', 'burg', 'x ', 'misto', 'sanduich')}


def _por_palavra(ofertas, termo):
    raizes = _raizes(termo)
    if not raizes:
        return ofertas
    return [o for o in ofertas
            if all(any(alt in normalizar(o.get('nome')) + ' ' for alt in ALTERNATIVAS.get(r, (r,))) for r in raizes)]


def filtrar(llm, ofertas, pedido):
    """ofertas normalizadas (src/bot/ifood.py) -> só as relevantes, em ordem de relevância."""
    termo = (pedido or {}).get('termo') or ''
    if not ofertas or not termo:
        return ofertas
    lote = ofertas[:MAX_ITENS]
    texto = _pediu(pedido) + '\n\nItens:\n' + '\n'.join(_linhas(lote))
    try:
        dados, _modelo, _seg = llm(SISTEMA, [('texto', texto)], ESQUEMA)
        manter = [i for i in (dados or {}).get('manter') or [] if isinstance(i, int) and 0 <= i < len(lote)]
        escolhidos = [lote[i] for i in dict.fromkeys(manter)]
        if escolhidos:
            return escolhidos + _por_palavra(ofertas[MAX_ITENS:], termo)
        print(f'relevância: Gemini não manteve nada pra {termo!r}, indo por palavra')
        return _por_palavra(ofertas, termo)  # pode ser [] mesmo: melhor "não achei" que coisa errada
    except Exception as e:  # noqa: BLE001 - filtro é bônus: sem ele vai por palavra
        print(f'relevância falhou ({e!r}), indo por palavra')
    # Gemini fora: palavra; se a palavra zerar (sinônimo, "refri" x "Coca"), mostra o que o iFood deu
    return _por_palavra(ofertas, termo) or ofertas


def _pediu(pedido):
    termo, busca, obs = (pedido or {}).get('termo') or '', (pedido or {}).get('busca'), (pedido or {}).get('observacao')
    return (f'A pessoa pediu: {termo}' + (f' (ou seja: {busca})' if busca and busca != termo else '')
            + (f' (detalhe: {obs})' if obs else ''))


def _linhas(lote):
    return [f'{i}. {o.get("nome")}  (loja: {o.get("loja") or "?"})' for i, o in enumerate(lote)]


# várias buscas numa chamada só: a escolha da loja da lista (src/bot/melhor_loja.py) filtra a lista inteira de
# uma vez. Uma chamada por item estourava a cota por minuto da chave do Gemini (429 na 13ª, 17/10 23h55).
# As regras são as MESMAS do filtro de um item (recortadas do SISTEMA), pra nunca divergirem.
SISTEMA_VARIOS = (
    'Você filtra resultados de busca de um app de delivery, de VÁRIAS buscas de uma vez (uma lista de '
    'compras). A busca é burra: casa a palavra com o nome da LOJA também, então vem item que não tem nada '
    'a ver.\n\nPra CADA lista, devolva em `manter` os números dos itens daquela lista que SÃO o produto que '
    'a pessoa pediu nela, do mais relevante pro menos relevante. Regras, as mesmas pra todas:\n'
    + SISTEMA[SISTEMA.index('- Julgue'):SISTEMA.index('Responda só')]
    + 'Responda só o JSON do esquema, com uma entrada por lista (o número dela em `lista`).')

ESQUEMA_VARIOS = {'type': 'OBJECT',
                  'properties': {'listas': {'type': 'ARRAY', 'items': {
                      'type': 'OBJECT',
                      'properties': {'lista': {'type': 'INTEGER'},
                                     'manter': {'type': 'ARRAY', 'items': {'type': 'INTEGER'}}},
                      'required': ['lista', 'manter']}}},
                  'required': ['listas']}


def filtrar_varios(llm, pares):
    """Como `filtrar`, pra várias buscas numa chamada só. pares: [(ofertas, pedido)] -> [só as relevantes de
    cada uma, na ordem de relevância], na ordem dos pares. Gemini fora: cada uma por palavra, como no filtrar."""
    lotes, blocos = [], []
    for k, (ofertas, pedido) in enumerate(pares):
        lote = (ofertas or [])[:MAX_ITENS] if (pedido or {}).get('termo') else []
        lotes.append(lote)
        if lote:
            blocos.append(f'Lista {k}. {_pediu(pedido)}\nItens:\n' + '\n'.join(_linhas(lote)))
    if not blocos:
        return [ofertas for ofertas, _ in pares]
    manter, falhou = {}, False
    try:
        dados, _modelo, _seg = llm(SISTEMA_VARIOS, [('texto', '\n\n'.join(blocos))], ESQUEMA_VARIOS)
        for e in (dados or {}).get('listas') or []:
            k = e.get('lista')
            if isinstance(k, int) and 0 <= k < len(lotes):
                manter[k] = [i for i in e.get('manter') or [] if isinstance(i, int) and 0 <= i < len(lotes[k])]
    except Exception as e:  # noqa: BLE001 - filtro é bônus: sem ele vai por palavra
        print(f'relevância em lote falhou ({e!r}), indo por palavra')
        falhou = True
    saida = []
    for k, (ofertas, pedido) in enumerate(pares):
        termo = (pedido or {}).get('termo') or ''
        if not lotes[k]:
            saida.append(ofertas)  # sem oferta ou sem termo: igual ao filtrar
        elif falhou:
            saida.append(_por_palavra(ofertas, termo) or ofertas)
        elif manter.get(k):
            saida.append([lotes[k][i] for i in dict.fromkeys(manter[k])] + _por_palavra(ofertas[MAX_ITENS:], termo))
        else:
            saida.append(_por_palavra(ofertas, termo))  # o Gemini não manteve nada nessa: palavra (pode dar [])
    return saida
