"""O Beto consistente (18/10 08h, claim bot-kit-consistency): o principal é o prato de verdade, a receita garante
o que não pode faltar e os ajustes do kit são lidos e aplicados pelo código em cima do kit da tela."""
from src.bot import grupo, kit_ajuste
from tests.fakes import Mundo
from tests.test_fluxo import endereco_pronto


def pronto(m):
    endereco_pronto(m)
    m.wpp.limpar()
    return m


def kit(m):
    return m.estado()['kit']


def linhas(m, papel=None):
    return [lin for lin in kit(m)['linhas'] if papel is None or lin['papel'] == papel]


def nomes(m):
    return ' | '.join(lin['nome'] for lin in kit(m)['linhas'])


def lanche_5():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    assert m.estado()['fase'] == 'kit'
    return m


# --- o principal é o prato de verdade ----------------------------------------------------

def test_e_o_prato_pela_receita():
    pizza = {'termo': 'pizza'}
    assert grupo.e_o_prato('Pizza de calabresa (Grande (8 fatias))', pizza) is True
    assert grupo.e_o_prato('Omelete de pizza', pizza) is False
    assert grupo.e_o_prato('Pastel de pizza', pizza) is False
    assert grupo.e_o_prato('Pão de alho', pizza) is False
    assert grupo.e_o_prato('Coca-Cola 2 litros', pizza) is False
    assert grupo.e_o_prato('Calabresa G', pizza) is None  # a pizzaria que não escreve "pizza": fica com o modelo
    lanche = {'termo': 'hambúrguer'}
    assert grupo.e_o_prato('X-Bacon', lanche) is True
    assert grupo.e_o_prato('Combo X-Burger + batata', lanche) is True
    assert grupo.e_o_prato('Pão de hambúrguer', lanche) is False
    assert grupo.e_o_prato('Batata frita (porção)', lanche) is False
    assert grupo.e_o_prato('Molho especial da casa', lanche) is False
    churrasco = {'termo': 'carne pra churrasco', 'tipo_loja': 'MERCADO'}
    for nome in ('Picanha bovina', 'Linguiça toscana', 'Contrafilé em bife', 'Coxa e sobrecoxa'):
        assert grupo.e_o_prato(nome, churrasco) is True, nome
    for nome in ('Carvão', 'Carne moída (patinho)', 'Carne de panela (acém)', 'Sal grosso para churrasco',
                 'Tempero para churrasco', 'Pão de alho', 'Queijo coalho', 'Cerveja pilsen lata'):
        assert grupo.e_o_prato(nome, churrasco) is False, nome
    assert grupo.e_o_prato('Molho para yakisoba', {'termo': 'yakisoba'}) is False  # sem receita: o prato como sabor
    assert grupo.e_o_prato('Yakisoba de frango', {'termo': 'yakisoba'}) is None


def test_quantas_principais_pela_receita():
    assert grupo.quantas_principais({'termo': 'pizza'}, 5, {'nome': 'Pizza de calabresa (Grande (8 fatias))'}) == 2
    assert grupo.quantas_principais({'termo': 'pizza'}, 11, {'nome': 'Pizza (Grande (8 fatias))'}) == 5
    assert grupo.quantas_principais({'termo': 'esfiha'}, 4, {'nome': 'Esfiha de carne'}) == 12
    assert grupo.quantas_principais({'termo': 'hambúrguer'}, 5, {'nome': 'X-Burger'}) == 5
    assert grupo.quantas_principais({'termo': 'carne pra churrasco'}, 10, {'nome': 'Picanha bovina'}) == 5
    assert grupo.quantas_principais({'termo': 'carne pra churrasco'}, 10, {'nome': 'Linguiça toscana 500 g'}) == 8
    assert grupo.quantas_principais({'termo': 'sushi'}, 4, {'nome': 'Combinado 30 peças'}) == 2
    assert grupo.quantas_principais({'termo': 'yakisoba'}, 3, {'nome': 'Yakisoba de frango'}) == 3


