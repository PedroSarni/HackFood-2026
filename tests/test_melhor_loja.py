"""A loja da lista: a que tem TUDO e sai mais em conta (src/bot/melhor_loja.py), a troca de loja no meio
levando o carrinho, e o kit que não cai em pizzaria sem a Coca que pediram (17/10, 23h22)."""
import pytest

from src.bot import grupo, melhor_loja, relevancia
from src.bot.interpretar import regra_rapida
from src.shared.mcp_fake import _uid
from tests.fakes import Mundo
from tests.test_fluxo import endereco_pronto

END = {'lat': -22.0087, 'lng': -47.8909, 'id': 'x'}
CENTRAL, BOM_PRECO, FORNO = _uid('loja', 'm2'), _uid('loja', 'm1'), _uid('loja', 'r4')


@pytest.fixture(autouse=True)
def por_palavra(monkeypatch):
    """O fake do Gemini mantém tudo ("água sanitária" levaria a água mineral junto): aqui vale a palavra,
    como o filtro de relevância faz quando o Gemini cai."""
    monkeypatch.setattr(relevancia, 'filtrar',
                        lambda llm, ofertas, pedido: relevancia._por_palavra(ofertas, pedido['termo']))
    monkeypatch.setattr(relevancia, 'filtrar_varios',
                        lambda llm, pares: [relevancia._por_palavra(o, p['termo']) for o, p in pares])


def _item(termo, tipo='MERCADO', qtd=None):
    return {'termo': termo, 'busca': termo, 'quantidade': qtd, 'tipo_loja': tipo, 'observacao': None}


def _plano(*itens):
    m = Mundo()
    return melhor_loja.planejar(m.ctx.ifood(m.wa), m.llm, END, list(itens))


def _lista(m, *itens):
    m.llm.resposta = {'acao': 'comprar', 'itens': list(itens)}
    m.enviar(', '.join(i['termo'] for i in itens))
    m.llm.resposta = None


def _tocar_loja(m, nome):
    for _tipo, d in reversed(m.wpp.saida):
        opcoes = list(d.get('botoes') or []) + [(i, t) for i, t, _ in d.get('linhas') or []]
        for bid, titulo in opcoes:
            if bid.startswith('loja:') and nome in titulo:
                return m.enviar(('botao', bid))
    raise AssertionError(f'sem botão da loja {nome}')


# --------------------------------------------------------------------------- o plano


def test_lista_vai_pra_loja_que_tem_tudo_e_sai_mais_em_conta():
    plano = _plano(_item('detergente'), _item('agua sanitaria'), _item('cebola'))
    melhor = plano['lojas'][0]
    # Central: 2,29 + 6,99 + 5,49 e entrega grátis; Bom Preço: 2,49 + 5,49 + 5,99 + 4,99 de entrega
    assert (melhor['loja_id'], melhor['tem'], melhor['custo']) == (CENTRAL, [0, 1, 2], 14.77)
    assert plano['lojas'][1]['loja_id'] == BOM_PRECO and plano['lojas'][1]['custo'] == 18.96


def test_quantidade_pedida_entra_na_conta():
    plano = _plano(_item('detergente', qtd=10), _item('cebola'))
    assert plano['lojas'][0]['custo'] == round(2.29 * 10 + 5.49, 2)


def test_loja_com_tudo_ganha_da_mais_barata_que_nao_tem_tudo():
    plano = _plano(_item('bolo de fuba'), _item('leite'))
    assert plano['lojas'][0]['loja'] == 'Padaria Pão Quente'  # só ela tem bolo de fubá, mesmo sendo mais cara
    assert plano['lojas'][0]['tem'] == [0, 1]


def test_item_que_nenhuma_loja_tem_fica_de_fora_e_ganha_a_que_tem_mais():
    plano = _plano(_item('detergente'), _item('caviar'), _item('cebola'))
    assert plano['lojas'][0]['loja_id'] == CENTRAL and plano['lojas'][0]['tem'] == [0, 2]


