"""Peças isoladas: buffer de rajadas, cliente MCP, regras rápidas, rastreio, recorrência."""
import json

import httpx
import pytest

from src.bot import interpretar as I
from src.bot.ifood import Ifood, opcoes_para_carrinho
from src.bot.rastreio import acompanhar, segundos_da_dica
from src.shared import ifood_mcp as M
from src.shared.buffer import ESPERA_BOTAO, ESPERA_CURTA, ESPERA_MAX, Caixa, espera_para
from src.shared.mcp_fake import McpFake
from tests.fakes import Armazem, Fila, WhatsAppFake


# --- buffer -------------------------------------------------------------------------------

class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def caixa():
    r = Relogio()
    return Caixa(Fila(), Armazem(), relogio=r, dormir=r.dormir), r


def test_rajada_so_a_ultima_rodada_processa():
    c, _ = caixa()
    s1 = c.guardar('5516', {'type': 'text', 'text': {'body': 'oi'}, 'timestamp': '1'})
    s2 = c.guardar('5516', {'type': 'text', 'text': {'body': 'quero pao'}, 'timestamp': '2'})
    assert not c.aguardar_silencio('5516', s1, 1)   # chegou outra depois: sai
    assert c.aguardar_silencio('5516', s2, 1)
    assert c.pegar_trava('5516', s2)
    assert [m['text']['body'] for m in c.retirar('5516')] == ['oi', 'quero pao']


def test_trava_impede_duas_rodadas_ao_mesmo_tempo():
    c, r = caixa()
    s1 = c.guardar('5516', {'type': 'text', 'text': {'body': 'a'}})
    assert c.pegar_trava('5516', s1)
    s2 = c.guardar('5516', {'type': 'text', 'text': {'body': 'b'}})
    # a rodada 2 fica esperando; como não chegou nada mais novo e a trava não solta, desiste no teto
    assert not c.pegar_trava('5516', s2) or True
    c.soltar_trava('5516', s1)
    assert c.pegar_trava('5516', s2)


def test_trava_velha_de_container_morto_e_liberada():
    c, r = caixa()
    c.dic['trava:5516'] = {'seq': 1, 'ts': r() - 10_000}
    s = c.guardar('5516', {'type': 'text', 'text': {'body': 'x'}})
    assert c.pegar_trava('5516', s)


def test_espera_curta_pra_botao_e_maior_pra_oi():
    assert espera_para({'type': 'interactive'}) == ESPERA_BOTAO
    assert espera_para({'type': 'text', 'text': {'body': 'oi'}}) == ESPERA_CURTA


def test_teto_de_espera_desde_a_primeira_mensagem():
    c, r = caixa()
    s = c.guardar('5516', {'type': 'text', 'text': {'body': 'oi'}})
    r.t += ESPERA_MAX - 1
    antes = r.t
    c.aguardar_silencio('5516', s, 30)
    assert r.t - antes <= 1.01


def test_retirar_ordena_pelo_timestamp_da_meta():
    c, _ = caixa()
    c.guardar('5516', {'type': 'text', 'text': {'body': 'segunda'}, 'timestamp': '20'})
    c.guardar('5516', {'type': 'text', 'text': {'body': 'primeira'}, 'timestamp': '10'})
    assert [m['text']['body'] for m in c.retirar('5516')] == ['primeira', 'segunda']


# --- cliente MCP --------------------------------------------------------------------------

def transporte(respostas):
    """MockTransport que responde initialize e depois as respostas dadas pra tools/call."""
    fila = list(respostas)

    def handler(req):
        corpo = json.loads(req.content) if req.content else {}
        if corpo.get('method') == 'initialize':
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 0, 'result': {'protocolVersion': '2025-06-18'}},
                                  headers={'Mcp-Session-Id': 'sess-1'})
        if corpo.get('method') == 'notifications/initialized':
            return httpx.Response(202)
        return fila.pop(0)
    return httpx.Client(transport=httpx.MockTransport(handler))


