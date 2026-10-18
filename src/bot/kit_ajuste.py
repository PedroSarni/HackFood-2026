"""O ajuste do kit lido e aplicado pelo CÓDIGO: "sem refri", "troca a coca por guaraná", "mais batata",
"mais barato" mexem SÓ no que a pessoa citou, em cima do kit que está na tela (src/bot/grupo.py chama).

18/10 de manhã o Beto (o modelo) recebia o ajuste inteiro e devolvia outro kit: "troca a coca por guaraná"
trocava o lanche junto, "mais batata" mexia na quantidade de tudo, "sem refri" virava 4 sucos. Agora cada
frase do ajuste ("sem refri e mais batata") vira uma operação, e a operação é determinística:
- tira:   "sem refri", "tira a batata", "não quero cerveja"      -> some a linha citada, e só ela
- troca:  "troca a coca por guaraná", "guaraná em vez de coca"    -> a citada sai e a pedida entra no lugar
- mais / menos: "mais batata", "mais 2 refri", "menos uma pizza" -> a quantidade da linha citada
- qtd:    "só 3 pizzas", "deixa 2 refri"                          -> a quantidade vira essa
- poe:    "põe uma sobremesa", "coloca cerveja", "com farofa"     -> entra (da lista da loja ou de uma busca nela)
- barato: "mais barato", "tá caro"                                -> um degrau da escada (grupo.baratear)
- livre:  o resto ("2 são vegetarianos", "sem cebola")            -> vai pro modelo, que só mexe no que citou (`conferir`)
O mesmo ajuste no mesmo kit dá sempre o mesmo resultado, e a explicação na tela é do código ("Tirei o refri 👍").
"""
import re

from src.bot import grupo, relevancia
from src.bot.interpretar import normalizar, numero_em

_ARTIGOS = r'(?:(?:o|a|os|as|um|uma|uns|umas|de|do|da|dos|das|esse|essa|esses|essas|este|esta|aquele|aquela|ai|la)\s+)*'
_NUM = r'(\d{1,2}|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|doze|quinze|vinte|meia duzia|uma duzia)'
_SEPARA = re.compile(r'\s*(?:,|;|\.|\+|\be\b|\bmas\b|\bso que\b|\bporem\b)\s*')
_PESSOAS_SO = re.compile(r'^(?:agora\s+)?(?:somos|seremos|vamos ser|estamos em|em|pra|para|com|sao)\s+(?:mais\s+)?\d+'
                         r'(?:\s+(?:pessoas?|gente|amig\w+))?$|^\d+\s+(?:pessoas?|gente|amig\w+)$|^(?:eu e\s+)?mais\s+\d+'
                         r'\s+(?:pessoas?|amig\w+)$')
_TIRA = re.compile(rf'^(?:sem|tira|tirar|tire|remove|remover|retira|retirar|some com|fora|corta|cortar|nao quero|'
                   rf'nao precisa(?: de)?|dispensa|nenhum|nenhuma|zero|cancela|exclui)\s+{_ARTIGOS}(.+?)(?:\s+nao)?$')
_TIRA_FIM = re.compile(rf'^{_ARTIGOS}(.+?)\s+(?:nao|fora|nao quero|pode tirar|tira)$')
_TROCA = re.compile(rf'^(?:(?:troca|trocar|troque|muda|mudar|mude|substitui|substituir|substitua|coloca|poe|bota)\s+)?'
                    rf'{_ARTIGOS}(.+?)\s+(?:por|pra|para|pelo|pela|pelos|pelas)\s+{_ARTIGOS}(.+)$')
_TROCA_INVERSA = re.compile(rf'^(?:(?:quero|poe|coloca|bota|manda)\s+)?{_ARTIGOS}(.+?)\s+(?:em vez|no lugar|ao inves)\s+'
                            rf'(?:de|do|da|dos|das)\s+{_ARTIGOS}(.+)$')
_BARATO = re.compile(r'barat|em conta|\bcaro\b|economi|reduz\w* o (?:preco|valor|total)|baix\w* o (?:preco|valor|total)|'
                     r'gast\w* menos|menos dinheiro|mais acessivel')
_MAIS = re.compile(rf'^(?:(?:poe|coloca|bota|adiciona|acrescenta|inclui|quero|manda|coloque|adicione|traz)\s+)?'
                   rf'(mais|menos)\s+(?:{_NUM}\s+)?{_ARTIGOS}(.+)$')
