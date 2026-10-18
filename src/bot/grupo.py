"""Dividir com os amigos: "lanchar em 5 pessoas hambúrguer" vira um kit numa loja só, com quanto
fica pra cada um.

Como o kit é montado (`montar`), sempre na MESMA loja, porque o iFood fecha um pedido por loja:
1. busca o prato principal e agrupa as ofertas por loja, na ordem do iFood (fica guardado pro
   "Outra loja", que não busca de novo); só conta como principal o que É o prato (`e_o_prato`, pela
   receita: "Omelete de Pizza" não é pizza, carvão não é churrasco; 18/10 07h44 o kit de pizza saiu com
   5 omeletes de uma padaria); as lojas que têm tudo o que a pessoa pediu junto ("com coca") vêm
   primeiro, da mais barata pra mais cara (src/bot/melhor_loja.py);
2. na loja escolhida, abre os principais (getItem) e já escolhe as opções obrigatórias pelo código
   (pizza pra 3+ pessoas vai grande): o modelo vê "Pizza de calabresa (Grande (8 fatias))" e só pensa
   em quantas;
3. busca na mesma loja o que acompanha (a receita diz: refri e batata pro lanche; carvão, refri e pão
   de alho pro churrasco) e o que a pessoa pediu junto ("com coca");
4. o modelo (Beto) decide a composição e as quantidades (`SISTEMA`); o código confere (`_validar`):
   principal em quantidade de gente (`quantas_principais`), bebida por cabeça, o que não pode faltar
   (`RECEITAS[...]['essenciais']`), o que pediram entra. Se o modelo falhar, devolver bobagem ou dizer
   que a loja não tem o prato, uma regra fixa monta (`kit_padrao`) ou a próxima loja é tentada:
   ninguém fica sem kit porque a IA caiu;
5. o que entrou e não foi aberto no passo 2 passa pelo getItem pra garantir as opções obrigatórias;
6. o CÓDIGO faz a conta: preço x quantidade, taxa de entrega e o valor por pessoa, arredondado pra
   cima no centavo (a soma das partes nunca fica abaixo do total). O modelo nunca calcula dinheiro.

Ajuste do kit da tela ("sem refri", "troca a coca por guaraná", "mais batata", "mais barato", "agora
somos 6"): o código lê e aplica em cima do kit que está na tela (src/bot/kit_ajuste.py); o modelo só
entra no que o código não entendeu ("2 são vegetarianos"), e mesmo aí só pode mexer no que foi citado.

O carrinho só é criado quando a pessoa toca em "Quero esse kit" (src/bot/fluxo.py, `kit_ok`); daí
em diante é o pedido de sempre, com o "por pessoa" no total e no resumo.
"""
import concurrent.futures
import math
import re
import unicodedata

from src.bot import melhor_loja, ranking, relevancia
from src.bot.combina import complementos
from src.bot.interpretar import normalizar, numero_em
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao

MAX_PESSOAS = 30
LOJAS_GUARDADAS = 5      # lojas do principal guardadas pro "Outra loja"
PRINCIPAIS_POR_LOJA = 4  # cada um custa um getItem: o iFood real barra rajada
POR_COMPLEMENTO = 4
BUSCAS_EXTRAS = 3        # complementos buscados por kit (refri, batata, o que a pessoa pediu)
EM_PARALELO = 4          # getItem e buscas da loja juntos; o freio do iFood (src/shared/ifood_mcp.py) segura o ritmo
MAX_LINHAS = 8           # o kit cabe numa mensagem com botões (1024 caracteres)
AJUSTES_GUARDADOS = 8    # ajustes lembrados pra valer na próxima loja ("sem refri" vale no "Outra loja")

BEBIDA = re.compile(r'\b(refri\w*|coca|guarana|soda|suco|agua|cha|cerveja|chopp|vinho|sprite|fanta|pepsi|'
                    r'bebida|energetico|limonada)\b')
ALCOOL = re.compile(r'\b(cerveja|chopp|vinho|vodka|whisky|cachaca|gin|caipirinha|drink)\b')
DOIS_LITROS = re.compile(r'\b(2 ?l|2 litros?|2 ?lt|2000 ?ml|1[,.]5 ?l|1 ?5 litros?)\b')
PACK = re.compile(r'\b(pack|fardo|caixa|engradado|c ?\d{1,2}|\d{1,2} ?(?:un|unid\w*|latas|garrafas|long ?necks?))\b')
PORCAO = re.compile(r'\b(batata|fritas|porcao|onion|mandioca|polenta|nuggets|aneis)\b')
SALGADINHO = re.compile(r'\b(esfiha|esfirra|coxinha|kibe|quibe|salgad\w*|mini|bolinha|empada|enroladinho)\b')
FATIAS = re.compile(r'(\d{1,2}) (?:fatias|pedacos)')
PECAS = re.compile(r'(\d{1,3}) (?:pecas|pcs|unidades)')
PESO = re.compile(r'(\d+(?:[.,]\d+)?) ?(kg|quilos?|g|gr|gramas)\b')
GRANDE = re.compile(r'\b(grande|familia|gigante|big|g)\b')
GRUPO = re.compile(r'\b(dividir|divide|rachar|racha|galera|pessoas|amig\w*|turma|familia|todo mundo|cada um|'
                   r'por pessoa|pra cada|convidad\w*|pessoal)\b')

_N = r'(\d{1,2}|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|quinze|vinte)'
# a ordem importa. O número dito é o grupo: "com 13 amigos" = 13 (18/10 09h21: virava 14, e quem fala corrige
# com "agora somos 14" se quiser). Só "eu e mais 3" / "com mais 3 amigos" somam quem está falando.
_PESSOAS = [
    (re.compile(rf'\beu e mais {_N}\b'), 1),
    (re.compile(rf'\b(?:eu|mim|nos) e (?:mais )?{_N} (?:amig|colega|pesso|filh|net|prim|parent|irma)'), 1),
    (re.compile(rf'\bcom mais {_N} (?:amig|colega|pesso|filh|net|prim|parent|irma|convidad)'), 1),
    (re.compile(rf'\bcom {_N} (?:amig|colega|pesso|filh|net|prim|parent|irma|convidad)'), 0),
    (re.compile(rf'\b{_N} (?:pessoas?|amig\w*|convidad\w*|adultos?|cabecas)\b'), 0),
    (re.compile(rf'\b(?:somos|seremos|estamos em|vamos ser|em|pra|para|familia de|entre) {_N}\b'), 0),
]

