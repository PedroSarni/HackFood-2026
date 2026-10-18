"""Qual loja leva o pedido inteiro: a que tem TUDO o que a pessoa pediu e, entre essas, a de melhor
custo-benefício (os itens + a entrega).

Antes, a loja era a do 1º item escolhido: o resto da lista só era procurado nela ("não achei água sanitária
no Mercado X", com outro mercado ali do lado tendo tudo), e o kit escolhia a pizzaria pela pizza e avisava
"não achei coca-cola nessa loja" (17/10, 23h22). O iFood fecha um pedido por loja, então a loja certa tem que
ser escolhida ANTES do primeiro item.

`planejar` (lista com 2+ itens):
1. busca cada item uma vez, sem loja: a busca do iFood devolve ofertas de várias lojas, com taxa e tempo de
   entrega. As buscas rodam em paralelo (o freio de src/shared/ifood_mcp.py segura o ritmo: rajada vira
   fila, não martelada) e UMA chamada do Gemini filtra todas (src/bot/relevancia.py, `filtrar_varios`):
   uma por item estourava a cota por minuto da chave;
2. loja que ficou faltando 1 ou 2 itens ganha uma busca SÓ NELA pra eles: a 1ª página da busca geral pode
   não ter mostrado o item dela (num limite de buscas);
3. a conta, pra cada loja: o mais barato dela de cada item x a quantidade pedida + a taxa de entrega;
4. a ordem: quem tem mais itens da lista primeiro; empate, a mais barata (de real em real); empate de novo,
   a nota e o tempo de entrega.
`com_tudo_primeiro` faz o mesmo pro kit em grupo (src/bot/grupo.py): das lojas do prato principal, as que
também têm o que a pessoa pediu junto ("com coca") vêm primeiro, da mais barata pra mais cara.
O código decide e faz a conta; o Gemini só diz o que é o produto.
"""
import concurrent.futures
import re

from src.bot import ranking, relevancia
from src.bot.interpretar import normalizar
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao

LOJAS_NO_PLANO = 5      # as melhores ficam guardadas pro "Trocar de loja" (sem buscar de novo)
CONFERENCIAS = 6        # buscas só numa loja pra confirmar item que a busca geral não mostrou
FALTA_PRA_CONFERIR = 2  # só confere loja que ficou faltando até 2 itens
EM_PARALELO = 8         # buscas do iFood juntas (o freio dele segura o ritmo); o Gemini é uma chamada só


def infra(e):
    """iFood fora, login vencido, rede: sobe pro fluxo explicar. Item que não existe é só "não tem"."""
    cod = str(getattr(e, 'codigo', '') or '').upper()
    return isinstance(e, SemAutorizacao) or cod.startswith('HTTP_') or cod in ('TIMEOUT', 'REDE', 'SESSAO',
                                                                              'RESPOSTA_VAZIA')


def _buscas(api, endereco, consultas):
    """[(pedido, consulta, loja_id)] -> [ofertas cruas]. A 1ª vai sozinha: login que precisa renovar renova uma
    vez só (ele renova dentro de cada chamada, e duas renovações juntas derrubariam o login); as outras vão
    juntas. Erro de item vira "não tem" ([]); erro de iFood ou de login sobe."""
    def uma(c):
        pedido, consulta, loja_id = c
        try:
            return api.buscar(consulta, endereco, pedido.get('tipo_loja') or 'MERCADO', loja_id=loja_id)[0]
        except ErroMCP as e:
            if infra(e):
                raise
            print(f'melhor loja: busca de {consulta!r} falhou ({e!r})')
            return []
    if not consultas:
        return []
    primeira = [uma(consultas[0])]
    with concurrent.futures.ThreadPoolExecutor(EM_PARALELO) as ex:
        return primeira + list(ex.map(uma, consultas[1:]))


def ofertas_de_varios(api, llm, endereco, pedidos, lojas=None):
    """As ofertas de cada item (lojas[k]: só naquela loja), só o que é DE FATO o produto e na ordem: a busca
    desambiguada pelo Gemini primeiro ("cebola in natura", não "cebola"); quem não achou nada nela tenta o
    termo puro numa 2ª rodada. Um filtro do Gemini por rodada, pra todos os itens juntos."""
    lojas = lojas or [None] * len(pedidos)
    consultas = [list(dict.fromkeys(x for x in (p.get('busca'), p['termo']) if x)) for p in pedidos]
    saida, vez = [[] for _ in pedidos], list(range(len(pedidos)))
    for rodada in range(2):
        vez = [k for k in vez if rodada < len(consultas[k])]
        if not vez:
            break
        cruas = _buscas(api, endereco, [(pedidos[k], consultas[k][rodada], lojas[k]) for k in vez])
        filtradas = relevancia.filtrar_varios(llm, [(c, pedidos[k]) for k, c in zip(vez, cruas)])
        sem_nada = []
        for k, ofertas in zip(vez, filtradas):
            ofertas = ranking.ordenar(ofertas, pedidos[k])
            if lojas[k]:
                ofertas = [o for o in ofertas if o.get('loja_id') == lojas[k]]
            if ofertas:
                saida[k] = ofertas
            else:
                sem_nada.append(k)
        vez = sem_nada
    return saida


def _minutos(tempo):
    """'25-35 min' -> 35 (o pior caso); sem tempo vai pro fim."""
    nums = re.findall(r'\d+', str(tempo or ''))
    return int(nums[-1]) if nums else 999


def _ordem(lj):
    return (-len(lj['precos']), round(lj['custo']), -(lj.get('nota') or 0), _minutos(lj.get('tempo')))