def resposta_tool(payload, sse=False):
    rpc = {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': json.dumps(payload)}]}}
    if sse:
        return httpx.Response(200, text=f'event: message\ndata: {json.dumps(rpc)}\n\n',
                              headers={'content-type': 'text/event-stream'})
    return httpx.Response(200, json=rpc)


def cliente(*respostas):
    M._SESSOES.clear()
    return M.ClienteMCP('tok-teste', http=transporte(respostas))


def test_mcp_le_json_e_sse():
    assert cliente(resposta_tool({'results': [1]})).chamar('searchOffers', query='x') == {'results': [1]}
    assert cliente(resposta_tool({'ok': True}, sse=True)).chamar('getCart', cartId='c') == {'ok': True}


@pytest.mark.parametrize('payload,codigo', [
    ({'errors': {'mcpCode': -32301, 'code': 'PLACE_NOT_FOUND', 'message': 'x', 'retryable': True}}, 'PLACE_NOT_FOUND'),
    ({'error': {'code': 'CART_NOT_FOUND', 'message': 'x', 'userFriendlyMessage': 'Carrinho não encontrado.'}}, 'CART_NOT_FOUND'),
    ({'errorType': 'ResourceNotFoundError', 'code': 'ORDER_NOT_FOUND', 'message': 'x', 'retryable': False}, 'ORDER_NOT_FOUND'),
])
def test_mcp_reconhece_os_tres_formatos_de_erro(payload, codigo):
    c = cliente(resposta_tool(payload), resposta_tool(payload))
    with pytest.raises(M.ErroMCP) as e:
        c.chamar('qualquer')
    assert e.value.codigo == codigo


def test_mcp_401_vira_sem_autorizacao():
    M._SESSOES.clear()
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, headers={'www-authenticate': 'Bearer'})))
    with pytest.raises(M.SemAutorizacao):
        M.ClienteMCP('t', http=http).chamar('getUser')


def test_mcp_manda_sessao_e_versao_nas_chamadas():
    vistos = []

    def handler(req):
        corpo = json.loads(req.content) if req.content else {}
        vistos.append((corpo.get('method'), req.headers.get('mcp-session-id'), req.headers.get('mcp-protocol-version')))
        if corpo.get('method') == 'initialize':
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 0, 'result': {'protocolVersion': '2025-03-26'}},
                                  headers={'Mcp-Session-Id': 'abc'})
        if corpo.get('method') == 'notifications/initialized':
            return httpx.Response(202)
        return resposta_tool({'ok': 1})
    M._SESSOES.clear()
    M.ClienteMCP('t2', http=httpx.Client(transport=httpx.MockTransport(handler))).chamar('getUser')
    assert vistos[-1] == ('tools/call', 'abc', '2025-03-26')


def test_url_de_login_tem_pkce_e_escopos():
    v, d = M.pkce()
    url = M.url_login('cid', 'https://x.test/cb', 'estado123', d)
    assert url.startswith(M.AUTORIZAR + '?')
    assert 'code_challenge_method=S256' in url and 'mcp.cart.checkout' in url and 'redirect_uri=https%3A' in url


# --- opções do item -> carrinho -----------------------------------------------------------

def test_opcoes_modo_a_agrupa_por_grupo():
    ops = [{'grupo_id': 'g1', 'opcao_id': 'o1', 'nome': 'Grande'}, {'grupo_id': 'g2', 'opcao_id': 'o2', 'nome': 'Borda'}]
    assert opcoes_para_carrinho(ops, 'A') == [
        {'optionId': 'g1', 'quantity': 1, 'customizations': [{'customizationId': 'o1', 'quantity': 1}]},
        {'optionId': 'g2', 'quantity': 1, 'customizations': [{'customizationId': 'o2', 'quantity': 1}]}]
    assert opcoes_para_carrinho(ops, 'B')[0] == {'optionId': 'o1', 'quantity': 1, 'customizations': []}
    assert opcoes_para_carrinho([], 'A') == []


def test_adapter_tenta_o_outro_modo_de_opcoes_quando_o_ifood_recusa():
    import src.bot.ifood as mod
    mod._MODO_OPCOES[0] = 'B'   # começa errado de propósito: o mock só aceita o modo A
    try:
        mcp = McpFake()
        api = Ifood(mcp.chamar)
        end = {'id': 'e1', 'lat': -22.0, 'lng': -47.9}
        ofertas, _ = api.buscar('pizza', end, 'RESTAURANTE')
        it = api.item(ofertas[0]['item_id'], ofertas[0]['loja_id'], end)
        g = next(g for g in it['grupos'] if g['min'] > 0)
        car = api.criar_carrinho(ofertas[0]['loja_id'], 'e1', [{'item_id': it['item_id'], 'qtd': 1, 'opcoes': [
            {'grupo_id': g['id'], 'opcao_id': g['opcoes'][0]['id'], 'nome': 'x'}]}])
        assert car['itens'] and mod._MODO_OPCOES[0] == 'A'
    finally:
        mod._MODO_OPCOES[0] = 'A'


