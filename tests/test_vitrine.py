"""Vitrine do "oi": agentes internos montam ideias do gosto da pessoa (src/bot/vitrine.py)."""
import time

from src.bot import vitrine
from tests.fakes import Mundo
from tests.test_fluxo import endereco_pronto


def as_horas(m, hora):
    """Põe o relógio do Mundo na hora local (Brasília) pedida, no mesmo dia."""
    m.agora = m.agora - time.gmtime(m.agora - 3 * 3600).tm_hour * 3600 + hora * 3600


def pronto_pra_oi(hist=None, hora=20):
    m = Mundo()
    endereco_pronto(m)       # tem endereço com coordenada: dá pra buscar ideias
    m.enviar('cancelar')     # volta pro começo: o próximo "oi" é de começo de conversa
    if hist:
        m.armazem[f'hist:{m.wa}'] = hist
    as_horas(m, hora)
    m.wpp.limpar()
    return m


def vitrine_enviada(m):
    return next((d for t, d in m.wpp.saida if t == 'carrossel' and d['texto'] == vitrine_topo()), None)


def vitrine_topo():
    from src.bot import textos as T
    return T.VITRINE_TOPO


# --- agentes ---------------------------------------------------------------------------

def test_agente_gosto_le_o_historico_e_os_pedidos_do_ifood():
    hist = {'cat:pizza': {'vezes': 3, 'ultima': 1}, 'cat:hambúrguer': {'vezes': 1, 'ultima': 9}}
    assert vitrine.agente_gosto(hist, []) == 'pizza'                     # mais vezes ganha
    assert vitrine.agente_gosto({}, [{'resumo': '2x X-Bacon, 1x Coca'}]) == 'hambúrguer'  # pedido feito no app
    assert vitrine.agente_gosto({}, []) is None


def test_agente_hora_segue_o_relogio_de_brasilia():
    m = Mundo()
    for hora, cat in ((8, 'pão'), (12, 'marmita'), (16, 'açaí'), (20, 'pizza'), (2, 'hambúrguer')):
        as_horas(m, hora)
        assert vitrine.da_hora(m.agora) == cat
    assert vitrine.agente_hora(m.agora, 'hambúrguer') is None            # mesma do gosto: não repete card


def test_descontos_e_precinho_so_com_produto_de_verdade():
    ofertas = [{'preco': 50.0, 'preco_antigo': None}, {'preco': 30.0, 'preco_antigo': 40.0}]
    assert vitrine.agente_descontos(ofertas) == [ofertas[1]]
    assert vitrine.agente_precinho('pizza', ofertas) == (45, [ofertas[1]])
    assert vitrine.agente_precinho('pastel', ofertas) is None             # teto 20: nada abaixo


# --- no fluxo --------------------------------------------------------------------------

def test_oi_chega_simplesinho_com_a_vitrine_embaixo():
    m = pronto_pra_oi()
    m.enviar('oi')
    tipos = [t for t, _ in m.wpp.saida]
    assert tipos == ['botoes', 'carrossel']                               # boas-vindas e logo a vitrine
    assert len(m.wpp.saida[0][1]['texto']) < 90                           # simplesinha
    v = vitrine_enviada(m)
    assert 2 <= len(v['cards']) <= 4 and all(c['botoes'][0][0].startswith('vit:') for c in v['cards'])
    assert len({c['imagem'] for c in v['cards']}) == len(v['cards'])      # cada card com a sua foto


def test_vitrine_segue_o_gosto_da_pessoa():
    m = pronto_pra_oi(hist={'cat:pizza': {'nome': 'pizza', 'vezes': 3, 'ultima': 1}}, hora=12)
    m.enviar('oi')
    primeiro = vitrine_enviada(m)['cards'][0]['texto']
    assert 'Tô afim de Pizza' in primeiro and 'Seu favorito' in primeiro  # meio-dia, mas ele gosta é de pizza


def test_card_do_precinho_busca_com_teto_e_so_mostra_abaixo_dele():
    m = pronto_pra_oi(hist={'cat:pizza': {'nome': 'pizza', 'vezes': 3, 'ultima': 1}})
    m.enviar('oi')
    cards = m.estado()['vitrine']['cards']
    i = next(i for i, c in enumerate(cards) if c['agente'] == 'precinho')
    m.tocar(f'vit:{i}')
    assert m.mcp.chamadas_de('searchOffers')[-1]['refinements']['maxItemPrice'] == 45.0
    lista = m.estado()['listas'][m.estado()['lista_atual']]
    assert lista['ofertas'] and all(o['preco'] <= 45 for o in lista['ofertas'])


def test_card_de_descontos_so_mostra_promocao():
    m = pronto_pra_oi(hist={'cat:pizza': {'nome': 'pizza', 'vezes': 3, 'ultima': 1}})
    m.enviar('oi')
    cards = m.estado()['vitrine']['cards']
    m.tocar(f'vit:{next(i for i, c in enumerate(cards) if c["agente"] == "descontos")}')
    lista = m.estado()['listas'][m.estado()['lista_atual']]
    assert lista['ofertas'] and all(o['preco_antigo'] and o['preco_antigo'] > o['preco'] for o in lista['ofertas'])


def test_card_pode_ser_escolhido_escrevendo_ou_falando():
    m = pronto_pra_oi(hist={'cat:pizza': {'nome': 'pizza', 'vezes': 3, 'ultima': 1}})
    m.enviar('oi')
    m.enviar('descontos pra você')
    assert m.estado()['fase'] == 'escolhendo'


def test_vitrine_guardada_nao_busca_de_novo_a_cada_oi():
    m = pronto_pra_oi()
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar('oi')
    buscas = len(m.mcp.chamadas_de('searchOffers'))
    assert 1 <= buscas - antes <= vitrine.MAX_BUSCAS                      # o firewall do iFood barra rajada
    m.enviar('oi')
    assert len(m.mcp.chamadas_de('searchOffers')) == buscas               # 2º "oi": a mesma vitrine, sem buscar
    m.agora += vitrine.VALIDADE + 1
    m.enviar('oi')
    assert len(m.mcp.chamadas_de('searchOffers')) > buscas                # venceu: monta de novo


def test_sem_endereco_o_oi_vem_sem_vitrine():
    m = Mundo()
    m.enviar('oi')
    assert [t for t, _ in m.wpp.saida] == ['botoes'] and not m.mcp.chamadas_de('searchOffers')


def test_vitrine_no_modo_audio_vira_fotos_numeradas():
    m = pronto_pra_oi()
    m.ctx._locutor = lambda t: ('audio/ogg', b'OggS')
    m.enviar('me responde por áudio')
    m.wpp.limpar()
    m.enviar('oi')
    tipos = [t for t, _ in m.wpp.saida]
    assert 'carrossel' not in tipos and tipos[-1] == 'audio' and tipos.count('imagem') >= 2