def _conta(lj, quantidades):
    """O mais barato de cada item que a loja tem x a quantidade pedida + a taxa de entrega."""
    sub = sum(preco * quantidades[i] for i, preco in lj['precos'].items())
    return round(sub + (lj.get('taxa') or 0), 2)


def _anotar(lojas, i, ofertas, so_loja=None):
    """Junta as ofertas do item i por loja: {loja_id: {..., 'precos': {i: o menor preço dela}}}."""
    for o in ofertas:
        if o.get('preco') is None or (so_loja and o.get('loja_id') != so_loja):
            continue
        lj = lojas.setdefault(o['loja_id'], {'loja_id': o['loja_id'], 'loja': o.get('loja') or 'Loja',
                                             'taxa': o.get('taxa_entrega'), 'tempo': o.get('tempo'),
                                             'nota': o.get('nota'), 'precos': {}})
        lj['precos'][i] = min(lj['precos'].get(i, o['preco']), o['preco'])


def planejar(api, llm, endereco, itens):
    """Lista com 2+ itens -> {'itens': [termos], 'lojas': [...]}, a melhor loja primeiro (no máximo
    LOJAS_NO_PLANO). Cada loja: {loja_id, loja, taxa, tempo, nota, tem: [índices dos itens], custo}.
    'lojas' vazia = nada perto."""
    quantidades = [i.get('quantidade') or 1 for i in itens]
    lojas = {}
    for i, ofertas in enumerate(ofertas_de_varios(api, llm, endereco, itens)):
        _anotar(lojas, i, ofertas)
    for lj in lojas.values():
        lj['custo'] = _conta(lj, quantidades)
    _conferir(api, llm, endereco, itens, lojas, quantidades)
    melhores = sorted(lojas.values(), key=_ordem)[:LOJAS_NO_PLANO]
    return {'itens': [i['termo'] for i in itens],
            'lojas': [{'loja_id': lj['loja_id'], 'loja': lj['loja'], 'taxa': lj['taxa'], 'tempo': lj['tempo'],
                       'nota': lj['nota'], 'tem': sorted(lj['precos']), 'custo': lj['custo']} for lj in melhores]}


def _conferir(api, llm, endereco, itens, lojas, quantidades):
    """Loja quase completa (faltando até 2 itens) ganha busca só nela pro que faltou, das 3 melhores pra
    baixo, no limite de CONFERENCIAS. Só item do tipo de loja dela (pizza não se confere no mercado)."""
    pendentes = []
    for lj in sorted(lojas.values(), key=_ordem)[:3]:
        faltam = [i for i in range(len(itens)) if i not in lj['precos']]
        tipos = {itens[i].get('tipo_loja') for i in lj['precos']}
        if len(faltam) <= FALTA_PRA_CONFERIR:
            pendentes += [(lj, i) for i in faltam if itens[i].get('tipo_loja') in tipos]
    pendentes = pendentes[:CONFERENCIAS]
    achados = ofertas_de_varios(api, llm, endereco, [itens[i] for _, i in pendentes],
                                [lj['loja_id'] for lj, _ in pendentes])
    for (lj, i), ofertas in zip(pendentes, achados):
        _anotar(lojas, i, ofertas, so_loja=lj['loja_id'])
        lj['custo'] = _conta(lj, quantidades)


def com_tudo_primeiro(api, llm, endereco, fontes, extras):
    """Kit em grupo: das lojas do prato principal (`grupo.fontes`), as que também têm TUDO o que a pessoa
    pediu junto ("pizza com coca") vêm primeiro, da mais barata pra mais cara (o principal mais barato + os
    pedidos + a entrega); as outras depois, na ordem de antes. Sem nada junto, todas têm tudo e vale só a
    conta (sem busca a mais). Marca `tem_tudo` e `custo` em cada uma."""
    if not fontes:
        return fontes
    lojas, ids = {}, {f['loja_id'] for f in fontes}
    for i, ofertas in enumerate(ofertas_de_varios(api, llm, endereco, extras)):
        _anotar(lojas, i, [o for o in ofertas if o.get('loja_id') in ids])
    pendentes = [(f['loja_id'], i) for f in fontes[:3] for i in range(len(extras))
                 if i not in (lojas.get(f['loja_id']) or {}).get('precos', {})][:CONFERENCIAS]
    achados = ofertas_de_varios(api, llm, endereco, [extras[i] for _, i in pendentes],
                                [loja_id for loja_id, _ in pendentes])
    for (loja_id, i), ofertas in zip(pendentes, achados):
        _anotar(lojas, i, ofertas, so_loja=loja_id)
    for f in fontes:
        precos = (lojas.get(f['loja_id']) or {}).get('precos') or {}
        principal = min((o['preco'] for o in f.get('principais') or [] if o.get('preco') is not None), default=0)
        f['tem_tudo'] = len(precos) == len(extras)
        f['custo'] = round(principal + sum(precos.values()) + (f.get('taxa') or 0), 2)
    return sorted(fontes, key=lambda f: (not f['tem_tudo'], round(f['custo']) if f['tem_tudo'] else 0))


def mais_parecida(ofertas, nome):
    """Das 5 primeiras (já na ordem de relevância), a de nome mais parecido com `nome`; empate fica a mais
    relevante. Pra levar o carrinho de uma loja pra outra: "Arroz branco tipo 1" acha o tipo 1 de lá."""
    alvo = set(normalizar(nome).split())
    return max(ofertas[:5], key=lambda o: len(alvo & set(normalizar(o.get('nome')).split())))
