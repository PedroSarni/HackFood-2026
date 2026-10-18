"""Dividir com os amigos: "lanchar em 5 pessoas hambúrguer" vira um kit numa loja só, com quanto
fica pra cada um.

Como o kit é montado (`montar`), sempre na MESMA loja, porque o iFood fecha um pedido por loja:
1. busca o prato principal e agrupa as ofertas por loja, na ordem do iFood (fica guardado pro
   "Outra loja", que não busca de novo); as lojas que têm tudo o que a pessoa pediu junto ("com coca")
   vêm primeiro, da mais barata pra mais cara (src/bot/melhor_loja.py);
2. na loja escolhida, abre os principais (getItem) e já escolhe as opções obrigatórias pelo código
   (pizza pra 3+ pessoas vai grande): o modelo vê "Pizza de calabresa (Grande (8 fatias))" e só pensa
   em quantas;
3. busca na mesma loja o que acompanha (src/bot/combina.py: refri e batata pro lanche) e o que a
   pessoa pediu junto ("com coca");
4. o Gemini decide a composição e as quantidades (`SISTEMA`); se ele falhar ou devolver bobagem,
   uma regra fixa monta (`kit_padrao`): ninguém fica sem kit porque a IA caiu;
5. o que entrou e não foi aberto no passo 2 passa pelo getItem pra garantir as opções obrigatórias;
6. o CÓDIGO faz a conta: preço x quantidade, taxa de entrega e o valor por pessoa, arredondado pra
   cima no centavo (a soma das partes nunca fica abaixo do total). O modelo nunca calcula dinheiro.

O carrinho só é criado quando a pessoa toca em "Quero esse kit" (src/bot/fluxo.py, `kit_ok`); daí
em diante é o pedido de sempre, com o "por pessoa" no total e no resumo.
"""
import math
import re

from src.bot import melhor_loja, ranking, relevancia
from src.bot.combina import complementos
from src.bot.interpretar import normalizar, numero_em
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao

MAX_PESSOAS = 30
LOJAS_GUARDADAS = 5      # lojas do principal guardadas pro "Outra loja"
PRINCIPAIS_POR_LOJA = 4  # cada um custa um getItem: o iFood real barra rajada
POR_COMPLEMENTO = 4
BUSCAS_EXTRAS = 3        # complementos buscados por kit (refri, batata, o que a pessoa pediu)
MAX_LINHAS = 8           # o kit cabe numa mensagem com botões (1024 caracteres)

BEBIDA = re.compile(r'\b(refri\w*|coca|guarana|soda|suco|agua|cha|cerveja|chopp|vinho|sprite|fanta|pepsi|'
                    r'bebida|energetico|limonada)\b')
ALCOOL = re.compile(r'\b(cerveja|chopp|vinho|vodka|whisky|cachaca|gin|caipirinha|drink)\b')
DOIS_LITROS = re.compile(r'\b(2 ?l|2 litros?|2 ?lt|2000 ?ml|1[,.]5 ?l|1 ?5 litros?)\b')
PORCAO = re.compile(r'\b(batata|fritas|porcao|onion|mandioca|polenta|nuggets|aneis)\b')
SALGADINHO = re.compile(r'\b(esfiha|esfirra|coxinha|kibe|quibe|salgad\w*|mini|bolinha|empada|enroladinho)\b')
FATIAS = re.compile(r'(\d{1,2}) (?:fatias|pedacos)')
GRANDE = re.compile(r'\b(grande|familia|gigante|big|g)\b')
GRUPO = re.compile(r'\b(dividir|divide|rachar|racha|galera|pessoas|amig\w*|turma|familia|todo mundo|cada um|'
                   r'por pessoa|pra cada|convidad\w*|pessoal)\b')