def test_pizza_pra_5_nao_vira_omelete_da_padaria_mais_barata():
    # 18/10 07h44: "pizzada com mais 4 amigos" virou 5x Omelete de Pizza da Padaria Santa Fé (R$ 18, a mais barata)
    m = pronto(Mundo())
    m.enviar('pizza pra 5 pessoas dividindo')
    k = kit(m)
    assert k['loja'].startswith('Pizzaria') and 'Omelete' not in nomes(m)
    assert all('Pizza' in lin['nome'] for lin in linhas(m, 'principal'))
    assert not any(f['loja'] == 'Padaria Santa Fé' for f in k['fontes'])  # nem no "Outra loja"


def test_modelo_dizendo_que_a_loja_nao_tem_o_prato_pula_pra_proxima():
    m = pronto(Mundo())
    vistas = []
    original = m.llm.__call__

    def modelo(sistema, partes, esquema, **kw):
        if 'falta_o_prato' in esquema['properties'] and not vistas:
            vistas.append(partes[0][1])
            return {'itens': [], 'explicacao': 'não tem pizza aqui', 'falta_o_prato': True}, 'fake', 0.01
        return original(sistema, partes, esquema, **kw)
    m.ctx._gerar_json = modelo
    m.enviar('pizza pra 5 pessoas dividindo')
    k = kit(m)
    assert vistas and k['loja'].startswith('Pizzaria') and len(k['vistas']) == 2  # a 1ª foi pulada
    assert all('Pizza' in lin['nome'] for lin in linhas(m, 'principal'))


def test_quantidade_absurda_do_modelo_e_refeita_na_proporcao():
    m = pronto(Mundo())
    m.llm.kit = {'itens': [{'n': 0, 'qtd': 12}, {'n': 1, 'qtd': 4}], 'explicacao': 'Muito lanche 🍔'}
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    princ = linhas(m, 'principal')
    assert sum(lin['qtd'] for lin in princ) == 5 and [lin['qtd'] for lin in princ] == [4, 1]
    assert any(lin['papel'] == 'bebida' for lin in linhas(m))  # a bebida que ele esqueceu entra


def test_churrasco_pra_10_tem_carne_carvao_e_bebida_e_nada_que_nao_e_carne():
    m = pronto(Mundo())
    m.enviar('churrasco pra 10 pessoas')
    k = kit(m)
    assert k['tema']['termo'] == 'carne pra churrasco' and k['loja'] == 'Supermercado Central'
    principais = linhas(m, 'principal')
    assert principais and all(any(c in lin['nome'] for c in ('Picanha', 'Alcatra', 'Linguiça')) for lin in principais)
    assert 3 <= sum(lin['qtd'] for lin in principais) <= 8  # ~400 g por pessoa; peça sem peso no nome serve 2
    assert any('Carvão' in lin['nome'] and lin['qtd'] == 2 for lin in k['linhas'])  # saco pra cada 6
    assert any(lin['papel'] == 'bebida' for lin in k['linhas'])
    for errado in ('moída', 'panela', 'Sal grosso', 'Tempero'):
        assert errado not in nomes(m), errado


# --- ajustes lidos pelo código -----------------------------------------------------------

def test_ler_ajuste_vira_operacoes():
    cands = [{'nome': 'X-Burger', 'base': 'X-Burger', 'papel': 'principal', 'termo': 'hambúrguer', 'unit': 22.9},
             {'nome': 'Coca-Cola 2 litros', 'base': 'Coca-Cola 2 litros', 'papel': 'bebida', 'termo': 'refrigerante',
              'unit': 12.9},
             {'nome': 'Batata frita (porção)', 'base': 'Batata frita (porção)', 'papel': 'acompanhamento',
              'termo': 'batata frita', 'unit': 14.9},
             {'nome': 'Guaraná Antarctica 2 litros', 'base': 'Guaraná Antarctica 2 litros', 'papel': 'bebida',
              'termo': 'refrigerante', 'unit': 11.9}]
    atual = [(0, 5), (1, 2), (2, 2)]
    tema = {'termo': 'hambúrguer'}

    def ops(t):
        return [(o['op'], o.get('alvo') or o.get('de') or o.get('texto')) for o in kit_ajuste.ler(t, cands, atual, tema)]
    assert ops('sem refri') == [('tira', 'refri')]
    assert ops('sem a batata e sem o refri') == [('tira', 'batata'), ('tira', 'refri')]
    assert ops('quero esse mesmo pedido so que sem a batata') == [('nada', None), ('tira', 'batata')]
    assert ops('troca a coca por guaraná') == [('troca', 'coca')]
    assert ops('guaraná em vez de coca') == [('troca', 'coca')]
    assert ops('mais batata') == [('mais', 'batata')]
    assert ops('mais 2 batatas') == [('mais', 'batatas')]
    assert ops('menos uma coca') == [('menos', 'coca')]
    assert ops('só 3 lanches') == [('qtd', 'lanches')]
    assert ops('põe cerveja') == [('poe', 'cerveja')]
    assert ops('põe uma cerveja') == [('qtd', 'cerveja')]
    assert ops('mais barato') == [('barato', None)]
    assert ops('tá muito caro') == [('barato', None)]
    assert ops('agora somos 6') == [('pessoas', None)]
    assert ops('2 são vegetarianos') == [('livre', '2 sao vegetarianos')]
    assert ops('sem cebola') == [('livre', 'sem cebola')]