COMIDAS = [('hamburguer', 'hambúrguer'), ('burger', 'hambúrguer'), ('lanche', 'lanche'), ('pizza', 'pizza'),
           ('esfiha', 'esfiha'), ('esfirra', 'esfiha'), ('pastel', 'pastel'), ('coxinha', 'coxinha'),
           ('salgado', 'salgado'), ('sushi', 'sushi'), ('marmita', 'marmita'), ('acai', 'açaí'),
           ('cachorro quente', 'cachorro-quente'), ('hot dog', 'cachorro-quente'), ('churras', 'carne pra churrasco'),
           ('picanha', 'picanha'), ('linguica', 'linguiça'), ('espetinho', 'espetinho')]
DE_MERCADO = {'churras', 'picanha', 'linguica'}

# --------------------------------------------------------------------------- receitas
# O que cada comida precisa pra ser kit: o que conta como o prato principal (a busca do iFood e o filtro de
# relevância deixam passar "Omelete de Pizza" pra pizza e carvão pra churrasco), quanto cada pessoa come, o que
# acompanha e o que não pode faltar. Nome que começa com `cabeca` é outra coisa (pão de alho, molho, tempero);
# `nunca` em qualquer lugar do nome tira (carne moída não vai pra churrasqueira). O que a receita não decide
# fica com o filtro do modelo (uma pizzaria que chama a pizza só de "Calabresa" continua valendo).
_SO_BEBIDA = r'refri\w*|suco|coca|guarana|agua|cerveja|sprite|fanta|pepsi|cha|energetico|vinho|chopp'
_SO_DOCE = r'sobremesa|bolo|torta|pudim|sorvete|mousse|milkshake|brownie|petit|acai'
_CABECA = (r'^(?:(?:mini|super|mega|big|combo|kit|promo|promocao|oferta|novo|nova|o|a|\d+x?|\d+ ?un|\d+ ?unid\w*)\s+)*'
           r'(?:%s)\b')
RECEITAS = [
    {'id': 'pizza', 'chaves': ('pizza',), 'principal': r'\bpizzas?\b', 'por_pessoa': 'fatias',
     'cabeca': (r'omelete|pastel|pasteis|esfih\w*|esfirr\w*|pao|paes|sanduich\w*|lanche|calzone|massa|molho|tempero|'
                r'queijo|borda|cone|salgad\w*|coxinha|empad\w*|enrolad\w*|batata|porcao|' + _SO_BEBIDA + '|' + _SO_DOCE),
     'junto': ('refrigerante',)},
    {'id': 'lanche', 'chaves': ('hamburguer', 'hamburger', 'burger', 'burguer', 'lanche', 'x ', 'sanduiche', 'cachorro',
                                'hot dog', 'misto', 'smash'),
     'principal': (r'\b(x|hamburg\w*|burg\w*|burguer\w*|smash\w*|cheese\w*|sanduich\w*|lanche\w*|misto|beirute|bauru|'
                   r'cachorro|hot ?dog|dogao|podrao|americano|bacon|salada|egg|tudo)\b'),
     'por_pessoa': 1,
     'cabeca': r'pao|paes|molho|batata|porcao|onion|nugget\w*|salada|sopa|caldo|' + _SO_BEBIDA + '|' + _SO_DOCE,
     'junto': ('refrigerante', 'batata frita')},
    {'id': 'salgado', 'chaves': ('esfiha', 'esfirra', 'coxinha', 'salgad', 'kibe', 'quibe', 'pastel', 'empada'),
     'principal': (r'\b(esfih\w*|esfirr\w*|coxinh\w*|kibe|quibe|pastel|pasteis|pastei\w*|empad\w*|salgad\w*|bolinh\w*|'
                   r'enrolad\w*|croquete|risole|rissole)\b'),
     'por_pessoa': 3, 'cabeca': r'molho|pizza|' + _SO_BEBIDA + '|' + _SO_DOCE, 'junto': ('refrigerante', 'suco')},
    {'id': 'marmita', 'chaves': ('marmita', 'marmitex', 'prato feito', 'pf', 'executivo', 'almoco', 'refeicao'),
     'principal': r'\b(marmit\w*|prato|pf|executivo|refeicao|feijoada|parmegiana|strogonoff|lasanha|yakisoba)\b',
     'por_pessoa': 1, 'cabeca': r'molho|' + _SO_BEBIDA + '|' + _SO_DOCE, 'junto': ('refrigerante', 'suco')},
    {'id': 'sushi', 'chaves': ('sushi', 'japones', 'temaki', 'combinado', 'sashimi'),
     'principal': r'\b(sushi\w*|combinad\w*|temaki\w*|hot ?roll|sashimi|uramaki|niguiri|nigiri|hossomaki|barca|joy|pecas)\b',
     'por_pessoa': 'pecas', 'cabeca': r'molho|shoyu|gengibre|wasabi|hashi|' + _SO_BEBIDA + '|' + _SO_DOCE,
     'junto': ('refrigerante',)},
    {'id': 'churrasco', 'chaves': ('churras', 'espetinho', 'picanha', 'linguic', 'carne'),
     'principal': (r'\b(picanha|linguic\w*|fraldinha|contra ?file|alcatra|maminha|costela|cupim|coxa|sobrecoxa|asa|asinha|'
                   r'frango|carne|bife|file|coracao|ancho|chorizo|paleta|lombo|pernil|kafta|espet\w*|t bone|tomahawk|'
                   r'prime rib|bisteca|acem|patinho|miolo|bovin\w*|suin\w*|tulipa|denver|short rib)\b'),
     'nunca': (r'moid\w*|de panela|cozid\w*|desfiad\w*|\bseca\b|salsich\w*|nugget\w*|empanad\w*|hamburg\w*|almondeg\w*|'
               r'\bpet\b|caes|gato|racao|ensopad\w*|figado|pronto'),
     'por_pessoa': 'kg',
     'cabeca': (r'carvao|farofa|sal|tempero|pao|paes|molho|queijo|espeto de|espetos de|acendedor|grelha|gelo|vinagrete|'
                r'cebola|alho|limao|madeira|bambu|guardanapo|' + _SO_BEBIDA + '|' + _SO_DOCE),
     'junto': ('carvão', 'refrigerante', 'pão de alho', 'farofa'), 'buscas': ('picanha', 'linguiça toscana'),
     'essenciais': (('carvão', r'\bcarv', lambda p: math.ceil(p / 6)),)},
]


