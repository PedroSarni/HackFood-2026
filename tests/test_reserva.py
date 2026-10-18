"""Catálogo de reserva do MCP: o iFood cai e o bot segue no mock sem ninguém ver erro (src/bot/contexto.py),
o kit respeita o teto em reais (src/bot/grupo.py), carne de marcas diferentes conta como a mesma compra, e o
catálogo de fora (Volume do Modal) troca o embutido (src/shared/mcp_fake.py)."""
import importlib
from types import SimpleNamespace

import pytest

from src.bot import grupo
from src.bot.contexto import com_reserva, mcp_caiu
from src.bot.ifood import PrecisaLogin
from src.bot.recorrencia import categoria
from src.shared import alertas, mcp_fake
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao
from tests.fakes import Armazem

LOCAL = {'latitude': -22.0, 'longitude': -47.9}


def test_queda_do_ifood_x_erro_de_negocio_e_login():
    for codigo in ('TIMEOUT', 'REDE', 'HTTP_403', 'HTTP_502', 'RESPOSTA_VAZIA', 'SESSAO', 'RPC_-32603'):
        assert mcp_caiu(ErroMCP(codigo, 'x')), codigo
    for codigo in ('ITEM_NOT_AVAILABLE', 'MERCHANT_CLOSED', 'CART_NOT_FOUND', 'PLACE_NOT_FOUND'):
        assert not mcp_caiu(ErroMCP(codigo, 'x')), codigo
    assert not mcp_caiu(SemAutorizacao('AUTHENTICATION_REQUIRED', 'x')) and not mcp_caiu(PrecisaLogin())
    assert mcp_caiu(ConnectionError('mudo')) and not mcp_caiu(KeyError('bug nosso'))


def test_ifood_mudo_liga_o_mock_refaz_a_chamada_e_avisa_o_dash_de_leve():
    estado, feitas = Armazem(), []

    def real(ferramenta, **args):
        raise ErroMCP('TIMEOUT', 'o iFood não respondeu em 10 s', tentar_de_novo=True)

    def mock(ferramenta, **args):
        feitas.append((ferramenta, args))
        return {'results': ['do mock']}
    chamar = com_reserva(estado, real, mock)
    assert chamar('searchOffers', query='pão') == {'results': ['do mock']}
    assert feitas == [('searchOffers', {'query': 'pão'})]           # a MESMA chamada, já no mock
    assert estado['cfg:mock'] is True and estado['cfg:mock_motivo']['auto'] is True
    a = alertas.listar(estado)['alertas'][0]
    assert a['tipo'] == 'mcp_reserva' and a['nivel'] == 'aviso'       # sino discreto, sem faixa vermelha
    assert 'TIMEOUT' in a['detalhe']


def test_erro_de_negocio_e_login_continuam_com_o_fluxo_de_sempre():
    estado = Armazem()
    for erro in (ErroMCP('ITEM_NOT_AVAILABLE', 'esgotou'), SemAutorizacao('AUTHENTICATION_REQUIRED', 'x')):
        def real(ferramenta, erro=erro, **args):
            raise erro
        with pytest.raises(type(erro)):
            com_reserva(estado, real, lambda *a, **k: pytest.fail('não era pra ir pro mock'))('getItem')
    assert not estado.get('cfg:mock') and not alertas.listar(estado)['alertas']


def test_teto_do_kit_em_reais():
    assert grupo.teto_em('kit churrasco com picanha seara pra 13 amigos por até 300 reais com cerveja') == 300
    assert grupo.teto_em('no máximo R$ 250,50') == 250.5
    assert grupo.teto_em('uns 25 por pessoa', 13) == 325
    assert grupo.teto_em('com 300 conto') == 300
    assert grupo.teto_em('até 2 litros de coca') is None and grupo.teto_em('pra 13 amigos') is None


def test_caber_corta_do_mais_caro_e_nunca_some_com_o_que_foi_pedido():
    linhas = [{'nome': 'Picanha', 'unit': 69.90, 'qtd': 4, 'papel': 'principal'},
              {'nome': 'Brahma 12', 'unit': 38.90, 'qtd': 3, 'papel': 'pedido'},
              {'nome': 'Coalho', 'unit': 17.90, 'qtd': 2, 'papel': 'pedido'},
              {'nome': 'Carvão', 'unit': 17.90, 'qtd': 2, 'papel': 'acompanhamento'}]
    cabe = grupo.caber(linhas, 300, taxa=4.99)
    total = sum(lin['total'] for lin in cabe) + 4.99
    assert total <= 300 and {lin['nome'] for lin in cabe} >= {'Picanha', 'Brahma 12', 'Coalho'}
    assert all(lin['qtd'] >= 1 for lin in cabe)
    assert linhas[0]['qtd'] == 4                              # não mexe na lista de quem chamou
    assert grupo.caber(linhas, None) == [{**lin, 'total': round(lin['unit'] * lin['qtd'], 2)} for lin in linhas]