def test_sem_refri_so_tira_o_refri_e_explica_e_de_novo_nao_muda_nada():
    m = lanche_5()
    antes = [(lin['item_id'], lin['qtd']) for lin in linhas(m) if lin['papel'] != 'bebida']
    m.enviar('sem refri')
    assert [(lin['item_id'], lin['qtd']) for lin in linhas(m)] == antes
    assert kit(m)['explicacao'] == 'Tirei Coca-Cola 2 litros 👍'
    m.enviar('sem refri')  # o mesmo ajuste de novo: nada muda, e diz
    assert [(lin['item_id'], lin['qtd']) for lin in linhas(m)] == antes
    assert kit(m)['explicacao'] == 'Não tinha refri no kit 🙂'


def test_troca_a_coca_por_guarana_troca_so_a_bebida():
    m = lanche_5()
    lanches = [(lin['item_id'], lin['qtd']) for lin in linhas(m, 'principal')]
    assert any('Coca' in lin['nome'] for lin in linhas(m, 'bebida'))
    m.enviar('troca a coca por guaraná')
    assert [(lin['item_id'], lin['qtd']) for lin in linhas(m, 'principal')] == lanches
    bebidas = [lin for lin in linhas(m) if 'Guaran' in lin['nome'] or 'Coca' in lin['nome']]
    assert len(bebidas) == 1 and 'Guaran' in bebidas[0]['nome'] and bebidas[0]['qtd'] == 2  # 2 litros pra cada 4
    assert kit(m)['explicacao'].startswith('Troquei Coca-Cola 2 litros por Guaran')


def test_mais_batata_e_menos_batata_mexem_so_na_batata():
    m = lanche_5()
    antes = {lin['item_id']: lin['qtd'] for lin in linhas(m)}
    batata = next(lin for lin in linhas(m) if 'Batata' in lin['nome'])
    m.enviar('mais batata')
    assert {lin['item_id']: lin['qtd'] for lin in linhas(m)} == {**antes, batata['item_id']: batata['qtd'] + 1}
    assert kit(m)['explicacao'] == 'Pus mais 1 Batata frita (porção) 👍'
    m.enviar('menos 2 batatas')
    assert {lin['item_id']: lin['qtd'] for lin in linhas(m)} == {**antes, batata['item_id']: batata['qtd'] - 1}


def test_so_2_x_burger_e_poe_suco_buscado_na_loja_e_cerveja_que_nao_tem():
    m = lanche_5()
    m.enviar('só 2 x-burger')
    assert next(lin['qtd'] for lin in linhas(m) if lin['nome'] == 'X-Burger') == 2
    m.enviar('põe suco')
    suco = next(lin for lin in linhas(m) if 'Suco' in lin['nome'])
    assert suco['qtd'] == 5 and suco['papel'] == 'pedido'  # 1 por pessoa, e o que pediram fica
    assert m.mcp.chamadas_de('searchOffers')[-1]['refinements'].get('merchantId') == kit(m)['loja_id']  # buscou NA loja
    assert kit(m)['explicacao'] == 'Pus 5x Suco natural de laranja 👍'
    m.enviar('põe cerveja')  # a lanchonete não tem
    assert not any('erveja' in lin['nome'] for lin in linhas(m)) and suco['item_id'] in {lin['item_id'] for lin in linhas(m)}
    assert 'Não achei cerveja nessa loja' in m.wpp.saida[-1][1]['texto']