_QTD = re.compile(rf'^(?:(?:so|deixa|deixar|quero|coloca|poe|bota|manda|apenas|fica|ficam|faz|fazer)\s+)?{_NUM}\s+'
                  rf'{_ARTIGOS}(.+?)(?:\s+(?:so|apenas|no total|basta|ta bom|entao))?$')
_POE = re.compile(rf'^(?:poe|coloca|colocar|bota|botar|adiciona|adicionar|acrescenta|acrescentar|inclui|incluir|quero|'
                  rf'queria|manda|com|traz|traga|junta|juntar|add|vem com|vem)\s+{_ARTIGOS}(.+?)'
                  rf'(?:\s+(?:tambem|junto|ai|pf|por favor|pra gente|pra mim))?$')
_NADA = re.compile(r'^(?:(?:o|a|os|as|esse|essa|este|esta|mesmo|mesma|mesmos|tudo|igual|resto|kit|pedido|isso|assim|ai|'
                   r'dai|entao|ok|beleza|por favor|pf|ne|pra mim|pra gente|nada|mais nada|so isso)\s*)*$')
# palavra que mostra que o alvo não é um produto ("2 são vegetarianos", "um não come carne")
_NAO_PRODUTO = re.compile(r'\b(sao|e|esta|estao|come|comem|nao|quer|querem|gosta|gostam|pode|podem|tem|vai|vao|ser|somos|'
                          r'alergic\w*|alergia|vegetarian\w*|vegan\w*|crianc\w*|idos\w*|lactose|gluten|diet\w*|pessoa\w*|'
                          r'gente|amig\w*|adult\w*|picante|apimentad\w*|bem passad\w*|mal passad\w*|ao ponto|quente|'
                          r'gelad\w*|rapido|demora|entrega|hoje|amanha|agora|depois)\b')
# "sem cebola" num kit de restaurante é como quer o lanche (vai pro modelo); no mercado, cebola é produto
# (18/10 08h49: "adiciona um tomate e uma cebola" num churrasco tem que virar tomate e cebola no kit)
_INGREDIENTE = re.compile(r'\b(cebola|tomate|alface|picles|maionese|ketchup|mostarda|pimenta|ovo|milho|azeitona|catupiry|'
                          r'cheddar|molho|acucar|oleo|sal|queijo|bacon|presunto|calabresa|oregano|rucula|cebolinha|salsinha|'
                          r'tempero|gelo)\b')
_CORTESIA = re.compile(r'\b(por favor|por gentileza|pfv|pf|obrigad[oa]|valeu|please|ai|dai|entao|ok|beleza|ne|tipo)\b')
_BEBIDA_PALAVRA = re.compile(r'\b(refri\w*|bebid\w*|refrigerant\w*)\b')
_DOCE = re.compile(r'\b(sobremesa\w*|doce\w*|pudim|bolo|sorvete|mousse|milkshake|brownie|petit|torta|chocolate)\b')
_PORCAO_PALAVRA = re.compile(r'\b(porc(?:ao|oes)|acompanhamento\w*)\b')


def frases(ajuste):
    """'sem refri e mais batata, por favor' -> ['sem refri', 'mais batata'] (normalizado, sem acento nem cortesia)."""
    partes = (_CORTESIA.sub(' ', p).strip() for p in _SEPARA.split(normalizar(ajuste)) if p)
    return [' '.join(p.split()) for p in partes if p.strip()]


def ja_no_texto(termo, texto):
    """'tomate' em 'adiciona um tomate': o pedido já está no ajuste (não vira um 2º "põe tomate")."""
    raizes = relevancia._raizes(termo)
    return bool(raizes) and all(r in normalizar(texto) for r in raizes)


def _n(texto):
    return numero_em(texto) if texto else None


def _produto(alvo):
    """O alvo parece um produto ('guaraná', 'batata frita', 'pão de alho'), não uma restrição ('sao vegetarianos')?"""
    palavras = [p for p in alvo.split() if p not in ('de', 'da', 'do', 'com', 'e')]
    return 1 <= len(palavras) <= 4 and not _NAO_PRODUTO.search(alvo) and not any(p.isdigit() for p in palavras)