_N = r'(\d{1,2}|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|quinze|vinte)'
# a ordem importa: "eu e mais 3" e "com 4 amigos" contam quem está escrevendo
_PESSOAS = [
    (re.compile(rf'\beu e mais {_N}\b'), 1),
    (re.compile(rf'\b(?:eu|mim|nos) e (?:mais )?{_N} (?:amig|colega|pesso|filh|net|prim|parent|irma)'), 1),
    (re.compile(rf'\bcom (?:mais )?{_N} (?:amig|colega|pesso|filh|net|prim|parent|irma|convidad)'), 1),
    (re.compile(rf'\b{_N} (?:pessoas?|amig\w*|convidad\w*|adultos?|cabecas)\b'), 0),
    (re.compile(rf'\b(?:somos|seremos|estamos em|vamos ser|em|pra|para|familia de|entre) {_N}\b'), 0),
]

COMIDAS = [('hamburguer', 'hambúrguer'), ('burger', 'hambúrguer'), ('lanche', 'lanche'), ('pizza', 'pizza'),
           ('esfiha', 'esfiha'), ('esfirra', 'esfiha'), ('pastel', 'pastel'), ('coxinha', 'coxinha'),
           ('salgado', 'salgado'), ('sushi', 'sushi'), ('marmita', 'marmita'), ('acai', 'açaí'),
           ('cachorro quente', 'cachorro-quente'), ('hot dog', 'cachorro-quente'), ('churrasco', 'carne pra churrasco')]


def _so_negocio(e):
    """Item fora do cardápio ou sem opção some do kit calado; iFood fora do ar e login vencido sobem pro
    fluxo explicar (senão viraria um "não achei hambúrguer perto de você" mentiroso)."""
    cod = str(e.codigo or '').upper()
    if isinstance(e, SemAutorizacao) or cod.startswith('HTTP_') or cod in ('TIMEOUT', 'REDE', 'SESSAO', 'RESPOSTA_VAZIA'):
        raise e


def pessoas_em(texto):
    """'lanchar em 5 pessoas' -> 5, 'eu e mais 3' -> 4, 'com 4 amigos' -> 5, 'casal' -> 2; None se não disse."""
    t = normalizar(texto)
    if re.search(r'\b(casal|eu e (?:minha|meu) (?:esposa|esposo|marido|mulher|namorad\w+|filh\w+|mae|pai))\b', t):
        return 2
    for padrao, soma in _PESSOAS:
        m = padrao.search(t)
        if m:
            n = numero_em(m.group(1)) if not m.group(1).isdigit() else int(m.group(1))
            if n:
                return n + soma
    return None


def bebidas_em(texto):
    """Sem o Gemini: o que pediram pra beber junto ("hambúrguer com coca"), como itens de pedido."""
    t = normalizar(texto)
    nomes = [n for chave, n in (('coca', 'coca-cola'), ('guarana', 'guaraná'), ('suco', 'suco')) if chave in t]
    return [{'termo': n, 'busca': n, 'quantidade': None, 'observacao': None, 'tipo_loja': 'RESTAURANTE'} for n in nomes]


def parece_grupo(texto):
    """Sem o Gemini: 'pizza pra 4 dividindo' tem número de pessoas E palavra de grupo."""
    return bool(pessoas_em(texto) and GRUPO.search(normalizar(texto)))


def tema_em(texto):
    """Sem o Gemini: a comida dita, como item de pedido; None se não achou."""
    t = normalizar(texto)
    for chave, termo in COMIDAS:
        if chave in t:
            return {'termo': termo, 'busca': termo, 'quantidade': None, 'observacao': None,
                    'tipo_loja': 'MERCADO' if chave == 'churrasco' else 'RESTAURANTE'}
    return None


def por_pessoa(total, pessoas):
    """Arredonda pra CIMA no centavo: 5 x R$ 36,42 cobre R$ 182,09."""
    if not total or not pessoas or pessoas < 1:
        return None
    return math.ceil(round(float(total) * 100) / pessoas) / 100


# --------------------------------------------------------------------------- busca das lojas