def receita_de(tema):
    """A receita da comida pedida ('carne pra churrasco' -> churrasco); None pra comida sem receita (yakisoba)."""
    texto = ' '.join(normalizar((tema or {}).get(k)) for k in ('termo', 'busca')) + ' '
    for r in RECEITAS:
        if any(c in texto for c in r['chaves']):
            return r
    return None


def e_o_prato(nome, tema):
    """O item é mesmo o prato? True/False quando o nome diz; None quando não diz (fica o filtro do modelo).
    "Omelete de pizza" e "Pastel de pizza" não são pizza; "Carvão" e "Carne moída" não são churrasco."""
    n = normalizar(nome)
    r = receita_de(tema)
    if r:
        if r.get('nunca') and re.search(r['nunca'], n):
            return False
        if re.match(_CABECA % r['cabeca'], n):
            return False
        if re.search(r['principal'], n):
            return True
    for raiz in relevancia._raizes((tema or {}).get('termo')):  # o prato como sabor/recheio: "omelete de pizza"
        if re.search(rf'\b(?:de|da|do|sabor|tipo|com|para|pra|estilo|molho|massa|recheio)\s+(?:\w+\s+)?{re.escape(raiz)}', n):
            return False
    return None


def _peso_kg(nome):
    m = PESO.search(nome)
    if not m:
        return None
    v = float(m.group(1).replace(',', '.'))
    return v if m.group(2).startswith(('kg', 'quilo')) else v / 1000


def quantas_principais(tema, pessoas, cand=None):
    """Quantas unidades do principal pro grupo: pizza ~3 fatias por pessoa (pelas fatias do nome; 8 sem dizer),
    salgadinho 3 por pessoa, sushi ~10 peças por pessoa, churrasco ~400 g por pessoa (peça sem peso no nome
    serve 2), o resto 1 por pessoa."""
    r = receita_de(tema)
    nome = normalizar((cand or {}).get('nome'))
    regra = (r or {}).get('por_pessoa')
    if regra is None:  # sem receita: pelo nome do produto
        regra = 'fatias' if 'pizza' in nome else 3 if SALGADINHO.search(nome) else 1
    if regra == 'fatias':
        m = FATIAS.search(nome)
        return max(1, math.ceil(pessoas * 3 / (int(m.group(1)) if m else 8)))
    if regra == 'pecas':
        m = PECAS.search(nome)
        return max(1, math.ceil(pessoas * 10 / int(m.group(1)))) if m and int(m.group(1)) else pessoas
    if regra == 'kg':
        kg = _peso_kg(nome)
        return max(1, math.ceil(pessoas * 0.4 / kg)) if kg else max(1, math.ceil(pessoas / 2))
    return pessoas * int(regra)


def _e_bebida(cand):
    return cand['papel'] == 'bebida' or bool(BEBIDA.search(normalizar(cand['nome'] + ' ' + (cand.get('termo') or ''))))


def _qtd_bebida(cand, pessoas):
    nome = normalizar(cand['nome'])
    return math.ceil(pessoas / 4) if DOIS_LITROS.search(nome) or PACK.search(nome) else pessoas


def _essencial(cand, tema):
    """A regra do item que não pode faltar (carvão no churrasco), se o candidato for um deles."""
    nome = normalizar(cand['nome'] + ' ' + (cand.get('termo') or ''))
    for termo, regex, qtd in (receita_de(tema) or {}).get('essenciais') or ():
        if re.search(regex, nome):
            return termo, qtd
    return None


def quantidade_de(cand, pessoas, tema=None):
    """Quantos de um item que não é o principal: bebida por cabeça (2 L ou pack pra cada 4), porção pra cada 3,
    carvão pra cada 6, 1 do resto."""
    if _e_bebida(cand):
        return _qtd_bebida(cand, pessoas)
    if PORCAO.search(normalizar(cand['nome'])):
        return math.ceil(pessoas / 3)
    ess = _essencial(cand, tema)
    return ess[1](pessoas) if ess else 1


def _escala(cand, tema):
    """O item cresce com o grupo? (bebida, porção, carvão: sim; pão de alho, sobremesa: fica como está)"""
    return _e_bebida(cand) or bool(PORCAO.search(normalizar(cand['nome']))) or _essencial(cand, tema) is not None


def _so_negocio(e):
    """Item fora do cardápio ou sem opção some do kit calado; iFood fora do ar e login vencido sobem pro
    fluxo explicar (senão viraria um "não achei hambúrguer perto de você" mentiroso)."""
    cod = str(e.codigo or '').upper()
    if isinstance(e, SemAutorizacao) or cod.startswith('HTTP_') or cod in ('TIMEOUT', 'REDE', 'SESSAO', 'RESPOSTA_VAZIA'):
        raise e


def _em_paralelo(fn, itens):
    """fn(item) pra cada item, na ordem: o 1º sozinho (login que precisa renovar renova uma vez só, como em
    src/bot/melhor_loja.py) e o resto junto. Com o iFood real cada chamada leva ~2,5 s e o kit, em fila,
    levava ~50 s (18/10 11h06); o erro de qualquer uma sobe."""
    itens = list(itens)
    if not itens:
        return []
    primeiro = [fn(itens[0])]
    if len(itens) == 1:
        return primeiro
    with concurrent.futures.ThreadPoolExecutor(min(EM_PARALELO, len(itens) - 1)) as ex:
        return primeiro + list(ex.map(fn, itens[1:]))


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
    nomes = [n for chave, n in (('coca', 'coca-cola'), ('guarana', 'guaraná'), ('suco', 'suco'), ('cerveja', 'cerveja'))
             if chave in t]
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
                    'tipo_loja': 'MERCADO' if chave in DE_MERCADO else 'RESTAURANTE'}
    return None


def mesmo_prato(a, b):
    """'churrasco' e 'carne pra churrasco' (e 'picanha') são o mesmo prato; 'pizza' e 'churrasco' não; 'tomate'
    não é prato nenhum. 18/10 08h48: a Lia devolveu o prato com outras palavras e o fluxo montou outro kit."""
    ra, rb = receita_de(a), receita_de(b)
    if ra or rb:
        return bool(ra and rb and ra['id'] == rb['id'])
    ta, tb = tema_em((a or {}).get('termo')), tema_em((b or {}).get('termo'))
    if ta or tb:
        return bool(ta and tb and normalizar(ta['termo']) == normalizar(tb['termo']))
    return normalizar((a or {}).get('termo')) == normalizar((b or {}).get('termo'))


