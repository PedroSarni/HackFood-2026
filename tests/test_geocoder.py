"""Resolvedor de CEP (BrasilAPI/ViaCEP) sem internet: respostas gravadas."""
import httpx

from src.shared import geocoder as G
from tests.fakes import Mundo

CEP_PAULISTA = {'cep': '01310100', 'state': 'SP', 'city': 'São Paulo', 'neighborhood': 'Bela Vista',
                'street': 'Avenida Paulista',
                'location': {'coordinates': {'latitude': '-23.56', 'longitude': '-46.65'}}}
VIACEP_SAO_CARLOS = {'cep': '13560-010', 'logradouro': 'Avenida São Carlos', 'bairro': 'Centro',
                     'localidade': 'São Carlos', 'uf': 'SP'}


def cliente(brasilapi=None, viacep=None, vistos=None):
    def handler(req):
        if vistos is not None:
            vistos.append(req)
        if 'brasilapi' in req.url.host:
            return httpx.Response(200, json=brasilapi) if brasilapi else httpx.Response(404, json={})
        return httpx.Response(200, json=viacep or {'erro': True})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_cep_resolve_rua_e_bairro_e_pega_o_numero_do_texto():
    r = G.normalizar('01310-100 numero 1578 apto 5', http=cliente(CEP_PAULISTA))
    assert r['texto'] == 'Avenida Paulista, 1578 - Bela Vista, São Paulo - SP, 01310-100'
    assert r['bairro'] == 'Bela Vista' and r['lat'] == -23.56


def test_brasilapi_fora_cai_pro_viacep():
    r = G.normalizar('13560010, 1200', http=cliente(viacep=VIACEP_SAO_CARLOS))
    assert r['texto'] == 'Avenida São Carlos, 1200 - Centro, São Carlos - SP, 13560-010'


def test_sem_cep_nem_consulta():
    vistos = []
    assert G.normalizar('rua episcopal 1500 ap 3 sao carlos', http=cliente(vistos=vistos)) is None
    assert vistos == []  # texto com rua o iFood já entende sozinho


def test_cep_geral_da_cidade_sem_rua_vai_o_texto_cru():
    assert G.normalizar('13560-000, 10', http=cliente({'cep': '13560000', 'city': 'São Carlos', 'street': ''})) is None


def test_numero_ignora_o_numero_do_nome_da_rua():
    assert G._numero('rua 7 de setembro 300 apto 12 campinas', 'Rua 7 de Setembro') == '300'


def test_falha_de_rede_devolve_none():
    def cai(req):
        raise httpx.ConnectError('sem internet')
    assert G.normalizar('01310-100, 1578', http=httpx.Client(transport=httpx.MockTransport(cai))) is None


# --- no fluxo ----------------------------------------------------------------------------

def test_fluxo_manda_o_cep_resolvido_pro_ifood_e_completa_o_bairro():
    m = Mundo()
    m.ctx._geocoder = lambda texto: G._montar('Rua das Flores', '120', 'Vila Prado', 'São Carlos', 'SP',
                                              '13560000', lat=-22.0, lng=-47.9)
    m.enviar('quero leite')
    m.enviar('13560-000 numero 120')
    primeira = m.mcp.chamadas_de('createAddress')[0]
    assert primeira['address'] == 'Rua das Flores, 120 - Vila Prado, São Carlos - SP, 13560-000'
    assert m.estado()['fase'] in ('complemento', 'endereco_escolha')  # não perguntou o bairro


def test_fluxo_cai_pro_texto_original_quando_o_resolvido_nao_acha():
    m = Mundo()
    m.ctx._geocoder = lambda texto: G._montar('Lugar Nenhum', '', '', '', '')  # sem número: mock recusa
    m.enviar('quero leite')
    m.enviar('Rua das Flores, 120, São Carlos')
    enviados = [c['address'] for c in m.mcp.chamadas_de('createAddress')]
    assert enviados == ['Lugar Nenhum', 'Rua das Flores, 120, São Carlos']

def test_resposta_real_do_ifood_vem_embrulhada_em_data():
    """Formato visto no MCP real em 17/10: success + data + agentHints (o mock responde sem envelope)."""
    from src.bot.ifood import Ifood
    real = {'success': True, 'data': {'matchConfidence': 'SINGLE', 'candidates': [{
        'candidateId': 'c1', 'formattedAddress': 'Avenida Paulista, 1578, Bela Vista, São Paulo, SP, CEP 01310-000',
        'location': {'street': 'Avenida Paulista', 'number': '1578', 'neighborhood': 'Bela Vista',
                     'city': 'São Paulo', 'state': 'SP'},
        'coordinates': {'latitude': -23.56144, 'longitude': -46.65592}}]},
        'agentHints': {'confirmAddressGuidance': '...'}}
    r = Ifood(lambda tool, **a: real).geocodificar('Avenida Paulista, 1578')
    c = r['candidatos'][0]
    assert c['id'] == 'c1' and c['bairro'] == 'Bela Vista' and c['lat'] == -23.56144


def test_candidato_fora_do_brasil_e_descartado():
    """Bug real: '01310-100, 1578' cru virou '100th St, 1578, Tisdale, SK' (Canadá)."""
    from src.bot.ifood import Ifood
    real = {'success': True, 'data': {'candidates': [
        {'candidateId': 'ca', 'formattedAddress': '100th St, 1578, Tisdale, SK',
         'location': {'street': '100th St', 'number': '1578', 'state': 'SK'}, 'coordinates': {'latitude': 52.8}},
        {'candidateId': 'br', 'formattedAddress': 'Avenida Paulista, 1578',
         'location': {'street': 'Avenida Paulista', 'number': '1578', 'neighborhood': 'Bela Vista', 'state': 'SP'},
         'coordinates': {'latitude': -23.5, 'longitude': -46.6}}]}}
    assert [c['id'] for c in Ifood(lambda tool, **a: real).geocodificar('x')['candidatos']] == ['br']