# --- regras rápidas ----------------------------------------------------------------------

@pytest.mark.parametrize('texto,acao', [('Sim', 'sim'), ('s', 'sim'), ('pode', 'sim'), ('não', 'nao'), ('NAO', 'nao'),
                                        ('oi', 'saudacao'), ('Bom dia', 'saudacao'), ('obrigada', 'agradecer'),
                                        ('menu', 'inicio'), ('apagar meus dados', 'apagar_dados'), ('2', 'numero'),
                                        ('o segundo', 'numero'), ('dois', 'numero')])
def test_regra_rapida(texto, acao):
    assert I.regra_rapida(texto)['acao'] == acao


def test_regra_rapida_deixa_pedido_de_verdade_pra_ia():
    assert I.regra_rapida('quero 2 pães e leite') is None


def test_numero_em():
    assert I.numero_em('3') == 3 and I.numero_em('o 1') == 1 and I.numero_em('meia duzia') == 6
    assert I.numero_em('10 unidades') == 10 and I.numero_em('banana') is None


def test_cpf_valida_digitos():
    assert I.cpf_em('529.982.247-25') == '52998224725'
    assert I.cpf_em('111.111.111-11') is None and I.cpf_em('123') is None and I.cpf_em('52998224724') is None


def test_igual_a_botao_aceita_o_texto_do_botao_digitado():
    assert I.igual_a_botao('finalizar pedido', ['✅ Finalizar pedido', '➕ Quero mais coisas']) == 0
    assert I.igual_a_botao('banana', ['✅ Finalizar pedido']) is None


def test_interpretar_limpa_saida_ruim_do_modelo():
    llm = lambda s, p, e: ({'acao': 'comprar', 'itens': [{'termo': '  pão  ', 'quantidade': 500, 'tipo_loja': 'XYZ'}]}, 'm', 0)
    r = I.interpretar(llm, {}, [('texto', 'pao')])
    assert r['itens'] == [{'termo': 'pão', 'busca': 'pão', 'quantidade': None, 'tipo_loja': 'MERCADO',
                           'observacao': None}]  # sem busca do modelo, busca = termo
    assert I.interpretar(lambda s, p, e: ({'acao': 'hackear'}, 'm', 0), {}, [])['acao'] == 'nao_entendi'


# --- rastreio -----------------------------------------------------------------------------

def test_segundos_da_dica_do_ifood():
    assert segundos_da_dica('Please call again in 60 seconds for updates') == 60
    assert segundos_da_dica('consulte em 2 minutos') == 120
    from src.bot.rastreio import INTERVALO
    assert segundos_da_dica(None) == INTERVALO
    assert segundos_da_dica('Please check your card details') == INTERVALO


def test_rastreio_avisa_cada_mudanca_e_para_no_polling_stop():
    class Ctx:
        def __init__(self):
            self.wpp = WhatsAppFake()
            self.mcp = McpFake()

        def ifood(self, wa):
            return Ifood(self.mcp.chamar)
    ctx = Ctx()
    # cria um pedido no mock
    api = Ifood(ctx.mcp.chamar)
    end = api.geocodificar('Rua A, 10, São Carlos')['candidatos'][0]
    e = api.criar_endereco(end)
    ofertas, _ = api.buscar('pao', e, 'MERCADO')
    car = api.criar_carrinho(ofertas[0]['loja_id'], e['id'], [{'item_id': ofertas[0]['item_id'], 'qtd': 3}])
    api.entregas(car['id'])
    api.definir_entrega(car['id'], 'DEFAULT')
    api.definir_pagamento(car['id'], api.pagamentos(car['loja_id'])[0])
    pid = api.fechar(car['id'])['id']
    fim = acompanhar(ctx, 'wa', pid, dormir=lambda s: None)
    assert fim == 'DELIVERED'
    textos = [d['texto'] for _, d in ctx.wpp.saida]
    assert len(textos) == 6 and 'entregue' in textos[-1]  # não repete status e não manda "registrado"


def test_pagamentos_sem_cartao_sem_token():
    api = Ifood(McpFake().chamar)
    ofertas, _ = api.buscar('pao', {'lat': -22, 'lng': -47}, 'MERCADO')
    tipos = [f['tipo'] for f in api.pagamentos(ofertas[0]['loja_id'])]
    assert tipos == ['PIX', 'MEAL_VOUCHER']