def fontes(api, llm, endereco, tema):
    """Busca o principal e agrupa por loja, na ordem do iFood: [{loja_id, loja, taxa, principais}]."""
    ofertas = []
    for consulta in dict.fromkeys(x for x in (tema.get('busca'), tema['termo']) if x):
        achadas, _prox = api.buscar(consulta, endereco, tema.get('tipo_loja') or 'RESTAURANTE')
        ofertas = ranking.ordenar(relevancia.filtrar(llm, achadas, tema), tema)
        if ofertas:
            break
    lojas = {}
    for o in ofertas:
        f = lojas.setdefault(o['loja_id'], {'loja_id': o['loja_id'], 'loja': o.get('loja') or 'Loja',
                                            'taxa': o.get('taxa_entrega'), 'principais': []})
        if len(f['principais']) < PRINCIPAIS_POR_LOJA * 2:
            f['principais'].append(o)
    return list(lojas.values())[:LOJAS_GUARDADAS]


def escolher_loja(lista, vistas=()):
    """A 1ª loja ainda não vista; entre as 3 primeiras, prefere a que tem 2+ opções do principal
    (kit pra grupo fica melhor variando o sabor). Se alguma tem tudo o que pediram junto ("com coca",
    `melhor_loja.com_tudo_primeiro`), escolhe só entre essas."""
    livres = [f for f in lista if f['loja_id'] not in vistas]
    livres = [f for f in livres if f.get('tem_tudo')] or livres
    if not livres:
        return None
    return next((f for f in livres[:3] if len(f['principais']) >= 2), livres[0])


# --------------------------------------------------------------------------- opções obrigatórias

def opcoes_automaticas(item, pessoas, preferir=''):
    """Escolhe as opções obrigatórias sem perguntar: tamanho pra 3+ pessoas vai no maior; o que bate
    com o pedido ('coca') vem antes; senão a 1ª (a padrão da loja). Devolve as opções no formato do
    fluxo ({grupo_id, opcao_id, nome, preco}) ou None se algum grupo obrigatório não tem opção."""
    escolhidas = []
    pref = set(normalizar(preferir).split())
    for g in item.get('grupos') or []:
        if not g.get('min'):
            continue
        ops = [o for o in g.get('opcoes') or [] if o.get('id')]
        if len(ops) < g['min']:
            return None
        ordem = list(ops)
        if 'tamanho' in normalizar(g.get('nome')) and pessoas >= 3:
            grandes = [o for o in ops if GRANDE.search(normalizar(o['nome']))]
            ordem = grandes + sorted((o for o in ops if o not in grandes), key=lambda o: -(o.get('preco') or 0))
        elif pref:
            casam = [o for o in ops if pref & set(normalizar(o['nome']).split())]
            ordem = casam + [o for o in ops if o not in casam]
        escolhidas += [{'grupo_id': g.get('id'), 'opcao_id': o['id'], 'nome': o['nome'], 'preco': o.get('preco')}
                       for o in ordem[:g['min']]]
    return escolhidas


def _rotulo(nome, opcoes):
    return nome + (' (' + ', '.join(o['nome'] for o in opcoes) + ')' if opcoes else '')


def _unitario(preco, opcoes):
    return round((preco or 0) + sum(o.get('preco') or 0 for o in opcoes or []), 2)


def _abrir(api, endereco, oferta, pessoas, preferir=''):
    """getItem + opções automáticas -> candidato pronto pro carrinho; None se não dá pra montar."""
    try:
        item = api.item(oferta['item_id'], oferta['loja_id'], endereco)
    except ErroMCP as e:
        _so_negocio(e)
        print(f'kit: getItem de {oferta.get("nome")!r} falhou: {e!r}')
        return None
    opcoes = opcoes_automaticas(item, pessoas, preferir)
    if opcoes is None:
        return None
    nome = item.get('nome') or oferta['nome']
    preco = oferta.get('preco') if oferta.get('preco') is not None else item.get('preco')
    return {'item_id': oferta['item_id'], 'nome': _rotulo(nome, opcoes), 'base': nome, 'opcoes': opcoes,
            'unit': _unitario(preco, opcoes), 'aberto': True}


def _papel(termo, pedido):
    if pedido:
        return 'pedido'
    return 'bebida' if BEBIDA.search(normalizar(termo)) else 'acompanhamento'