def _minusculo(texto):
    t = unicodedata.normalize('NFKD', str(texto or '').lower())
    return ''.join(c for c in t if not unicodedata.combining(c))


_VALOR = r'(\d{1,5}(?:[.,]\d{1,2})?)'
_POR_PESSOA = re.compile(rf'(?:r\$\s*)?{_VALOR}\s*(?:reais|conto|pila)?\s*(?:por pessoa|pra cada|para cada|cada um|por cabeca)')
_TETO = re.compile(rf'\b(?:ate|no maximo|maximo de|max\.?|limite de|orcamento de|gastar|teto de)\s*(?:uns\s*)?'
                   rf'(?:r\$\s*)?{_VALOR}|(?:r\$\s*){_VALOR}|{_VALOR}\s*(?:reais|conto|pila)\b')
_SEM_BEBIDA = re.compile(r'\b(?:sem|tira\w*|nao (?:quero|precisa)|nenhum\w*|zero|fora)\s+(?:o |a |os |as |de |um |uma )?'
                         r'(?:refri\w*|bebid\w*|refrigerant\w*|coca|guarana|suco|agua|cerveja)')


def teto_em(texto, pessoas=None):
    """Quanto a pessoa topa gastar no kit inteiro: "por até 300 reais" -> 300; "uns 25 por pessoa" com 13
    pessoas -> 325. None se não disse valor. Quem garante o teto é o código (`caber`), não o modelo."""
    t = _minusculo(texto)
    m = _POR_PESSOA.search(t)
    if m and pessoas:
        return round(float(m.group(1).replace(',', '.')) * pessoas, 2)
    m = _TETO.search(t)
    if not m:
        return None
    v = float(next(g for g in m.groups() if g).replace(',', '.'))
    return v if v >= 10 else None  # "até 2 litros" não é dinheiro


def caber(linhas, teto, taxa=0.0):
    """Corta o kit até o total (com a entrega) caber no teto: primeiro tira 1 da linha mais cara que tem
    mais de 1, depois some com acompanhamento que ninguém pediu. O que foi pedido ("com cerveja") e o
    principal nunca somem de todo. Devolve as linhas (as que ficaram, com total refeito)."""
    linhas = [dict(lin) for lin in linhas]
    soma = lambda: sum(lin['unit'] * lin['qtd'] for lin in linhas) + (taxa or 0)  # noqa: E731
    while teto and soma() > teto + 0.005:
        varias = [lin for lin in linhas if lin['qtd'] > 1]
        if varias:
            max(varias, key=lambda lin: lin['unit'])['qtd'] -= 1
            continue
        sobra = [lin for lin in linhas if lin['papel'] in ('acompanhamento', 'bebida')]
        if not sobra:
            break
        linhas.remove(max(sobra, key=lambda lin: lin['unit']))
    for lin in linhas:
        lin['total'] = round(lin['unit'] * lin['qtd'], 2)
    return linhas


def por_pessoa(total, pessoas):
    """Arredonda pra CIMA no centavo: 5 x R$ 36,42 cobre R$ 182,09."""
    if not total or not pessoas or pessoas < 1:
        return None
    return math.ceil(round(float(total) * 100) / pessoas) / 100


# --------------------------------------------------------------------------- busca das lojas

def fontes(api, llm, endereco, tema):
    """Busca o principal e agrupa por loja, na ordem do iFood: [{loja_id, loja, taxa, principais}]. Só entra o
    que é o prato (`e_o_prato`); se a busca dita não acha nada, a receita tem outras ("picanha" pro churrasco)."""
    ofertas = []
    consultas = [x for x in (tema.get('busca'), tema['termo']) if x] + list((receita_de(tema) or {}).get('buscas') or ())
    for consulta in dict.fromkeys(consultas):
        achadas, _prox = api.buscar(consulta, endereco, tema.get('tipo_loja') or 'RESTAURANTE')
        ofertas = [o for o in ranking.ordenar(relevancia.filtrar(llm, achadas, tema), tema)
                   if e_o_prato(o.get('nome'), tema) is not False]
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


def _buscar_na_loja(api, llm, endereco, fonte, pedido, tipo):
    """As ofertas de um complemento só nesta loja, já filtradas e na ordem de relevância."""
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
    return [o for o in achadas if o.get('loja_id') == fonte['loja_id']]