def test_carne_de_marcas_diferentes_e_a_mesma_compra():
    assert categoria('Contrafilé bovino Friboi') == categoria('Picanha bovina Seara') == 'carne'
    assert categoria('Carne moída de patinho Friboi') == 'carne'
    assert categoria('Pastel de carne') == 'pastel' and categoria('Esfiha de carne') == 'esfiha'
    assert categoria('Marmita de carne de panela') == 'marmita'


@pytest.fixture
def catalogo_de_fora():
    dados = {'versao': 't1', 'img_base': 'https://exemplo.test/img/', 'sinonimos': {'breja': ['cerveja']},
             'lojas': {'vp': {'nome': 'Supermercado Teste', 'tipo': 'GROCERIES', 'eta': {'min': 30, 'max': 45},
                              'taxa': 4.99, 'nota': 4.7, 'km': 1.8, 'minimo': 30, 'logo': 'loja-vp.jpg'}},
             'itens': [{'loja': 'vp', 'nome': 'Picanha bovina Seara', 'desc': 'Peça aprox. 1 kg', 'preco': 74.9,
                        'promo': 69.9, 'foto': 'picanha.jpg', 'grupos': None},
                       {'loja': 'vp', 'nome': 'Cerveja Brahma lata 350 ml', 'desc': 'Pack com 12', 'preco': 41.9,
                        'promo': None, 'foto': 'brahma.jpg',
                        'grupos': [['Gelada?', 1, 1, [['Sim', 0], ['Não', 0]]]]}]}
    embutida = mcp_fake._id_item(0)
    mcp_fake.usar_catalogo(dados)
    yield embutida
    importlib.reload(mcp_fake)  # volta o catálogo embutido pros outros testes


def test_catalogo_de_fora_troca_lojas_itens_fotos_e_ids(catalogo_de_fora):
    m = mcp_fake.McpFake(armazem={}, chave='mock:1')
    r = m.chamar('searchOffers', query='breja', userLocation=LOCAL, resultKind='ITEM')
    item = r['results'][0]
    assert item['itemName'] == 'Cerveja Brahma lata 350 ml' and item['itemImageUrl'] == 'https://exemplo.test/img/brahma.jpg'
    assert item['merchant']['merchantLogoUrl'] == 'https://exemplo.test/img/loja-vp.jpg'
    assert mcp_fake._id_item(0) != catalogo_de_fora      # id de um catálogo nunca vale no outro
    d = m.chamar('getItem', itemId=item['itemId'], userLocation=LOCAL)
    assert d['optionGroups'][0]['name'] == 'Gelada?' and len(d['optionGroups'][0]['options']) == 2
    pic = m.chamar('searchOffers', query='picanha seara', userLocation=LOCAL, resultKind='ITEM')['results'][0]
    assert pic['promotionalUnitPrice'] == 69.9 and mcp_fake.loja_do_mock(pic['merchant']['merchantId'])


def test_kit_com_teto_nunca_passa_do_valor_dito():
    from tests.fakes import Mundo
    from tests.test_fluxo import endereco_pronto
    m = Mundo()
    endereco_pronto(m)
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    sem_teto = m.estado()['kit']
    teto = round(sem_teto['total'] * 0.6, 2)        # bem abaixo do que o kit livre custou
    m.enviar(f'quero lanchar em 5 pessoas hamburguer por até {teto:.0f} reais'.replace('.', ','))
    k = m.estado()['kit']
    assert k['teto'] and k['total'] <= k['teto'] + 0.005
    assert 'Dentro do seu limite' in m.wpp.saida[-1][1]['texto']


def test_rotas_do_interruptor_do_mock():
    from fastapi.testclient import TestClient

    from src.painel.servidor import criar_api
    arm = Armazem()
    cli = TestClient(criar_api({'real': SimpleNamespace(fonte=SimpleNamespace(armazem=lambda: arm))}))
    assert cli.get('/api/mock').json() == {'ligado': False, 'auto': False, 'desde': None, 'motivo': None,
                                           'reservaAuto': False}
    r = cli.post('/api/mock', json={'ligado': True}).json()
    assert r['ligado'] and not r['auto'] and arm['cfg:mock'] is True
    assert cli.post('/api/mock', json={'ligado': True}, headers={'origin': 'https://exemplo.com'}).status_code == 403
    assert cli.post('/api/mock', json={'ligado': False, 'reservaAuto': True}).json()['reservaAuto'] is True
    assert arm['cfg:mock'] is False and 'cfg:mock_motivo' not in arm


def test_modo_palco_desligado_por_padrao_e_so_ele_arma_a_troca():
    from src.bot.contexto import reserva_armada
    estado = Armazem()
    assert not reserva_armada(estado)          # fora do palco: queda do iFood dá erro, nunca pedido de mentira
    estado['cfg:reserva_auto'] = True
    assert reserva_armada(estado)
