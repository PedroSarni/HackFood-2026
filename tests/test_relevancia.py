"""Filtro de relevância: a busca do iFood casa com o nome da loja (bug real da coxinha, 17/10)."""
from src.bot import relevancia as R

OFERTAS = [
    {'item_id': 'a', 'nome': 'Coxinha de Camarão com Requeijão', 'loja': 'Coxinhas Douradas'},
    {'item_id': 'b', 'nome': 'Espeto de Frango Empanado', 'loja': 'Coxinhas Dona Nita'},
    {'item_id': 'c', 'nome': 'Mini Coxinhas (10 un)', 'loja': 'Coxinhas Dona Nita'},
]


def test_gemini_tira_o_que_so_tem_coxinha_no_nome_da_loja_e_ordena():
    vistos = []

    def llm(s, partes, e):
        vistos.append(partes[0][1])
        return {'manter': [2, 0]}, 'fake', 0
    r = R.filtrar(llm, OFERTAS, {'termo': 'coxinha'})
    assert [o['item_id'] for o in r] == ['c', 'a']
    assert '(loja: Coxinhas Dona Nita)' in vistos[0] and 'A pessoa pediu: coxinha' in vistos[0]


def test_gemini_fora_cai_pro_filtro_por_palavra_no_nome_do_item():
    def llm(*a):
        raise RuntimeError('fora')
    assert [o['item_id'] for o in R.filtrar(llm, OFERTAS, {'termo': 'coxinha'})] == ['a', 'c']


def test_sinonimo_sem_gemini_nao_zera_a_lista():
    def llm(*a):
        raise RuntimeError('fora')
    assert R.filtrar(llm, OFERTAS, {'termo': 'salgado'}) == OFERTAS  # melhor algo que nada


def test_gemini_diz_que_nada_serve_vira_nao_achei():
    assert R.filtrar(lambda *a: ({'manter': []}, 'f', 0), OFERTAS, {'termo': 'pastel'}) == []


def test_indice_invalido_do_gemini_e_ignorado():
    r = R.filtrar(lambda *a: ({'manter': [9, 1, 1, -1]}, 'f', 0), OFERTAS, {'termo': 'espeto'})
    assert [o['item_id'] for o in r] == ['b']
