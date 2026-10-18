"""Achados do QA da madrugada de 18/10: a quantidade dita fora da pergunta "quantas unidades?" (U20), o "até
agora" que somava entrega e taxas sem avisar (M2) e o pedido que só fechava com toque, nunca por áudio."""
from src.bot import interpretar
from src.bot import textos as T
from tests.fakes import Mundo
from tests.test_fluxo import endereco_pronto, pedido_ate_o_resumo

LEITE = {'termo': 'leite', 'busca': 'leite', 'quantidade': 10, 'tipo_loja': 'MERCADO'}


def _lia_diz(m, intencao):
    """Daqui em diante a Lia (interpretar) devolve `intencao`; o resto (relevância, foto...) segue o fake."""
    llm = m.llm

    def gerar(sistema, partes, esquema, **kw):
        if sistema == interpretar.SISTEMA:
            return dict(intencao), 'fake', 0.01
        return llm(sistema, partes, esquema, **kw)
    m.ctx._gerar_json = gerar


def _com_dois_paes():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:2')          # "Seu pedido até agora" + Finalizar / Quero mais coisas / Tirar um item
    return m


def test_mais_10_leites_fora_da_pergunta_de_quantidade_vai_buscar_o_leite_e_nao_finge():
    m = _com_dois_paes()
    buscas = len(m.mcp.chamadas_de('searchOffers'))
    _lia_diz(m, {'acao': 'quantidade', 'numero': 10, 'itens': [LEITE],
                 'resposta': 'Pode deixar, adicionei mais 10 leites! 🥛'})
    m.wpp.limpar()
    m.enviar('pode colocar mais 10 leites')
    assert len(m.mcp.chamadas_de('searchOffers')) > buscas           # foi atrás do leite
    assert 'adicionei' not in ' '.join(m.wpp.textos()).lower()        # e não disse que já tinha colocado


def test_mais_2_leites_nao_vira_o_segundo_botao():
    m = _com_dois_paes()
    _lia_diz(m, {'acao': 'quantidade', 'numero': 2, 'itens': [{**LEITE, 'quantidade': 2}], 'resposta': 'Já vejo! 🥛'})
    m.wpp.limpar()
    m.enviar('coloca mais 2 leites')
    assert m.wpp.cards() and 'O que mais você quer' not in ' '.join(m.wpp.textos())   # buscou, não tocou "Quero mais"


def test_faz_o_pedido_falado_com_o_resumo_na_tela_fecha_sem_pedir_toque():
    m = pedido_ate_o_resumo(Mundo())
    _lia_diz(m, {'acao': 'finalizar', 'resposta': 'Bora! 🎉'})
    m.enviar(('audio', 'faz-o-pedido'))
    assert len(m.mcp.chamadas_de('submitOrder')) == 1
    assert 'Toque em' not in ' '.join(m.wpp.textos()[-3:])


def test_ate_agora_separa_os_itens_da_entrega_e_das_taxas():
    assert T.ate_agora(47.97, subtotal=36.99) == '🧺 Seu pedido até agora: *R$ 36,99*\n🛵 Com entrega e taxas: *R$ 47,97*'
    assert T.ate_agora(10.58, subtotal=10.58) == '🧺 Seu pedido até agora: *R$ 10,58*'   # o falso, antes da entrega
    assert T.ate_agora(10.58) == '🧺 Seu pedido até agora: *R$ 10,58*'
    assert 'R$ 8,00 por pessoa' in T.ate_agora(48.0, pessoas=6, subtotal=40.0)          # cada um paga a entrega também
    assert T.mais_alguma(47.97, None, 0, 'BK', subtotal=36.99).startswith('🧺 Seu pedido até agora: *R$ 36,99*\n🛵')