def ler(ajuste, cands, kit, tema):
    """O ajuste -> operações, na ordem. kit: [(índice do candidato, qtd)] da tela. Cada operação:
    {'op': tira|troca|mais|menos|qtd|poe|barato|pessoas|nada|livre, ...}."""
    ops = []
    for frase in frases(ajuste):
        if _PESSOAS_SO.match(frase):
            ops.append({'op': 'pessoas'})
            continue
        m = _TIRA.match(frase) or _TIRA_FIM.match(frase)
        if m:
            alvo = m.group(1)
            if _NADA.match(alvo):
                ops.append({'op': 'nada'})
            elif _cita_alguem(alvo, kit, cands, tema):
                ops.append({'op': 'tira', 'alvo': alvo})
            elif _INGREDIENTE.search(alvo) and (tema.get('tipo_loja') or 'RESTAURANTE') != 'MERCADO' or not _produto(alvo):
                ops.append({'op': 'livre', 'texto': frase})  # "sem cebola" no lanche: como quer o lanche, não linha
            else:
                ops.append({'op': 'tira', 'alvo': alvo})
            continue
        m = _TROCA.match(frase)
        if m and (_cita_alguem(m.group(1), kit, cands, tema) or (_produto(m.group(1)) and _produto(m.group(2)))):
            ops.append({'op': 'troca', 'de': m.group(1), 'por': m.group(2)})
            continue
        m = _TROCA_INVERSA.match(frase)
        if m and (_cita_alguem(m.group(2), kit, cands, tema) or (_produto(m.group(1)) and _produto(m.group(2)))):
            ops.append({'op': 'troca', 'de': m.group(2), 'por': m.group(1)})
            continue
        if _BARATO.search(frase):
            ops.append({'op': 'barato'})
            continue
        m = _MAIS.match(frase)
        if m and _produto(m.group(3)):
            ops.append({'op': m.group(1), 'alvo': m.group(3), 'n': _n(m.group(2)) or 1})
            continue
        m = _QTD.match(frase)
        if m and _produto(m.group(2)) and _n(m.group(1)):
            ops.append({'op': 'qtd', 'alvo': m.group(2), 'n': _n(m.group(1))})
            continue
        m = _POE.match(frase)
        if m:
            alvo = m.group(1)
            if _NADA.match(alvo):
                ops.append({'op': 'nada'})
                continue
            if _produto(alvo):
                mq = re.match(rf'^{_NUM}\s+(.+)$', alvo)  # "poe 2 guaranas"
                ops.append({'op': 'poe', 'alvo': mq.group(2) if mq else alvo, 'n': _n(mq.group(1)) if mq else None})
                continue
        if _NADA.match(frase):
            ops.append({'op': 'nada'})
        elif _produto(frase) and _achar(frase, cands, {n for n, _ in kit}, tema) is not None:
            ops.append({'op': 'poe', 'alvo': frase, 'n': None})  # "batata" seco com a batata na lista da loja
        else:
            ops.append({'op': 'livre', 'texto': frase})
    return ops


# --------------------------------------------------------------------------- quem o alvo cita

def _cita(alvo, cand, tema):
    """'coca' cita "Coca-Cola 2 litros"; 'refri' cita a Coca e o Guaraná (sinônimos do filtro de relevância);
    'bebida' cita qualquer bebida; 'lanche'/'pizza' citam o principal."""
    a = normalizar(alvo)
    if not a:
        return False
    nome = normalizar(cand['nome'] + ' ' + (cand.get('termo') or ''))
    if relevancia._por_palavra([{'nome': nome}], a):
        return True
    if _BEBIDA_PALAVRA.search(a) and (cand['papel'] == 'bebida' or grupo.BEBIDA.search(nome)):
        return True
    if _PORCAO_PALAVRA.search(a) and grupo.PORCAO.search(nome):
        return True
    if _DOCE.search(a) and _DOCE.search(nome):
        return True
    if cand['papel'] == 'principal' and (relevancia._por_palavra([{'nome': normalizar(tema['termo'])}], a)
                                        or a in ('comida', 'principal', 'prato', 'lanche', 'lanches')):
        return True
    return False


def _cita_alguem(alvo, kit, cands, tema):
    return any(_cita(alvo, cands[n], tema) for n, _ in kit)


def _citadas(alvo, kit, cands, tema):
    return [n for n, _ in kit if _cita(alvo, cands[n], tema)]


def _achar(alvo, cands, fora, tema):
    """Um candidato da loja (fora do kit) que é o alvo; bebida pra grupo prefere a de 2 litros."""
    achados = [i for i, c in enumerate(cands) if i not in fora and _cita(alvo, c, tema) and c['papel'] != 'principal']
    if not achados:
        return None
    grandes = [i for i in achados if grupo.DOIS_LITROS.search(normalizar(cands[i]['nome']))]
    return (grandes or achados)[0]