def test_loja_que_a_busca_geral_escondeu_e_conferida_so_nela(monkeypatch):
    m = Mundo()
    api = m.ctx.ifood(m.wa)
    buscar = api.buscar

    def sem_central_na_geral(termo, endereco, tipo, loja_id=None, pagina=None):
        ofertas, prox = buscar(termo, endereco, tipo, loja_id=loja_id, pagina=pagina)
        if loja_id is None and 'cebola' in termo:  # a 1ª página da busca geral não mostrou a cebola dele
            ofertas = [o for o in ofertas if o['loja_id'] != CENTRAL]
        return ofertas, prox
    monkeypatch.setattr(api, 'buscar', sem_central_na_geral)
    plano = melhor_loja.planejar(api, m.llm, END, [_item('detergente'), _item('agua sanitaria'), _item('cebola')])
    assert plano['lojas'][0]['loja_id'] == CENTRAL and plano['lojas'][0]['tem'] == [0, 1, 2]


def test_lista_inteira_gasta_uma_chamada_so_do_gemini(monkeypatch):
    monkeypatch.undo()  # aqui vale o filtro de verdade, com o Gemini falso contando as chamadas
    m = Mundo()
    antes = m.llm.chamadas
    plano = melhor_loja.planejar(m.ctx.ifood(m.wa), m.llm, END,
                                 [_item('detergente'), _item('cebola'), _item('leite'), _item('cafe')])
    assert m.llm.chamadas - antes == 1 and plano['lojas'][0]['tem'] == [0, 1, 2, 3]


def test_filtro_em_lote_devolve_cada_lista_no_lugar_e_sem_gemini_vai_por_palavra(monkeypatch):
    monkeypatch.undo()
    agua = [{'nome': 'Água mineral sem gás'}, {'nome': 'Água sanitária'}]
    tomate = [{'nome': 'Molho de tomate'}, {'nome': 'Tomate'}]
    pares = [(agua, {'termo': 'agua sanitaria'}), ([], {'termo': 'caviar'}), (tomate, {'termo': 'tomate'})]

    def gemini(sistema, partes, esquema):
        assert 'Lista 0.' in partes[0][1] and 'Lista 2.' in partes[0][1] and 'Lista 1.' not in partes[0][1]
        return {'listas': [{'lista': 2, 'manter': [1]}, {'lista': 0, 'manter': [1]}]}, 'fake', 0.1
    assert relevancia.filtrar_varios(gemini, pares) == [[agua[1]], [], [tomate[1]]]

    def fora(sistema, partes, esquema):
        raise RuntimeError('429 cota')
    assert relevancia.filtrar_varios(fora, pares)[0] == [agua[1]]   # por palavra: "agua" e "sanit"


def test_mais_parecida_acha_o_mesmo_produto_pelo_nome():
    ofertas = [{'nome': 'Arroz integral 1kg'}, {'nome': 'Arroz branco tipo 1 5kg'}, {'nome': 'Arroz parboilizado'}]
    assert melhor_loja.mais_parecida(ofertas, 'Arroz branco tipo 1')['nome'] == 'Arroz branco tipo 1 5kg'


def test_regra_rapida_troca_de_loja_sem_confundir_com_produto():
    for frase in ('troca de mercado', 'quero outro mercado', 'tem outra pizzaria?', 'muda de loja'):
        assert regra_rapida(frase) == {'acao': 'trocar_loja'}, frase
    for frase in ('quero outra pizza', 'manda pra outro endereço'):
        assert (regra_rapida(frase) or {}).get('acao') != 'trocar_loja', frase


# --------------------------------------------------------------------------- no fluxo


def test_lista_anuncia_a_loja_com_tudo_e_mostra_os_cards_dela():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    _lista(m, _item('detergente'), _item('agua sanitaria'), _item('cebola'))
    texto = ' '.join(m.wpp.textos())
    assert 'Supermercado Central* tem tudo' in texto and 'R$ 14,77' in texto
    est = m.estado()
    lst = est['listas'][est['lista_atual']]
    assert lst['termo'] == 'detergente' and {o['loja_id'] for o in lst['ofertas']} == {CENTRAL}
    assert 'loja' in m.wpp.todos_ids()                        # Trocar de loja nos cards