def candidatos(api, llm, endereco, fonte, tema, extras, pessoas):
    """O que o kit pode ter, nesta loja: principais já abertos e o que acompanha. Devolve (cands, faltou).
    Os getItem dos principais vão juntos, as buscas do que acompanha vão juntas e UMA chamada do modelo filtra
    todas (src/bot/relevancia.py, `filtrar_varios`): eram 3 buscas + 3 filtros em fila."""
    cands, faltou = [], []
    for c in _em_paralelo(lambda o: _abrir(api, endereco, o, pessoas), fonte['principais'][:PRINCIPAIS_POR_LOJA]):
        if c:
            cands.append({**c, 'papel': 'principal', 'termo': tema['termo'], 'loja_id': fonte['loja_id']})
    if not cands:
        return [], faltou
    tipo = tema.get('tipo_loja') or 'RESTAURANTE'
    pediu_bebida = any(BEBIDA.search(normalizar(e['termo'])) for e in extras)
    buscas = [(e, True) for e in extras[:2]]
    receita = receita_de(tema)
    juntos = list(receita['junto']) if receita and receita.get('junto') \
        else complementos([tema['termo']] + [c['base'] for c in cands], tipo)
    for termo in juntos:
        if pediu_bebida and BEBIDA.search(normalizar(termo)):
            continue  # pediu coca: não precisa sugerir outro refri por cima
        buscas.append(({'termo': termo, 'busca': termo, 'tipo_loja': tipo}, False))
    vistos, fila = set(), []
    for pedido, explicito in buscas:
        chave = normalizar(pedido['termo'])
        if chave in vistos or len(vistos) >= BUSCAS_EXTRAS:
            continue
        vistos.add(chave)
        if not explicito and ALCOOL.search(chave):
            continue
        fila.append((pedido, explicito))

    def buscar(par):
        consulta = par[0].get('busca') or par[0]['termo']
        try:
            return api.buscar(consulta, endereco, tipo, loja_id=fonte['loja_id'])[0]
        except ErroMCP as e:
            _so_negocio(e)
            print(f'kit: busca de {consulta!r} falhou: {e!r}')
            return []
    brutas = _em_paralelo(buscar, fila)
    filtradas = relevancia.filtrar_varios(llm, [(b, pedido) for b, (pedido, _) in zip(brutas, fila)])
    ja = {c['item_id'] for c in cands}
    for (pedido, explicito), ofertas in zip(fila, filtradas):
        achadas = [o for o in ranking.ordenar(ofertas, pedido)
                   if o['item_id'] not in ja and o.get('loja_id') == fonte['loja_id']]
        if not achadas and explicito and normalizar(pedido.get('busca')) != normalizar(pedido['termo']):
            achadas = [o for o in _buscar_na_loja(api, llm, endereco, fonte, pedido, tipo) if o['item_id'] not in ja]
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
- o kit é da comida pedida: só os produtos marcados [principal] contam como ela. Se NENHUM deles for de \
fato a comida pedida (pediram pizza e a loja só tem "omelete de pizza"; pediram churrasco e só tem carvão), \
responda falta_o_prato=true com itens vazio. Nunca improvise com outra comida no lugar.
- principal: pense em quanto cada pessoa come. Lanche/hambúrguer/marmita = 1 por pessoa. Pizza: cada \
pessoa come ~3 fatias (veja as fatias no nome; grande de 8 fatias serve ~3 pessoas). Esfiha, coxinha, \
kibe e salgado = ~3 por pessoa. Se tiver mais de uma opção, varie os sabores (ex.: 3 X-Burger e 2 \
X-Bacon), a não ser que peçam um só.
- bebida: refrigerante de 2 litros serve ~4 pessoas (prefira pra grupo); lata ou 600 ml = 1 por pessoa. \
Bebida alcoólica só se pedirem.
- churrasco: carne ~400 g por pessoa sem orçamento apertado (peça de picanha de ~1 kg serve 2 a 3); \
carvão NUNCA falta (saco de 3 kg pra cada ~3 kg de carne); cerveja: pack de 12 latas serve ~4 pessoas; \
queijo coalho: 1 espeto por pessoa. Com orçamento curto, fique dentro dele e explique que priorizou a carne.
- acompanhamento: porção de batata serve ~3 pessoas. Sobremesa só se pedirem ou se o grupo for grande.
- produtos marcados [pedido] a pessoa pediu: entram SEMPRE.
- respeite as restrições já combinadas, o ajuste ('2 são vegetarianos', 'sem cebola', 'mais barato') e o \
orçamento, se houver (o total do kit, com a entrega, não pode passar dele).
- se vier o kit atual, parta dele: mude SÓ o que o ajuste pede e mantenha o resto igual, mesmos produtos \
e mesmas quantidades ('2 são vegetarianos' troca 2 lanches por um sem carne; a bebida e a batata ficam as mesmas).
- use SÓ os números da lista e no máximo 8 produtos diferentes. NÃO calcule preços: o sistema calcula.
- explicacao: 1 frase curta, calorosa, em português, dizendo como pensou o kit, com 1 emoji \
("um lanche pra cada, Coca de 2 litros e batata pra dividir 😋"). Sem valores em reais e sem quantidades \
(o código pode ajustar as quantidades depois, pra caber no orçamento).
Responda só o JSON do esquema."""

ESQUEMA = {
    'type': 'OBJECT',
    'properties': {
        'itens': {'type': 'ARRAY', 'items': {
            'type': 'OBJECT',
            'properties': {'n': {'type': 'INTEGER'}, 'qtd': {'type': 'INTEGER'}},
            'required': ['n', 'qtd']}},
        'explicacao': {'type': 'STRING'},
        'falta_o_prato': {'type': 'BOOLEAN',
                          'description': 'true se nenhum produto [principal] da lista é de fato a comida pedida'},
    },
    'required': ['itens', 'explicacao'],
}


def _distribuir(total, opcoes):
    """7 unidades em 2 sabores -> [4, 3]."""
    k = len(opcoes)
    return [(c, total // k + (1 if i < total % k else 0)) for i, c in enumerate(opcoes)
            if total // k + (1 if i < total % k else 0) > 0]


def _proporcional(total, linhas):
    """7 unidades em linhas de 4 e 2 -> [(a, 5), (b, 2)]: mantém a proporção; ninguém fica com 0 enquanto couber."""
    soma = sum(q for _, q in linhas) or 1
    bruto = [(n, total * q / soma) for n, q in linhas]
    base = {n: int(v) for n, v in bruto}
    sobra = total - sum(base.values())
    for n, v in sorted(bruto, key=lambda x: -(x[1] - int(x[1]))):
        if sobra <= 0:
            break
        base[n] += 1
        sobra -= 1
    if total >= len(linhas):
        for n in base:
            if base[n] == 0:
                doador = max(base, key=base.get)
                base[doador] -= 1
                base[n] = 1
    return [(n, q) for n, q in base.items() if q > 0]


def _garantir_pedidos(escolha, cands, pessoas, tema=None, termos=None):
    """O que a pessoa pediu junto ("com coca") entra sempre: o 1º candidato de cada termo que ficou de fora."""
    escolha = list(escolha)
    dentro = {n for n, _ in escolha}
    for termo in dict.fromkeys(c['termo'] for c in cands if c['papel'] == 'pedido'):
        if termos is not None and normalizar(termo) not in termos:
            continue
        if not any(cands[n]['papel'] == 'pedido' and cands[n]['termo'] == termo for n in dentro):
            c = next(c for c in cands if c['papel'] == 'pedido' and c['termo'] == termo)
            n = cands.index(c)
            escolha.append((n, quantidade_de(c, pessoas, tema)))
            dentro.add(n)
    return escolha


def _completar(escolha, cands, pessoas, tema, sem_bebida=False):
    """O que não pode faltar: uma bebida (a de 2 litros, se tiver) a não ser que tenham dito "sem refri", e os
    essenciais da receita (carvão no churrasco)."""
    escolha = list(escolha)
    dentro = {n for n, _ in escolha}
    if not sem_bebida and not any(_e_bebida(cands[n]) for n in dentro):
        bebidas = [i for i, c in enumerate(cands) if c['papel'] == 'bebida']
        if bebidas:
            b = next((i for i in bebidas if DOIS_LITROS.search(normalizar(cands[i]['nome']))), bebidas[0])
            escolha.append((b, _qtd_bebida(cands[b], pessoas)))
            dentro.add(b)
    for termo, regex, qtd in (receita_de(tema) or {}).get('essenciais') or ():
        if any(re.search(regex, normalizar(cands[n]['nome'])) for n in dentro):
            continue
        i = next((i for i, c in enumerate(cands) if c['papel'] != 'principal' and re.search(regex, normalizar(c['nome']))), None)
        if i is not None:
            escolha.append((i, qtd(pessoas)))
            dentro.add(i)
    return escolha


def kit_padrao(pessoas, cands, tema=None, sem_bebida=False):
    """Regra fixa (modelo fora ou resposta sem sentido): [(índice, qtd)]. Principal em quantidade de gente
    (até 3 sabores), porção pra cada 3, o que pediram, bebida e o que a receita diz que não pode faltar."""
    idx = {id(c): i for i, c in enumerate(cands)}
    princ = [c for c in cands if c['papel'] == 'principal']
    if not princ:
        return []
    total = quantas_principais(tema, pessoas, princ[0])
    sabores = princ[:1 if total == 1 else 2 if total <= 6 else 3]
    escolha = [(idx[id(c)], q) for c, q in _distribuir(total, sabores)]
    porcao = next((c for c in cands if c['papel'] == 'acompanhamento' and PORCAO.search(normalizar(c['nome']))), None)
    if porcao:
        escolha.append((idx[id(porcao)], math.ceil(pessoas / 3)))
    escolha = _garantir_pedidos(escolha, cands, pessoas, tema)
    return _caber_linhas(_completar(escolha, cands, pessoas, tema, sem_bebida), cands, tema)


def requantificar(escolha, cands, pessoas, tema):
    """Os mesmos produtos, nas quantidades certas pra este tanto de gente ("agora somos 6"): o principal na
    proporção dos sabores que já estavam, bebida/porção/carvão por cabeça, o resto como estava."""
    princ = [(n, q) for n, q in escolha if cands[n]['papel'] == 'principal']
    novo = {}
    if princ:
        novo.update(_proporcional(quantas_principais(tema, pessoas, cands[princ[0][0]]), princ))
    for n, q in escolha:
        c = cands[n]
        if c['papel'] != 'principal':
            novo[n] = quantidade_de(c, pessoas, tema) if _escala(c, tema) else q
    return [(n, q) for n, q in novo.items() if q > 0]


def _validar(escolha, cands, pessoas, tema, sem_bebida=False):
    """O que o modelo devolveu passa pelo crivo do código: tem principal e em quantidade de gente (senão as
    quantidades são refeitas), no máximo 2 bebidas e por cabeça, porção em quantidade de gente, o que pediram
    entra, o que não pode faltar entra. None = sem principal (vai de regra fixa)."""
    princ = [(n, q) for n, q in escolha if cands[n]['papel'] == 'principal']
    if not princ:
        return None
    ideal = quantas_principais(tema, pessoas, cands[princ[0][0]])
    total = sum(q for _, q in princ)
    if not math.ceil(ideal * 0.6) <= total <= math.ceil(ideal * 1.5):
        print(f'kit: {total} principais pra {pessoas} pessoas (ideal {ideal}), refazendo as quantidades')
        escolha = requantificar(escolha, cands, pessoas, tema)
    bebidas = [n for n, _ in escolha if _e_bebida(cands[n])]
    saida, acompanha = [], set()
    for n, q in escolha:
        c = cands[n]
        if _e_bebida(c):
            if n in bebidas[2:]:
                continue
            if q > _qtd_bebida(c, pessoas) + 1:
                q = _qtd_bebida(c, pessoas)
        elif c['papel'] == 'acompanhamento':
            chave = normalizar(c['termo'])
            if chave in acompanha or len(acompanha) >= 3:
                continue  # um pão de alho basta (18/10 08h50: três no mesmo kit); variar sabor é coisa do principal
            acompanha.add(chave)
            if q > pessoas:
                q = quantidade_de(c, pessoas, tema)
        saida.append((n, q))
    saida = _garantir_pedidos(saida, cands, pessoas, tema)
    return _caber_linhas(_completar(saida, cands, pessoas, tema, sem_bebida), cands, tema)


def _caber_linhas(escolha, cands, tema):
    """Mais que MAX_LINHAS: sai primeiro o acompanhamento que ninguém pediu (do fim), nunca o pedido nem o essencial."""
    escolha = list(escolha)
    while len(escolha) > MAX_LINHAS:
        sobra = [n for n, _ in escolha if cands[n]['papel'] == 'acompanhamento' and not _essencial(cands[n], tema)]
        if not sobra:
            return escolha[:MAX_LINHAS]
        escolha = [(n, q) for n, q in escolha if n != sobra[-1]]
    return escolha


def _lista_pro_modelo(cands):
    linhas = []
    for i, c in enumerate(cands):
        papel = {'principal': 'principal', 'bebida': 'bebida', 'acompanhamento': 'acompanha',
                 'pedido': 'pedido'}[c['papel']]
        linhas.append(f'{i}. [{papel}] {c["nome"]} — R$ {c["unit"]:.2f}')
    return '\n'.join(linhas)


def compor(llm, pessoas, tema, cands, ajuste=None, atual=None, teto=None, taxa=None, restricoes=()):
    """O modelo escolhe o que entra e quantos; o código confere (`_validar`). Devolve ([(índice, qtd)],
    explicação, falta_o_prato). atual: o kit da tela [(índice, qtd)], quando o ajuste é livre ("2 são
    vegetarianos"): ele parte dali. restricoes: o que já foi combinado antes neste kit."""
    kit_atual = ('\nKit atual: ' + ', '.join(f'{q}x n{n}' for n, q in atual)) if atual else ''
    texto = (f'Pessoas: {pessoas}\nQuerem comer: {tema["termo"]}'
             + (f'\nRestrições já combinadas: {"; ".join(restricoes)}' if restricoes else '')
             + (f'\nAjuste pedido: {ajuste}' if ajuste else '') + kit_atual
             + (f'\nOrçamento: até R$ {teto:.2f} no total, com a entrega de R$ {taxa or 0:.2f}' if teto else '')
             + f'\n\nProdutos da loja:\n{_lista_pro_modelo(cands)}')
    sem_bebida = bool(_SEM_BEBIDA.search(normalizar(' '.join([ajuste or ''] + list(restricoes)))))
    try:
        dados, _modelo, _seg = llm(SISTEMA, [('texto', texto)], ESQUEMA)
    except Exception as e:  # noqa: BLE001 - sem o modelo, a regra fixa monta o kit
        print(f'kit: modelo falhou ({e!r}), indo de regra fixa')
        return kit_padrao(pessoas, cands, tema, sem_bebida), None, False
    dados = dados if isinstance(dados, dict) else {}
    juntos = {}
    for it in dados.get('itens') or []:
        n, q = it.get('n'), it.get('qtd')
        if isinstance(n, int) and isinstance(q, int) and 0 <= n < len(cands) and q > 0:
            juntos[n] = min(juntos.get(n, 0) + q, 50)
    escolha = list(juntos.items())
    if dados.get('falta_o_prato') and not any(cands[n]['papel'] == 'principal' for n, _ in escolha):
        return [], None, True
    escolha = _validar(escolha, cands, pessoas, tema, sem_bebida)
    if escolha is None:  # sem comida: regra fixa
        print(f'kit: composição sem sentido do modelo {list(juntos.items())}, indo de regra fixa')
        return kit_padrao(pessoas, cands, tema, sem_bebida), None, False
    explicacao = ' '.join(str(dados.get('explicacao') or '').split())[:200] or None
    if explicacao and re.search(r'r\$|\d+[.,]\d{2}', explicacao.lower()):
        explicacao = None  # dinheiro quem fala é o código
    return escolha, explicacao, False


def baratear(escolha, cands, pessoas, tema):
    """"Mais barato", um degrau por vez (o mesmo pedido de novo desce mais um): 1) todo principal vira o mais
    em conta da loja; 2) sai o acompanhamento que ninguém pediu; 3) a bebida vira a mais em conta pro grupo ou
    sai, se ninguém pediu. Devolve (kit, frase do que fez)."""
    qtd = dict(escolha)
    nome = lambda n: cands[n].get('base') or cands[n]['nome']  # noqa: E731
    princ = [n for n, _ in escolha if cands[n]['papel'] == 'principal']
    barato = min((i for i, c in enumerate(cands) if c['papel'] == 'principal'), key=lambda i: cands[i]['unit'], default=None)
    if princ and barato is not None and any(cands[n]['unit'] > cands[barato]['unit'] for n in princ):
        novo = [(barato, quantas_principais(tema, pessoas, cands[barato]))] + [(n, q) for n, q in escolha if n not in princ]
        return novo, f'fui de {nome(barato)} pra todo mundo, o mais em conta da loja'
    sobra = [n for n, _ in escolha if cands[n]['papel'] == 'acompanhamento']
    if sobra:
        n = max(sobra, key=lambda n: cands[n]['unit'] * qtd[n])
        return [(x, q) for x, q in escolha if x != n], f'tirei {nome(n)} pra baratear'
    bebidas = [n for n, _ in escolha if cands[n]['papel'] == 'bebida']
    if bebidas:
        n = max(bebidas, key=lambda n: cands[n]['unit'] * qtd[n])
        custo = cands[n]['unit'] * qtd[n]
        outras = [i for i, c in enumerate(cands) if c['papel'] == 'bebida' and i not in qtd]
        melhor = min(outras, key=lambda i: cands[i]['unit'] * _qtd_bebida(cands[i], pessoas), default=None)
        if melhor is not None and cands[melhor]['unit'] * _qtd_bebida(cands[melhor], pessoas) < custo - 0.005:
            novo = [(x, q) for x, q in escolha if x != n] + [(melhor, _qtd_bebida(cands[melhor], pessoas))]
            return novo, f'troquei {nome(n)} por {nome(melhor)}, que sai mais em conta'
        return [(x, q) for x, q in escolha if x != n], f'tirei {nome(n)} pra baratear'
    return list(escolha), 'esse já é o kit mais em conta dessa loja'


class _Loja:
    """O que o ajuste do kit precisa da loja (src/bot/kit_ajuste.py): buscar um produto só nela, reabrir um
    item com outra opção ("Refrigerante 2 L" de Coca pra Guaraná) e baratear."""

    def __init__(self, api, llm, endereco, fonte, cands, pessoas, tema):
        self.api, self.llm, self.endereco, self.fonte = api, llm, endereco, fonte
        self.cands, self.pessoas, self.tema = cands, pessoas, tema
        self.tipo = tema.get('tipo_loja') or 'RESTAURANTE'

    def buscar(self, termo):
        """Busca o termo nesta loja; os achados viram candidatos [pedido]. Devolve os índices novos."""
        pedido = {'termo': termo, 'busca': termo, 'tipo_loja': self.tipo}
        ja = {c['item_id'] for c in self.cands}
        novos = []
        for o in _buscar_na_loja(self.api, self.llm, self.endereco, self.fonte, pedido, self.tipo)[:POR_COMPLEMENTO]:
            if o['item_id'] in ja:
                continue
            self.cands.append({'item_id': o['item_id'], 'nome': o['nome'], 'base': o['nome'], 'opcoes': [],
                               'unit': o['preco'], 'aberto': False, 'papel': 'pedido', 'termo': termo,
                               'loja_id': self.fonte['loja_id']})
            novos.append(len(self.cands) - 1)
        return novos

    def reabrir(self, n, termo):
        """O mesmo item com a opção que bate com o termo (Guaraná no lugar de Coca). False se não tem."""
        c = self.cands[n]
        aberto = _abrir(self.api, self.endereco, {'item_id': c['item_id'], 'loja_id': c['loja_id'], 'nome': c['base'],
                                                  'preco': None}, self.pessoas, preferir=termo)
        if not aberto or not any(relevancia._por_palavra([{'nome': o['nome']}], termo) for o in aberto['opcoes']):
            return False
        c.update(aberto)
        return True

    def baratear(self, kit):
        return baratear(kit, self.cands, self.pessoas, self.tema)


# --------------------------------------------------------------------------- o kit

def _linhas(api, endereco, cands, escolha, pessoas):
    """Escolha -> linhas do kit; abre (getItem, todos juntos) o que ainda não foi aberto, pra garantir as opções."""
    linhas, faltou = [], []
    fechados = [cands[n] for n, _ in escolha if not cands[n]['aberto']]
    abertos = _em_paralelo(lambda c: _abrir(api, endereco, {'item_id': c['item_id'], 'loja_id': c['loja_id'],
                                                            'nome': c['nome'], 'preco': c['unit']},
                                            pessoas, preferir=c['termo']), fechados)
    for c, aberto in zip(fechados, abertos):
        if aberto:
            c.update(aberto)
    for n, q in escolha:
        c = cands[n]
        if not c['aberto']:
            faltou.append(c['termo'])
            continue
        linhas.append({'item_id': c['item_id'], 'nome': c['nome'], 'qtd': q, 'unit': c['unit'],
                       'total': round(c['unit'] * q, 2), 'opcoes': c['opcoes'], 'papel': c['papel'],
                       'termo': c.get('termo')})
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


def montar(api, llm, endereco, pessoas, tema, extras=(), ajuste=None, anterior=None, outra_loja=False, teto=None):
    """Monta (ou remonta) o kit. anterior: o kit que estava na tela; com outra_loja, pula as lojas
    já vistas sem buscar o principal de novo; com ajuste (só o pedido NOVO: o histórico vem em
    anterior['ajustes']), aplica em cima do kit da tela, na mesma loja (src/bot/kit_ajuste.py).
    Devolve (kit, motivo): motivo 'sem_principal' (nada perto) ou 'sem_loja' (acabaram as lojas)."""
    from src.bot import kit_ajuste  # import tardio: o kit_ajuste usa as regras daqui
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
    ajustes = list(anterior.get('ajustes') or []) if mesma_busca else []        # o que já pediram pra mudar
    restricoes = list(anterior.get('restricoes') or []) if mesma_busca else []  # o que ficou pro modelo
    escolha, explicacao, cands, faltou_loja, faltou_ajuste = None, None, [], [], []
    while fonte:
        if fonte['loja_id'] not in vistas:
            vistas.append(fonte['loja_id'])
        mesma_loja = mesma_busca and not outra_loja and anterior.get('loja_id') == fonte['loja_id']
        if mesma_loja and anterior.get('candidatos'):  # ajuste: a lista da tela, nunca refeita (o que entrou a mais vira "põe")
            cands, faltou_loja = [dict(c) for c in anterior['candidatos']], list(anterior.get('faltou_loja') or [])
        else:
            cands, faltou_loja = candidatos(api, llm, endereco, fonte, tema, list(extras), pessoas)
        if not cands:
            fonte = escolher_loja(lista, vistas)  # nenhum principal abriu nessa loja: tenta a próxima
            continue
        atual = None
        if mesma_loja and anterior.get('linhas'):  # o kit da tela, nos números desta lista: nenhuma linha se perde
            pos = {c['item_id']: i for i, c in enumerate(cands)}
            atual = []
            for lin in anterior['linhas']:
                if lin['item_id'] not in pos:
                    cands.append({'item_id': lin['item_id'], 'nome': lin['nome'], 'base': lin['nome'],
                                  'opcoes': lin.get('opcoes') or [], 'unit': lin['unit'], 'aberto': True,
                                  'papel': lin['papel'], 'loja_id': fonte['loja_id'],
                                  'termo': lin.get('termo') or (tema['termo'] if lin['papel'] == 'principal' else lin['nome'])})
                    pos[lin['item_id']] = len(cands) - 1
                atual.append((pos[lin['item_id']], lin['qtd']))
        loja = _Loja(api, llm, endereco, fonte, cands, pessoas, tema)
        if atual:
            # ajuste em cima do kit da tela: o código aplica; o modelo só entra no que o código não leu
            ops = kit_ajuste.ler(ajuste, cands, atual, tema) if ajuste else []
            # o que a Lia pôs em itens agora ("coca" seco, "adiciona tomate" com itens=[tomate]) entra como "põe",
            # sem refazer a lista da loja e sem repetir o que o texto do ajuste já pede
            ops += [{'op': 'poe', 'alvo': t, 'n': None} for t in _termos(extras)
                    if t not in _termos(anterior.get('extras')) and not kit_ajuste.ja_no_texto(t, ajuste or '')]
            livres = [o['texto'] for o in ops if o['op'] == 'livre']
            escolha = list(atual)
            if livres:
                texto_livre = ' e '.join(livres)
                escolha, explicacao, _falta = compor(llm, pessoas, tema, cands, texto_livre, atual, teto, fonte.get('taxa'),
                                                     restricoes)
                escolha = kit_ajuste.conferir(escolha, atual, cands, texto_livre, tema) if escolha else list(atual)
                restricoes = (restricoes + [texto_livre])[-AJUSTES_GUARDADOS:]
            if pessoas != anterior.get('pessoas'):
                escolha = requantificar(escolha, cands, pessoas, tema)
                explicacao = explicacao or f'Refiz as quantidades pra {pessoas} pessoas 👍'
            escolha, frases, faltou_ajuste = kit_ajuste.aplicar(ops, escolha, cands, pessoas, tema, loja)
            explicacao = kit_ajuste.explicar(frases) or explicacao
            break
        # kit novo nesta loja (1º kit, outra loja, outra comida): o modelo compõe, sabendo o que já foi pedido
        escolha, explicacao, falta = compor(llm, pessoas, tema, cands, ajuste, None, teto, fonte.get('taxa'),
                                            restricoes + ajustes)
        if falta:
            print(f'kit: o modelo diz que {fonte["loja"]!r} não tem {tema["termo"]!r}, tentando a próxima loja')
            cands, escolha = [], None
            fonte = escolher_loja(lista, vistas)
            continue
        for texto in ajustes + ([ajuste] if ajuste else []):  # "sem refri" dito antes vale aqui também
            tiras = [op for op in kit_ajuste.ler(texto, cands, escolha, tema) if op['op'] == 'tira']
            escolha, _frases, _faltou = kit_ajuste.aplicar(tiras, escolha, cands, pessoas, tema, loja)
        break
    if not cands or not escolha:
        return None, 'sem_principal'
    if ajuste:
        ajustes = (ajustes + [ajuste])[-AJUSTES_GUARDADOS:]
    linhas, faltou_abrir = _linhas(api, endereco, cands, escolha, pessoas)
    if teto:  # "por até 300 reais": o código garante, o modelo só tenta
        linhas = caber(linhas, teto, fonte.get('taxa'))
    if not any(lin['papel'] == 'principal' for lin in linhas):
        return None, 'sem_principal'
    kit = {'pessoas': pessoas, 'tema': tema, 'extras': list(extras), 'ajuste': ajuste, 'ajustes': ajustes,
           'restricoes': restricoes, 'teto': teto,
           'loja_id': fonte['loja_id'], 'loja': fonte['loja'], 'taxa': fonte.get('taxa'),
           'linhas': linhas, 'explicacao': explicacao, 'faltou_loja': faltou_loja,
           'faltou': list(dict.fromkeys(faltou_loja + faltou_abrir + faltou_ajuste)),
           'fontes': lista, 'vistas': vistas, 'candidatos': cands,
           'tem_outra': bool(escolher_loja(lista, vistas))}
    return contas(kit), None