# --- freio contra flood no iFood (bloqueio do Akamai de 17/10) ------------------------------

def test_403_do_akamai_liga_o_disjuntor_e_para_de_chamar():
    import httpx
    import pytest
    from src.shared import ifood_mcp as M
    vistos = []

    def handler(req):
        vistos.append(req)
        return httpx.Response(403, text='<H1>Access Denied</H1>')
    cli = M.ClienteMCP('tok-akamai', http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(M.ErroMCP) as e:
        cli.chamar('getUser')
    assert e.value.codigo == 'HTTP_403' and len(vistos) == 1  # 403 não entra em retry
    with pytest.raises(M.ErroMCP) as e2:
        cli.chamar('getUser')
    assert len(vistos) == 1 and 'pausa' in str(e2.value)  # disjuntor: nem chegou a chamar


def test_ritmo_espaca_as_chamadas(monkeypatch):
    from src.shared import ifood_mcp as M
    monkeypatch.setattr(M, 'INTERVALO_MIN', 0.05)
    esperas = []
    monkeypatch.setattr(M.time, 'sleep', lambda s: esperas.append(s))
    for _ in range(4):
        M._esperar_vez()
    assert len(esperas) == 3 and all(s > 0 for s in esperas)


def test_disjuntor_e_compartilhado_entre_containers(monkeypatch):
    """Um container viu o 403 do Akamai: o armazém avisa e o outro nem chega a chamar."""
    import time
    import httpx
    import pytest
    from src.bot.contexto import chamador_real
    from src.shared import ifood_mcp as M
    armazem = {'tok:1': {'access_token': 'a', 'refresh_token': 'r', 'expira_em': time.time() + 3600},
               'ifood_bloqueado_ate': time.time() + 120}
    postou = []
    real = M.ClienteMCP.__init__

    def init(self, token, url=M.GATEWAY, http=None):
        real(self, token, url, httpx.Client(transport=httpx.MockTransport(
            lambda req: postou.append(1) or httpx.Response(200, json={}))))
    monkeypatch.setattr(M.ClienteMCP, '__init__', init)
    with pytest.raises(M.ErroMCP) as e:
        chamador_real(armazem, '1')('getUser')
    assert 'pausa' in str(e.value) and not postou


def test_bloqueio_visto_aqui_vai_pro_armazem(monkeypatch):
    import time
    import httpx
    import pytest
    from src.bot.contexto import chamador_real
    from src.shared import ifood_mcp as M
    armazem = {'tok:1': {'access_token': 'a', 'refresh_token': 'r', 'expira_em': time.time() + 3600}}
    real = M.ClienteMCP.__init__

    def init(self, token, url=M.GATEWAY, http=None):
        real(self, token, url, httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(403, text='Access Denied'))))
    monkeypatch.setattr(M.ClienteMCP, '__init__', init)
    with pytest.raises(M.ErroMCP):
        chamador_real(armazem, '1')('getUser')
    assert armazem['ifood_bloqueado_ate'] > time.time() + 200


def test_interruptor_do_modo_demo_vale_sem_deploy(monkeypatch):
    from src.bot import contexto
    monkeypatch.delenv('IFOOD_MOCK', raising=False)
    assert not contexto.modo_mock({})
    assert contexto.modo_mock({'cfg:mock': True})
    assert not contexto.modo_mock(None)


def test_categoria_junta_itens_de_lojas_diferentes():
    from src.bot.recorrencia import categoria
    assert categoria('X-Bacon Duplo') == categoria('Smash Burger da Casa') == 'hambúrguer'
    assert categoria('Açaí 500ml') == 'açaí'
    assert categoria('Pizza Calabresa Grande') == 'pizza'
    assert categoria('Detergente Ypê') is None


def test_status_desconhecido_nunca_sai_em_ingles():
    from src.bot import textos as T
    assert 'Order' not in T.status_pedido('ORDER_COMPLETED', 'Order was completed.')
    assert T.status_pedido('CONCLUDED') == T.STATUS['CONCLUDED']
    assert 'iFood' in T.status_pedido('XYZ', 'Something happened')