def test_trocar_de_loja_no_meio_leva_o_carrinho_e_segue_a_lista_na_loja_nova():
    m = Mundo()
    endereco_pronto(m)
    _lista(m, _item('detergente'), _item('agua sanitaria'), _item('cebola'))
    m.tocar('pick:')                                          # detergente do Central
    m.tocar('qtd:2')
    assert m.estado()['carrinho']['loja_id'] == CENTRAL
    m.tocar('loja')                                           # Trocar de loja, com a água sanitária na tela
    _tocar_loja(m, 'Bom Preço')
    est = m.estado()
    assert est['carrinho']['loja_id'] == BOM_PRECO
    assert [(i['nome'], i['qtd']) for i in est['carrinho']['itens']] == [('Detergente', 2)]
    lst = est['listas'][est['lista_atual']]
    assert lst['termo'] == 'agua sanitaria' and {o['loja_id'] for o in lst['ofertas']} == {BOM_PRECO}
    assert 'veio junto' in ' '.join(m.wpp.textos())


def test_continuar_aqui_volta_pros_cards_sem_trocar():
    m = Mundo()
    endereco_pronto(m)
    _lista(m, _item('detergente'), _item('agua sanitaria'), _item('cebola'))
    m.tocar('loja')
    m.tocar('loja_fica')
    est = m.estado()
    assert est['fase'] == 'escolhendo' and est['plano']['escolhida'] == CENTRAL


def test_item_que_a_loja_da_lista_nao_tem_vai_pro_fim_e_oferece_trocar_de_loja():
    m = Mundo()
    endereco_pronto(m)
    _lista(m, _item('bolo de fuba'), _item('detergente'), _item('cebola'))
    assert 'Fica de fora: *bolo de fuba*' in ' '.join(m.wpp.textos())
    est = m.estado()
    assert est['listas'][est['lista_atual']]['termo'] == 'detergente'   # o que a loja tem vem primeiro
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.tocar('pick:')
    m.tocar('qtd:1')
    assert m.wpp.textos()[-1].startswith('Não achei *bolo de fuba* no Supermercado Central')
    assert {'pular', 'loja'} <= set(m.wpp.todos_ids()[-3:])


def test_pizza_e_uma_coca_vao_pra_pizzaria_que_tem_as_duas():
    m = Mundo()
    endereco_pronto(m)
    _lista(m, _item('pizza', 'RESTAURANTE'), _item('coca-cola', 'RESTAURANTE'))
    assert m.estado()['plano']['escolhida'] == FORNO          # tem pizza e Coca, e sai mais em conta
    assert 'Pizzaria Forno a Lenha* tem tudo' in ' '.join(m.wpp.textos())


def test_kit_de_pizza_com_coca_escolhe_a_pizzaria_com_coca():
    m = Mundo()
    api = m.ctx.ifood(m.wa)
    fontes = grupo.fontes(api, m.llm, END, _item('pizza', 'RESTAURANTE'))
    lista = melhor_loja.com_tudo_primeiro(api, m.llm, END, fontes, [_item('coca-cola', 'RESTAURANTE')])
    assert lista[0]['loja_id'] == FORNO and lista[0]['tem_tudo']


def test_kit_sem_nada_junto_vai_pela_conta_sem_buscar_a_mais():
    m = Mundo()
    api = m.ctx.ifood(m.wa)
    fontes = grupo.fontes(api, m.llm, END, _item('pizza', 'RESTAURANTE'))
    antes = len(m.mcp.chamadas_de('searchOffers'))
    lista = melhor_loja.com_tudo_primeiro(api, m.llm, END, fontes, [])
    assert lista[0]['loja_id'] == FORNO and len(m.mcp.chamadas_de('searchOffers')) == antes


def test_kit_pra_galera_com_coca_nao_avisa_que_faltou_coca():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar('pizza pra 10 pessoas com coca')
    texto = ' '.join(m.wpp.textos())
    assert 'Não achei' not in texto and 'Coca-Cola' in texto and 'Forno a Lenha' in texto