def candidatos(api, llm, endereco, fonte, tema, extras, pessoas):
    """O que o kit pode ter, nesta loja: principais já abertos e o que acompanha. Devolve (cands, faltou)."""
    cands, faltou = [], []
    for o in fonte['principais'][:PRINCIPAIS_POR_LOJA]:
        c = _abrir(api, endereco, o, pessoas)
        if c:
            cands.append({**c, 'papel': 'principal', 'termo': tema['termo'], 'loja_id': fonte['loja_id']})
    if not cands:
        return [], faltou
    tipo = tema.get('tipo_loja') or 'RESTAURANTE'
    pediu_bebida = any(BEBIDA.search(normalizar(e['termo'])) for e in extras)
    buscas = [(e, True) for e in extras[:2]]
    for termo in complementos([tema['termo']] + [c['base'] for c in cands], tipo):
        if pediu_bebida and BEBIDA.search(normalizar(termo)):
            continue  # pediu coca: não precisa sugerir outro refri por cima
        buscas.append(({'termo': termo, 'busca': termo, 'tipo_loja': tipo}, False))
    vistos, ja = set(), {c['item_id'] for c in cands}
    for pedido, explicito in buscas:
        chave = normalizar(pedido['termo'])
        if chave in vistos or len(vistos) >= BUSCAS_EXTRAS:
            continue
        vistos.add(chave)
        if not explicito and ALCOOL.search(chave):
            continue
        achadas = []
        for consulta in dict.fromkeys(x for x in (pedido.get('busca'), pedido['termo']) if x):
            try:
                brutas, _ = api.buscar(consulta, endereco, tipo, loja_id=fonte['loja_id'])
            except ErroMCP as e:
                _so_negocio(e)
                print(f'kit: busca de {consulta!r} falhou: {e!r}')
                brutas = []
            achadas = ranking.ordenar(relevancia.filtrar(llm, brutas, pedido), pedido)
            if achadas:
                break
        achadas = [o for o in achadas if o['item_id'] not in ja and o.get('loja_id') == fonte['loja_id']]
        if not achadas and explicito:
            faltou.append(pedido['termo'])
        for o in achadas[:POR_COMPLEMENTO]:
            ja.add(o['item_id'])
            cands.append({'item_id': o['item_id'], 'nome': o['nome'], 'base': o['nome'], 'opcoes': [],
                          'unit': o['preco'], 'aberto': False, 'papel': _papel(pedido['termo'], explicito),
                          'termo': pedido['termo'], 'loja_id': fonte['loja_id']})
    return cands, faltou


# --------------------------------------------------------------------------- composição

SISTEMA = """\
Você monta um kit de comida pra um grupo de pessoas dividir, com produtos de UMA loja do iFood. \
Recebe quantas pessoas são, o que querem comer, um pedido de ajuste (opcional) e os produtos da loja, \
numerados, com o preço de cada unidade. Monte um kit gostoso, que alimente todo mundo sem desperdício:
- principal: pense em quanto cada pessoa come. Lanche/hambúrguer/marmita = 1 por pessoa. Pizza: cada \
pessoa come ~3 fatias (veja as fatias no nome; grande de 8 fatias serve ~3 pessoas). Esfiha, coxinha, \
kibe e salgado = ~3 por pessoa. Se tiver mais de uma opção, varie os sabores (ex.: 3 X-Burger e 2 \
X-Bacon), a não ser que peçam um só.
- bebida: refrigerante de 2 litros serve ~4 pessoas (prefira pra grupo); lata ou 600 ml = 1 por pessoa. \
Bebida alcoólica só se pedirem.
- acompanhamento: porção de batata serve ~3 pessoas. Sobremesa só se pedirem ou se o grupo for grande.
- produtos marcados [pedido] a pessoa pediu: entram SEMPRE.
- respeite o ajuste ('sem refri', 'mais barato', '2 são vegetarianos', 'troca coca por guaraná', \
'mais batata') e o orçamento por pessoa, se houver.
- se vier o kit atual, parta dele: mude SÓ o que o ajuste pede e mantenha o resto igual, mesmos produtos \
e mesmas quantidades ('sem batata e sem refri' tira a batata e o refri; os lanches ficam os mesmos).
- use SÓ os números da lista e no máximo 8 produtos diferentes. NÃO calcule preços: o sistema calcula.
- explicacao: 1 frase curta, calorosa, em português, dizendo como pensou o kit, com 1 emoji \
("1 lanche pra cada, 2 Cocas de 2 litros e batata pra dividir 😋"). Sem valores em reais.
Responda só o JSON do esquema."""

