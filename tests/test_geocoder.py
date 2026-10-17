"""Geocodificador grátis (Nominatim + BrasilAPI/ViaCEP) sem internet: respostas gravadas."""
import httpx

from src.shared import geocoder as G
from tests.fakes import Mundo

EPISCOPAL = [{'lat': '-22.027', 'lon': '-47.891', 'address': {
    'road': 'Rua Episcopal', 'suburb': 'Núcleo Residencial Sylvio Villari', 'city': 'São Carlos',
    'ISO3166-2-lvl4': 'BR-SP', 'state': 'São Paulo', 'postcode': '13560-294'}}]
SETE_RIO_BRANCO = [{'lat': '-9.94', 'lon': '-67.82', 'address': {
    'road': 'Rua 7 de Setembro', 'city': 'Rio Branco', 'ISO3166-2-lvl4': 'BR-AC'}}]
CEP_PAULISTA = {'cep': '01310100', 'state': 'SP', 'city': 'São Paulo', 'neighborhood': 'Bela Vista',
                'street': 'Avenida Paulista',
                'location': {'coordinates': {'latitude': '-23.56', 'longitude': '-46.65'}}}


def cliente(nominatim=(), cep=None, vistos=None):
    def handler(req):
        if vistos is not None:
            vistos.append(req)
        if 'nominatim' in req.url.host:
            return httpx.Response(200, json=list(nominatim))
        if 'brasilapi' in req.url.host:
            return httpx.Response(200, json=cep) if cep else httpx.Response(404, json={})
        return httpx.Response(200, json={'erro': True})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_texto_baguncado_vira_endereco_canonico_sem_complemento_e_sem_bairro_chutado():
    vistos = []
    r = G.normalizar('rua episcopal 1500 ap 3 sao carlos', http=cliente(EPISCOPAL, vistos=vistos))
    assert r['texto'] == 'Rua Episcopal, 1500, São Carlos - SP'
    assert r['lat'] == -22.027 and r['bairro'] == ''  # bairro do OSM é do trecho, não do número
    assert 'ap 3' not in vistos[0].url.params['q']  # complemento atrapalha o geocode


def test_bairro_entra_quando_a_pessoa_escreveu():
    r = G.normalizar('rua episcopal 1500 sylvio villari sao carlos', http=cliente(EPISCOPAL))
    assert r['bairro'] == 'Núcleo Residencial Sylvio Villari'


def test_cidade_nao_citada_e_sem_ancora_nao_chuta_outro_estado():
    assert G.normalizar('rua sete de setembro 500', http=cliente(SETE_RIO_BRANCO)) is None


def test_com_ancora_trava_a_busca_perto_da_pessoa():
    vistos = []
    G.normalizar('rua sete de setembro 500', perto=(-22.01, -47.89), http=cliente(SETE_RIO_BRANCO, vistos=vistos))
    assert vistos[0].url.params['bounded'] == '1' and 'viewbox' in vistos[0].url.params


def test_cep_resolve_rua_e_bairro_e_pega_o_numero_do_texto():
    r = G.normalizar('01310-100 numero 1578 apto 5', http=cliente(cep=CEP_PAULISTA))
    assert r['texto'] == 'Avenida Paulista, 1578 - Bela Vista, São Paulo - SP, 01310-100'
    assert r['bairro'] == 'Bela Vista' and r['lat'] == -23.56


def test_numero_ignora_o_numero_do_nome_da_rua():
    assert G._numero('rua 7 de setembro 300 apto 12 campinas', 'Rua 7 de Setembro') == '300'


def test_falha_de_rede_devolve_none():
    def cai(req):
        raise httpx.ConnectError('sem internet')
    assert G.normalizar('rua episcopal 1500 sao carlos', http=httpx.Client(transport=httpx.MockTransport(cai))) is None


# --- no fluxo ----------------------------------------------------------------------------

def test_fluxo_manda_o_endereco_arrumado_pro_ifood_e_completa_o_bairro():
    m = Mundo()
    m.ctx._geocoder = lambda texto, perto: G._montar('Rua das Flores', '120', 'Vila Prado', 'São Carlos', 'SP',
                                                     lat=-22.0, lng=-47.9)
    m.enviar('quero leite')
    m.enviar('rua das flores 120 ap 4 sanca')
    primeira = m.mcp.chamadas_de('createAddress')[0]
    assert primeira['address'] == 'Rua das Flores, 120 - Vila Prado, São Carlos - SP'
    assert m.estado()['fase'] in ('complemento', 'endereco_escolha')  # não perguntou o bairro


def test_fluxo_cai_pro_texto_original_quando_o_arrumado_nao_acha():
    m = Mundo()
    m.ctx._geocoder = lambda texto, perto: G._montar('Lugar Nenhum', '', '', '', '')  # sem número: mock recusa
    m.enviar('quero leite')
    m.enviar('Rua das Flores, 120, São Carlos')
    enviados = [c['address'] for c in m.mcp.chamadas_de('createAddress')]
    assert enviados == ['Lugar Nenhum', 'Rua das Flores, 120, São Carlos']