def test_mais_barato_desce_um_degrau_por_vez_sem_inventar():
    m = lanche_5()
    totais = [kit(m)['total']]
    for _ in range(6):
        m.enviar('mais barato')
        totais.append(kit(m)['total'])
        assert sum(lin['qtd'] for lin in linhas(m, 'principal')) == 5  # ninguém fica sem lanche
        if totais[-1] == totais[-2]:
            break
    assert all('X-Burger' in lin['nome'] for lin in linhas(m, 'principal'))  # o mais em conta da loja
    assert not any('Batata' in lin['nome'] or lin['papel'] == 'bebida' for lin in linhas(m))
    assert totais[:-1] == sorted(totais[:-1], reverse=True) and len(set(totais[:-1])) == len(totais) - 1
    assert 'mais em conta dessa loja' in kit(m)['explicacao']


def test_agora_somos_6_refaz_as_quantidades_sem_trazer_o_refri_de_volta():
    m = lanche_5()
    m.enviar('sem refri')
    m.enviar('agora somos 6')
    k = kit(m)
    assert k['pessoas'] == 6 and sum(lin['qtd'] for lin in linhas(m, 'principal')) == 6
    assert not any(lin['papel'] == 'bebida' for lin in linhas(m))
    assert any('Batata' in lin['nome'] and lin['qtd'] == 2 for lin in linhas(m))
    assert k['explicacao'] == 'Refiz as quantidades pra 6 pessoas 👍'


def test_sem_refri_vale_na_outra_loja():
    m = lanche_5()
    m.enviar('sem refri')
    m.tocar('kit:outra')
    k = kit(m)
    assert k['loja'] == 'Burger House' and not any(lin['papel'] == 'bebida' for lin in linhas(m))
    assert k['ajustes'] == ['sem refri']


def test_coca_pedida_e_depois_tirada_nao_volta():
    m = pronto(Mundo())
    m.enviar('lanchar em 4 pessoas hamburguer com coca')
    assert any(lin['papel'] == 'pedido' for lin in linhas(m))
    m.enviar('sem coca')
    assert not any('Coca' in lin['nome'] for lin in linhas(m))
    m.enviar('agora somos 5')
    assert kit(m)['pessoas'] == 5 and not any('Coca' in lin['nome'] for lin in linhas(m))


def test_ajuste_livre_vai_pro_modelo_mas_so_os_lanches_mudam():
    m = lanche_5()
    cands = kit(m)['candidatos']
    no_kit = {lin['item_id'] for lin in linhas(m, 'principal')}
    veggie = next(i for i, c in enumerate(cands) if c['papel'] == 'principal' and 'Salada' in c['nome'])
    novo = next(i for i, c in enumerate(cands) if c['papel'] == 'principal' and c['item_id'] not in no_kit)
    lata = next(i for i, c in enumerate(cands) if c['papel'] == 'bebida' and 'lata' in c['nome'])
    bebida_antes = next(lin for lin in linhas(m, 'bebida'))
    batata_antes = next(lin for lin in linhas(m) if 'Batata' in lin['nome'])
    batata = next(i for i, c in enumerate(cands) if c['item_id'] == batata_antes['item_id'])
    # o modelo troca os lanches (pode), tira a Coca, põe 5 latas e dobra a batata (nada disso foi pedido)
    m.llm.kit = {'itens': [{'n': veggie, 'qtd': 2}, {'n': novo, 'qtd': 3}, {'n': lata, 'qtd': 5}, {'n': batata, 'qtd': 4}],
                 'explicacao': 'Dois sem carne 🥗'}
    m.enviar('2 são vegetarianos')
    assert sorted((lin['item_id'], lin['qtd']) for lin in linhas(m, 'principal')) == sorted(
        [(cands[veggie]['item_id'], 2), (cands[novo]['item_id'], 3)])
    assert any(lin['item_id'] == bebida_antes['item_id'] and lin['qtd'] == bebida_antes['qtd'] for lin in linhas(m))
    assert not any('lata' in lin['nome'] for lin in linhas(m))
    assert any(lin['item_id'] == batata_antes['item_id'] and lin['qtd'] == batata_antes['qtd'] for lin in linhas(m))
    assert kit(m)['explicacao'] == 'Dois sem carne 🥗' and kit(m)['restricoes'] == ['2 sao vegetarianos']