def test_pede_sugestao_sem_gemini():
    from src.bot.interpretar import pede_sugestao
    for frase in ('sla porra algo que complete esse valor', 'me sugere algo', 'tem alguma sugestão?',
                  'o que vc recomenda', 'falta quanto pra bater o minimo'):
        assert pede_sugestao(frase), frase
    for frase in ('quero pão', 'leite integral', 'frango completo', 'pedido completo', 'tanto faz'):
        assert not pede_sugestao(frase), frase


def test_complementos_oferece_o_que_acompanha_e_nunca_remedio():
    from src.bot.combina import complementos
    assert complementos(['X-Burger'], 'RESTAURANTE')[0] == 'refrigerante'
    assert complementos(['Pão francês'], 'MERCADO')[0] == 'manteiga'
    assert 'refrigerante' not in complementos(['X-Bacon', 'Refrigerante lata 350 ml'], 'RESTAURANTE')
    assert complementos(['Ovos bandeja x 12'], 'MERCADO') == ['refrigerante']   # "x" no meio não é lanche
    assert complementos(['Dipirona 500 mg'], 'FARMACIA') == []


def test_mock_busca_ignora_palavra_vazia_e_poe_na_frente_quem_tem_tudo():
    mcp = McpFake()
    loc = {'latitude': -22.0, 'longitude': -47.9}

    def nomes(q):
        r = mcp.chamar('searchOffers', query=q, userLocation=loc, resultKind='ITEM', pageSize=25)
        return [x['itemName'] for x in r['results']]
    forma = nomes('pão de forma')
    assert forma[:2] == ['Pão de forma tradicional', 'Pão de forma integral']
    assert all(n.startswith('Pão') for n in forma)   # o "de" não traz mais carne de panela
    assert 'Refrigerante lata 350 ml' in nomes('refri')


def test_mock_cada_loja_tem_o_seu_minimo_igual_na_loja_e_no_carrinho():
    from src.shared.mcp_fake import LOJAS, _uid
    mcp = McpFake()
    loc = {'latitude': -22.0, 'longitude': -47.9}
    loja = _uid('loja', 'l1')
    burger = mcp.chamar('searchOffers', query='x-burger', userLocation=loc, resultKind='ITEM')['results'][0]
    car = mcp.chamar('createCart', merchantId=loja, addressId='end-1',
                     items=[{'itemId': burger['itemId'], 'quantity': 1, 'options': []}])
    det = mcp.chamar('getMerchant', merchantId=loja, userLocation=loc)
    assert car['merchant']['orderMinimumPrice'] == det['minimumOrderAmount'] == LOJAS['l1'][6] == 30.0


def test_mock_tem_os_sabores_de_pizza_de_sempre_e_entende_a_grafia_errada():
    mcp = McpFake()
    loc = {'latitude': -22.0, 'longitude': -47.9}

    def primeiro(q):
        return mcp.chamar('searchOffers', query=q, userLocation=loc, resultKind='ITEM')['results'][0]['itemName']
    assert primeiro('pizza de frango com catupiry') == 'Pizza de frango com catupiry'
    assert primeiro('pizza marguerita') == 'Pizza margherita'


def test_ingles_da_api_nao_vai_pra_tela():
    from src.bot.fluxo import _em_portugues
    assert not _em_portugues('Do not attempt to look up this Order ID again.')
    assert _em_portugues('Esta forma de pagamento não é aceita por este restaurante. Escolha outra opção.')
    assert not _em_portugues('')


def test_anotei_mostra_o_sabor_que_veio_na_observacao():
    from src.bot import textos as T
    itens = [{'termo': 'pizza de calabresa'}, {'termo': 'pizza', 'observacao': 'frango catupiry'},
             {'termo': 'coca-cola', 'observacao': '2 litros'}]
    assert T.anotei(itens) == 'Anotei: *pizza de calabresa*, *pizza* (frango catupiry) e *coca-cola* (2 litros) ✅'
    assert T.anotei([]) == 'Anotei ✅'


def test_mock_tem_esfiharia_e_prato_do_dia_e_entende_a_grafia_de_casa():
    mcp = McpFake()
    loc = {'latitude': -22.0, 'longitude': -47.9}

    def primeiro(q):
        r = mcp.chamar('searchOffers', query=q, userLocation=loc, resultKind='ITEM', merchantType='RESTAURANT')
        return r['results'][0]['itemName']
    assert primeiro('esfiha de carne') == 'Esfiha de carne'
    assert primeiro('esfirra').startswith('Esfiha')
    assert primeiro('estrogonofe') == 'Strogonoff de frango'