def _nome(cand):
    base = cand.get('base') or cand['nome']
    return base if len(base) <= 40 else base[:39].rstrip() + '…'


def _nomes(indices, cands):
    return ' e '.join(_nome(cands[n]) for n in indices)


# --------------------------------------------------------------------------- aplicar

def aplicar(ops, kit, cands, pessoas, tema, loja):
    """Aplica as operações no kit [(índice, qtd)]. loja: objeto com buscar(termo) -> [índices de candidatos
    novos], reabrir(n, termo) -> bool (a opção do item, "Refrigerante 2 L (Guaraná)") e baratear(kit) ->
    (kit, frase). Devolve (kit, frases do que fez, o que não achou na loja)."""
    kit, frases, faltou = list(kit), [], []
    principais = lambda k: [n for n, _ in k if cands[n]['papel'] == 'principal']  # noqa: E731
    for op in ops:
        tipo = op['op']
        if tipo in ('livre', 'nada', 'pessoas'):
            continue
        if tipo == 'tira':
            alvo = _citadas(op['alvo'], kit, cands, tema)
            if not alvo:
                frases.append(f'não tinha {op["alvo"]} no kit')
            elif set(principais(kit)) <= set(alvo):
                frases.append(f'o kit precisa de {tema["termo"]}, deixei')
            else:
                kit = [(n, q) for n, q in kit if n not in alvo]
                frases.append(f'tirei {_nomes(alvo, cands)}')
        elif tipo == 'troca':
            de = _citadas(op['de'], kit, cands, tema)
            if not de:
                frases.append(f'não tinha {op["de"]} no kit')
                continue
            novo = _achar(op['por'], cands, {n for n, _ in kit}, tema)
            if novo is None:
                novo = _melhor(op['por'], loja.buscar(op['por']), cands)
            if novo is None and loja.reabrir(de[0], op['por']):
                frases.append(f'troquei por {_nome(cands[de[0]])}')
                continue
            if novo is None:
                faltou.append(op['por'])
                frases.append(f'não achei {op["por"]} nessa loja, deixei {_nomes(de, cands)}')
                continue
            tinha = sum(q for n, q in kit if n in de)  # lata por lata; 2 litros no lugar de lata vai por cabeça
            qtd = _quantas(cands[novo], pessoas) if grupo._escala(cands[novo], tema) else tinha
            kit = [(n, q) for n, q in kit if n not in de] + [(novo, qtd)]
            frases.append(f'troquei {_nomes(de, cands)} por {_nome(cands[novo])}')
        elif tipo in ('mais', 'menos'):
            alvo = _citadas(op['alvo'], kit, cands, tema)
            if alvo:
                n = alvo[0]
                qtd = dict(kit)[n] + (op['n'] if tipo == 'mais' else -op['n'])
                if qtd <= 0 and n in principais(kit) and len(principais(kit)) == 1:
                    frases.append(f'o kit precisa de {tema["termo"]}, deixei 1')
                    qtd = 1
                kit = [(x, qtd if x == n else q) for x, q in kit if x != n or qtd > 0]
                frases.append((f'pus mais {op["n"]} ' if tipo == 'mais' else f'tirei {op["n"]} ') + _nome(cands[n]))
            elif tipo == 'mais':
                kit, frase, nao_achou = _por(op['alvo'], op['n'], kit, cands, pessoas, tema, loja)
                frases.append(frase)
                faltou += nao_achou
            else:
                frases.append(f'não tinha {op["alvo"]} no kit')
        elif tipo == 'qtd':
            alvo = _citadas(op['alvo'], kit, cands, tema)
            if alvo:
                n = alvo[0]
                kit = [(x, op['n'] if x == n else q) for x, q in kit]
                frases.append(f'deixei {op["n"]}x {_nome(cands[n])}')
            else:
                kit, frase, nao_achou = _por(op['alvo'], op['n'], kit, cands, pessoas, tema, loja)
                frases.append(frase)
                faltou += nao_achou
        elif tipo == 'poe':
            if _citadas(op['alvo'], kit, cands, tema) and not op.get('n'):
                n = _citadas(op['alvo'], kit, cands, tema)[0]  # "põe batata" com batata no kit = mais uma
                kit = [(x, q + 1 if x == n else q) for x, q in kit]
                frases.append(f'pus mais 1 {_nome(cands[n])}')
                continue
            kit, frase, nao_achou = _por(op['alvo'], op.get('n'), kit, cands, pessoas, tema, loja)
            frases.append(frase)
            faltou += nao_achou
        elif tipo == 'barato':
            kit, frase = loja.baratear(kit)
            frases.append(frase)
    return kit[:grupo.MAX_LINHAS], frases, faltou