ESQUEMA = {
    'type': 'OBJECT',
    'properties': {
        'itens': {'type': 'ARRAY', 'items': {
            'type': 'OBJECT',
            'properties': {'n': {'type': 'INTEGER'}, 'qtd': {'type': 'INTEGER'}},
            'required': ['n', 'qtd']}},
        'explicacao': {'type': 'STRING'},
    },
    'required': ['itens', 'explicacao'],
}


def _distribuir(total, opcoes):
    """7 unidades em 2 sabores -> [4, 3]."""
    k = len(opcoes)
    return [(c, total // k + (1 if i < total % k else 0)) for i, c in enumerate(opcoes)
            if total // k + (1 if i < total % k else 0) > 0]


def _qtd_bebida(cand, pessoas):
    return math.ceil(pessoas / 4) if DOIS_LITROS.search(normalizar(cand['nome'])) else pessoas


def kit_padrao(pessoas, cands):
    """Regra fixa (Gemini fora ou resposta sem sentido): [(índice, qtd)]."""
    idx = {id(c): i for i, c in enumerate(cands)}
    princ = [c for c in cands if c['papel'] == 'principal']
    if not princ:
        return []
    nome = normalizar(princ[0]['nome'])
    if 'pizza' in nome:
        m = FATIAS.search(nome)
        total = math.ceil(pessoas * 3 / (int(m.group(1)) if m else 8))
    elif SALGADINHO.search(nome):
        total = pessoas * 3
    else:
        total = pessoas
    sabores = princ[:1 if total == 1 else 2 if total <= 6 else 3]
    escolha = [(idx[id(c)], q) for c, q in _distribuir(total, sabores)]
    bebidas = [c for c in cands if c['papel'] == 'bebida']
    if bebidas:
        b = next((c for c in bebidas if DOIS_LITROS.search(normalizar(c['nome']))), bebidas[0])
        escolha.append((idx[id(b)], _qtd_bebida(b, pessoas)))
    porcao = next((c for c in cands if c['papel'] == 'acompanhamento' and PORCAO.search(normalizar(c['nome']))), None)
    if porcao:
        escolha.append((idx[id(porcao)], math.ceil(pessoas / 3)))
    for termo in dict.fromkeys(c['termo'] for c in cands if c['papel'] == 'pedido'):
        c = next(c for c in cands if c['papel'] == 'pedido' and c['termo'] == termo)
        q = _qtd_bebida(c, pessoas) if BEBIDA.search(normalizar(termo + ' ' + c['nome'])) else 1
        escolha.append((idx[id(c)], q))
    return escolha


def _lista_pro_modelo(cands):
    linhas = []
    for i, c in enumerate(cands):
        papel = {'principal': 'principal', 'bebida': 'bebida', 'acompanhamento': 'acompanha',
                 'pedido': 'pedido'}[c['papel']]
        linhas.append(f'{i}. [{papel}] {c["nome"]} — R$ {c["unit"]:.2f}')
    return '\n'.join(linhas)


_TIRA = re.compile(r'\b(?:sem|tira\w*)\b')
_POE_OU_TROCA = re.compile(r'\b(?:troc\w*|mais|menos|barat\w*|vegetarian\w*|adicion\w*|coloc\w*|bota\w*|com'
                           r'|acrescent\w*|mud\w*|outr\w*|em vez)\b')


def _so_tira(ajuste):
    t = normalizar(ajuste)
    return bool(_TIRA.search(t)) and not _POE_OU_TROCA.search(t)


def _citado(nome, ajuste):
    t = f' {normalizar(ajuste)} '
    return any(f' {p} ' in t for p in normalizar(nome).split() if len(p) >= 4)


def compor(llm, pessoas, tema, cands, ajuste=None, atual=None):
    """O Gemini escolhe o que entra e quantos; o código confere. Devolve ([(índice, qtd)], explicação).
    atual: o kit da tela [(índice, qtd)]; com ajuste, ele parte dali em vez de recompor do zero
    (18/10: "sem a batata e sem o refri" trocou o X-Bacon por X-Salada)."""
    kit_atual = ('\nKit atual: ' + ', '.join(f'{q}x n{n}' for n, q in atual)) if atual and ajuste else ''
    texto = (f'Pessoas: {pessoas}\nQuerem comer: {tema["termo"]}'
             + (f'\nAjuste pedido: {ajuste}' if ajuste else '') + kit_atual
             + f'\n\nProdutos da loja:\n{_lista_pro_modelo(cands)}')
    try:
        dados, _modelo, _seg = llm(SISTEMA, [('texto', texto)], ESQUEMA)
    except Exception as e:  # noqa: BLE001 - sem o Gemini, a regra fixa monta o kit
        print(f'kit: Gemini falhou ({e!r}), indo de regra fixa')
        return kit_padrao(pessoas, cands), None
    juntos = {}
    for it in (dados or {}).get('itens') or []:
        n, q = it.get('n'), it.get('qtd')
        if isinstance(n, int) and isinstance(q, int) and 0 <= n < len(cands) and q > 0:
            juntos[n] = min(juntos.get(n, 0) + q, 50)
    escolha = list(juntos.items())[:MAX_LINHAS]
    principais = sum(q for n, q in escolha if cands[n]['papel'] == 'principal')
    if not principais or principais > pessoas * 6:  # sem comida ou absurdo (60 lanches pra 10): regra fixa
        print(f'kit: composição sem sentido do Gemini {escolha}, indo de regra fixa')
        return kit_padrao(pessoas, cands), None
    padrao = kit_padrao(pessoas, cands)
    for termo in dict.fromkeys(c['termo'] for c in cands if c['papel'] == 'pedido'):
        if not any(cands[n]['papel'] == 'pedido' and cands[n]['termo'] == termo for n, _ in escolha):
            escolha += [(n, q) for n, q in padrao if cands[n]['termo'] == termo][:1]  # o que pediram entra sempre
    if atual and ajuste and _so_tira(ajuste):
        # ajuste que só tira: nada novo entra e o principal que não foi citado fica como estava
        mantidos = {n for n, _ in escolha}
        sem_bebida = re.search(r'\b(?:refri\w*|bebida\w*)\b', normalizar(ajuste))
        tirado = {n for n, _ in atual if _citado(cands[n]['nome'], ajuste)
                  or (sem_bebida and cands[n]['papel'] == 'bebida')}
        travada = [(n, q) for n, q in atual if n not in tirado
                   and (n in mantidos or cands[n]['papel'] == 'principal')]
        if any(cands[n]['papel'] == 'principal' for n, _ in travada):
            escolha = travada
    explicacao = ' '.join(str((dados or {}).get('explicacao') or '').split())[:200] or None
    if explicacao and re.search(r'r\$|\d+[.,]\d{2}', explicacao.lower()):
        explicacao = None  # dinheiro quem fala é o código
    return escolha[:MAX_LINHAS], explicacao


# --------------------------------------------------------------------------- o kit

def _linhas(api, endereco, cands, escolha, pessoas):
    """Escolha -> linhas do kit; abre (getItem) o que ainda não foi aberto, pra garantir as opções."""
    linhas, faltou = [], []
    for n, q in escolha:
        c = cands[n]
        if not c['aberto']:
            aberto = _abrir(api, endereco, {'item_id': c['item_id'], 'loja_id': c['loja_id'], 'nome': c['nome'],
                                            'preco': c['unit']}, pessoas, preferir=c['termo'])
            if not aberto:
                faltou.append(c['termo'])
                continue
            c.update(aberto)
        linhas.append({'item_id': c['item_id'], 'nome': c['nome'], 'qtd': q, 'unit': c['unit'],
                       'total': round(c['unit'] * q, 2), 'opcoes': c['opcoes'], 'papel': c['papel']})
    ordem = {'principal': 0, 'pedido': 1, 'acompanhamento': 2, 'bebida': 3}
    linhas.sort(key=lambda lin: ordem.get(lin['papel'], 9))
    return linhas, faltou


def contas(kit):
    """Subtotal, total aproximado (com a taxa de entrega da busca) e por pessoa. Só o código conta."""
    sub = round(sum(lin['total'] for lin in kit['linhas']), 2)
    total = round(sub + (kit.get('taxa') or 0), 2)
    kit.update(subtotal=sub, total=total, por_pessoa=por_pessoa(total, kit['pessoas']))
    return kit


def _termos(itens):
    return [normalizar(i['termo']) for i in itens or []]


def montar(api, llm, endereco, pessoas, tema, extras=(), ajuste=None, anterior=None, outra_loja=False):
    """Monta (ou remonta) o kit. anterior: o kit que estava na tela; com outra_loja, pula as lojas
    já vistas sem buscar o principal de novo; com ajuste, refaz na mesma loja.
    Devolve (kit, motivo): motivo 'sem_principal' (nada perto) ou 'sem_loja' (acabaram as lojas)."""
    extras = [e for e in extras or [] if normalizar(e['termo']) != normalizar(tema['termo'])]
    mesma_busca = anterior and normalizar(anterior['tema']['termo']) == normalizar(tema['termo'])
    lista = anterior['fontes'] if mesma_busca else fontes(api, llm, endereco, tema)
    if not lista:
        return None, 'sem_principal'
    novos_extras = extras and not (mesma_busca and _termos(extras) == _termos(anterior.get('extras')))
    if not mesma_busca or novos_extras:
        # a loja do kit: a que tem o que pediram junto ("com coca", 17/10 23h22) e sai mais em conta
        lista = melhor_loja.com_tudo_primeiro(api, llm, endereco, lista, extras)
    vistas = list(anterior.get('vistas') or []) if mesma_busca else []
    if mesma_busca and not outra_loja:
        fonte = next((f for f in lista if f['loja_id'] == anterior['loja_id']), None) or escolher_loja(lista)
        if novos_extras and not fonte.get('tem_tudo'):  # a loja do kit não tem o que pediram agora: troca
            fonte = escolher_loja(lista) or fonte
    else:
        fonte = escolher_loja(lista, vistas)
    if not fonte:
        return None, 'sem_loja'
    while fonte:
        if fonte['loja_id'] not in vistas:
            vistas.append(fonte['loja_id'])
        reaproveita = (mesma_busca and not outra_loja and anterior.get('loja_id') == fonte['loja_id']
                       and _termos(extras) == _termos(anterior.get('extras')) and anterior.get('candidatos'))
        if reaproveita:
            cands, faltou = [dict(c) for c in anterior['candidatos']], []
        else:
            cands, faltou = candidatos(api, llm, endereco, fonte, tema, list(extras), pessoas)
        if cands:
            break
        fonte = escolher_loja(lista, vistas)  # nenhum principal abriu nessa loja: tenta a próxima
    if not cands:
        return None, 'sem_principal'
    atual = None
    if reaproveita and anterior.get('linhas'):  # mesma loja e mesmos candidatos: os números batem
        pos = {c['item_id']: i for i, c in enumerate(cands)}
        atual = [(pos[lin['item_id']], lin['qtd']) for lin in anterior['linhas'] if lin['item_id'] in pos]
    escolha, explicacao = compor(llm, pessoas, tema, cands, ajuste, atual)
    linhas, faltou_abrir = _linhas(api, endereco, cands, escolha, pessoas)
    if not any(lin['papel'] == 'principal' for lin in linhas):
        return None, 'sem_principal'
    kit = {'pessoas': pessoas, 'tema': tema, 'extras': list(extras), 'ajuste': ajuste,
           'loja_id': fonte['loja_id'], 'loja': fonte['loja'], 'taxa': fonte.get('taxa'),
           'linhas': linhas, 'explicacao': explicacao, 'faltou': list(dict.fromkeys(faltou + faltou_abrir)),
           'fontes': lista, 'vistas': vistas, 'candidatos': cands,
           'tem_outra': bool(escolher_loja(lista, vistas))}
    return contas(kit), None