def _melhor(alvo, indices, cands):
    """Dos achados na busca, o que É o alvo: 'tomate' prefere "Tomate kg" a "Molho de tomate"."""
    if not indices:
        return None
    raiz = relevancia._raizes(alvo)[:1]
    return next((i for i in indices if raiz and normalizar(cands[i]['nome']).startswith(raiz[0])), indices[0])


def _por(alvo, n, kit, cands, pessoas, tema, loja):
    """Põe o alvo no kit: da lista da loja, senão de uma busca nela. Devolve (kit, frase, [não achado])."""
    novo = _achar(alvo, cands, {x for x, _ in kit}, tema)
    if novo is None:
        novo = _melhor(alvo, loja.buscar(alvo), cands)
    if novo is None:
        return kit, f'não achei {alvo} nessa loja', [alvo]
    qtd = _quantas(cands[novo], pessoas, n)
    return kit + [(novo, qtd)], f'pus {qtd}x {_nome(cands[novo])}', []


def _quantas(cand, pessoas, pedida=None):
    """Quantos de um item novo: o número dito; senão bebida por cabeça (2 L pra cada 4), porção pra cada 3,
    carvão pra cada 6, 1 do resto."""
    if pedida:
        return min(int(pedida), 50)
    return grupo.quantidade_de(cand, pessoas)


def explicar(frases):
    """['tirei Coca-Cola 2 litros', 'pus mais 1 Batata frita'] -> 'Tirei Coca-Cola 2 litros e pus mais 1 Batata frita 👍'."""
    frases = [f for f in frases if f]
    if not frases:
        return None
    texto = frases[0] if len(frases) == 1 else ', '.join(frases[:-1]) + ' e ' + frases[-1]
    texto = texto[0].upper() + texto[1:]
    fez_algo = any(not f.startswith(('não ', 'o kit precisa', 'esse já é')) for f in frases)
    return (texto if len(texto) <= 180 else texto[:179].rstrip() + '…') + (' 👍' if fez_algo else ' 🙂')


# --------------------------------------------------------------------------- o modelo só mexe no que citou

# o ajuste livre é sobre o principal? ("2 são vegetarianos", "sem cebola", "um não come carne"): só aí o modelo
# pode mexer nos lanches; "quero algo mais gostoso" não troca nada
_SOBRE_PRINCIPAL = re.compile(r'vegetarian|vegan|vegg|alerg|lactose|gluten|crianc|idos|picante|apimentad|'
                              r'\b(?:sem|tira\w*|nao (?:come|comem|quer|querem|gosta|gostam))\b')


def conferir(escolha, atual, cands, texto, tema):
    """Depois do modelo (ajuste livre): linha que não foi citada fica exatamente como estava e linha nova que
    não foi citada não entra. Os principais só mudam se o ajuste é sobre eles ("2 são vegetarianos", "sem
    cebola"). Se ele tirou todos os principais, fica o kit de antes."""
    citadas = {n for n in set([x for x, _ in atual] + [x for x, _ in escolha]) if _cita_texto(texto, cands[n], tema)}
    principal_livre = any(cands[n]['papel'] == 'principal' for n in citadas) or bool(_SOBRE_PRINCIPAL.search(normalizar(texto)))
    pode_mudar = lambda n: n in citadas or (principal_livre and cands[n]['papel'] == 'principal')  # noqa: E731
    novo = dict(escolha)
    saida = []
    for n, q in atual:
        if pode_mudar(n):
            if n in novo:
                saida.append((n, novo[n]))
        else:
            saida.append((n, q))
    for n, q in escolha:
        if n not in dict(atual) and pode_mudar(n):
            saida.append((n, q))
    if not any(cands[n]['papel'] == 'principal' for n, _ in saida):
        return list(atual)
    return saida


def _cita_texto(texto, cand, tema):
    return any(_cita(p, cand, tema) for p in re.findall(r'[a-z]{3,}', normalizar(texto)))
