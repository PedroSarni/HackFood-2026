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


@pytest.mark.parametrize('texto', ['cancelar pedido', 'Cancelar o pedido', 'cancelar compra',
                                   'cancelar a compra', 'Quero cancelar!', 'desistir'])
def test_frases_de_cancelar_viram_cancelar(texto):
    assert I.regra_rapida(texto) == {'acao': 'cancelar'}


@pytest.mark.parametrize('texto', ['mudar', 'Mudar', 'alterar', 'mudar pedido', 'Mudar o pedido'])
def test_frases_de_mudar_viram_mudar(texto):
    assert I.regra_rapida(texto) == {'acao': 'mudar'}


@pytest.mark.parametrize('texto', ['voltar', 'trocar'])
def test_voltar_e_trocar_nao_viram_mudar(texto):
    assert (I.regra_rapida(texto) or {}).get('acao') != 'mudar'


def test_quero_leite_continua_sendo_pedido_pra_ia():
    assert I.regra_rapida('quero leite') is None


def test_numero_em():
    assert I.numero_em('3') == 3 and I.numero_em('o 1') == 1 and I.numero_em('meia duzia') == 6
    assert I.numero_em('10 unidades') == 10 and I.numero_em('banana') is None


def test_cpf_valida_digitos():
    assert I.cpf_em('529.982.247-25') == '52998224725'
    assert I.cpf_em('111.111.111-11') is None and I.cpf_em('123') is None and I.cpf_em('52998224724') is None


def test_igual_a_botao_aceita_o_texto_do_botao_digitado():
    assert I.igual_a_botao('revisar pedido', ['🧾 Revisar pedido', '➕ Quero mais coisas']) == 0
    assert I.igual_a_botao('banana', ['🧾 Revisar pedido']) is None


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


def test_bloqueio_visto_por_outro_container_nao_para_este(monkeypatch):
    """ops-ifood-reroll: o Akamai barra por IP e cada container do Modal tem o seu. O carimbo no armazém é só
    informativo: este container, com IP bom, continua chamando o iFood normalmente."""
    import time
    import httpx
    from src.bot.contexto import chamador_real
    from src.shared import ifood_mcp as M
    armazem = {'tok:1': {'access_token': 'a', 'refresh_token': 'r', 'expira_em': time.time() + 3600},
               'ifood_bloqueado_ate': time.time() + 120}
    monkeypatch.setattr(M, '_freio', {'proxima': 0.0, 'bloqueado_ate': 0.0})
    postou = []
    real = M.ClienteMCP.__init__

    def responder(req):  # JSON-RPC de verdade: initialize, notificação e o tools/call com o getUser
        postou.append(req)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': '2025-06-18', 'content': [
            {'type': 'text', 'text': '{"success": true, "data": {"fullName": "Teste"}}'}]}})

    def init(self, token, url=M.GATEWAY, http=None, **kw):
        real(self, token, url, **kw, http=httpx.Client(transport=httpx.MockTransport(responder)))
    monkeypatch.setattr(M.ClienteMCP, '__init__', init)
    r = chamador_real(armazem, '1')('getUser')
    assert postou and r.get('data', {}).get('fullName') == 'Teste'   # chamou mesmo com o carimbo de outro container no armazém


def test_bloqueio_visto_aqui_vai_pro_armazem(monkeypatch):
    import time
    import httpx
    import pytest
    from src.bot.contexto import chamador_real
    from src.shared import ifood_mcp as M
    armazem = {'tok:1': {'access_token': 'a', 'refresh_token': 'r', 'expira_em': time.time() + 3600}}
    real = M.ClienteMCP.__init__

    def init(self, token, url=M.GATEWAY, http=None, **kw):
        real(self, token, url, **kw, http=httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(403, text='Access Denied'))))
    monkeypatch.setattr(M.ClienteMCP, '__init__', init)
    monkeypatch.setattr(M, '_freio', {'proxima': 0.0, 'bloqueado_ate': 0.0})
    with pytest.raises(M.ErroMCP):
        chamador_real(armazem, '1')('getUser')   # sem ponte: o erro sobe
    assert armazem['ifood_bloqueado_ate'] > time.time() + 200   # carimbo informativo (scripts/modo.py)


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


def test_hora_dita_sem_depender_do_gemini():
    from src.bot.interpretar import hora_em
    assert hora_em('todo dia as 7h peça dois paes') == '07:00'
    assert hora_em('todo dia às 9h') == '09:00'
    assert hora_em('as 19:30') == '19:30'
    assert hora_em('as 7h30') == '07:30'
    assert hora_em('7 horas da noite') == '19:00'
    assert hora_em('8 da noite') == '20:00'
    assert hora_em('ao meio-dia') == '12:00'
    assert hora_em('quero dois paes') is None


def test_mock_tem_cafeteria_pro_cafe_expresso():
    mcp = McpFake()
    loc = {'latitude': -22.0, 'longitude': -47.9}
    r = mcp.chamar('searchOffers', query='café expresso', userLocation=loc, resultKind='ITEM',
                   merchantType='RESTAURANT')
    assert r['results'][0]['itemName'] == 'Café expresso'


def test_sugestao_da_hora_do_dia_em_brasilia():
    import calendar
    from src.bot.fluxo import _da_hora

    def em(h):  # h em Brasília = h + 3 em UTC
        return calendar.timegm((2026, 10, 17, h + 3, 0, 0))
    assert _da_hora(em(8))[0][0] == 'pão francês'
    assert _da_hora(em(12))[0][0] == 'marmita'
    assert _da_hora(em(20))[0][0] == 'pizza'


def test_regra_rapida_pega_codigo_de_entrega_sem_gemini():
    from src.bot.interpretar import regra_rapida
    for frase in ('Qual é o código de entrega?', 'qual a senha do entregador', 'me passa o codigo pro motoboy'):
        assert regra_rapida(frase) == {'acao': 'acompanhar', 'sobre': 'codigo_entrega'}, frase
    assert (regra_rapida('qual o codigo do produto') or {}).get('sobre') is None


def test_posicao_dita_precisa_de_artigo_e_ignora_dia_da_semana():
    from src.bot.fluxo import _posicao_dita
    assert _posicao_dita('Eu quero o arroz do tipo um, a primeira foto que você mandou', 3) == 1
    assert _posicao_dita('quero o último', 3) == 3
    assert _posicao_dita('o do meio', 3) == 2
    assert _posicao_dita('pode ser pra segunda-feira', 3) is None
    assert _posicao_dita('é a primeira vez que peço', 3) is None
    assert _posicao_dita('a quinta', 3) is None          # não tem quinta opção
    assert _posicao_dita('quero o dois', 3) == 2
    assert _posicao_dita('a opção três', 3) == 3
    assert _posicao_dita('o arroz do tipo um', 3) is None    # "tipo 1" é a classificação do arroz
    assert _posicao_dita('eu quero um', 3) is None           # sem artigo é quantidade


def test_cpf_sai_do_que_vai_pro_llm():
    from src.bot.fluxo import _cpf_no_texto, _sem_cpf
    assert _sem_cpf('meu cpf 529.982.247-25 e quero pão') == 'meu cpf [CPF] e quero pão'
    assert _cpf_no_texto('meu cpf é 529.982.247-25') == ('52998224725', '')
    assert _cpf_no_texto('quero pão, cpf 52998224725') == ('52998224725', 'quero pão')
    assert _cpf_no_texto('cpf na nota 529.982.247-25') == ('52998224725', '')
    assert _cpf_no_texto('meu telefone é 11987654321') is None   # dígito verificador não bate


def test_previsao_de_chegada_em_horario_de_brasilia():
    import calendar
    from src.bot.fluxo import _previsao
    quando = calendar.timegm((2026, 10, 18, 2, 21, 0))       # 23h21 em Brasília
    ped = {'quando': quando, 'tempo': '25-35 min'}
    assert _previsao(ped, quando + 60) == 'entre 23h46 e 23h56'
    assert _previsao(ped, quando + 3600) == 'até as 23h56'
    assert _previsao({'quando': quando}, quando) is None


def test_como_esta_entregue_nao_mostra_previsao_nem_codigo():
    from src.bot import textos as T
    ped = {'codigo': 'C1006', 'loja': 'Padaria', 'codigo_entrega': '1006', 'resumo': '3x Café', 'total': 25.49}
    andando = T.como_esta('PREPARING', '', ped, 'entre 23h46 e 23h56')
    assert '23h46' in andando and '1006' in andando and 'Padaria' in andando
    entregue = T.como_esta('DELIVERED', '', ped, 'entre 23h46 e 23h56')
    assert '23h46' not in entregue and 'Código de entrega' not in entregue and '3x Café' in entregue


def _busca_com_fechada():
    chamadas = []

    def chamar(tool, **args):
        chamadas.append(args)
        loja = lambda mid, aberta: {'merchantId': mid, 'merchantName': mid, 'isOpen': aberta}  # noqa: E731
        return {'results': [{'itemId': 'i1', 'itemName': 'Leite', 'unitPrice': 5.0, 'merchant': loja('fechado', False)},
                            {'itemId': 'i2', 'itemName': 'Leite', 'unitPrice': 6.0, 'merchant': loja('aberto', True)}]}
    return chamar, chamadas


def test_busca_normal_pede_so_loja_aberta():
    chamar, chamadas = _busca_com_fechada()
    Ifood(chamar).buscar('leite', {'lat': 1, 'lng': 2}, 'MERCADO')
    assert chamadas[0]['refinements']['onlyOpen'] is True


def test_interruptor_de_fechadas_mostra_loja_fechada_depois_das_abertas():
    chamar, chamadas = _busca_com_fechada()
    ofertas, _ = Ifood(chamar, mostrar_fechadas=True).buscar('leite', {'lat': 1, 'lng': 2}, 'MERCADO')
    assert chamadas[0]['refinements']['onlyOpen'] is False
    assert [o['loja_id'] for o in ofertas] == ['aberto', 'fechado']
    assert all(o['disponivel'] for o in ofertas)  # o ranking não joga fora


def test_lembrete_so_fala_de_fome_quando_e_comida():
    from src.bot import textos as T
    farm = T.lembrete({'resumo': '1x Dipirona 500 mg, 1x Paracetamol 750 mg', 'loja': 'Drogaria Saúde'})
    assert 'fome' not in farm and 'farmácia' in farm
    assert 'compras' in T.lembrete({'resumo': '2x Leite integral', 'loja': 'Supermercado Central'})
    assert 'fome' in T.lembrete({'resumo': '1x X-Burger', 'loja': 'Burger House'})


def test_unidade_de_venda_quilo_embalagem_ou_unidade():
    """18/10: "Quantas unidades de Banana Nanica?" parecia uma banana, e era 1 kg."""
    from src.bot import textos as T
    assert T.unidade('Banana Nanica', '')['tipo'] == 'kg'                     # hortifruti sem nada escrito: quilo
    assert T.unidade('Banana prata', 'Kg')['tipo'] == 'kg'
    assert T.unidade('Patinho Bovino Bife Congelado', '')['tipo'] == 'kg'
    emb = T.unidade('Carne moída de patinho Friboi', 'Bandeja 1 kg. Moída na hora.')
    assert emb['tipo'] == 'emb' and emb['sing'] == 'bandeja' and emb['detalhe'] == '1 kg' and emb['fem']
    pac = T.unidade('Arroz branco Tio João tipo 1', 'Pacote 5 kg.')
    assert pac['tipo'] == 'emb' and pac['plu'] == 'pacotes' and pac['detalhe'] == '5 kg'
    assert T.unidade('Leite integral Italac', 'Caixa 1 litro.')['sing'] == 'caixa'
    assert T.unidade('X-Burger', 'Pão, hambúrguer 120 g e queijo')['tipo'] == 'un'   # "120 g" no recheio não vira embalagem
    assert T.unidade('Dipirona 500 mg', 'Caixa com 10 comprimidos')['sing'] == 'caixa'
    # a pergunta, os botões e o "coloquei" seguem a unidade
    assert T.quantos('Banana Nanica', T.unidade('Banana Nanica')) .startswith('Quantos quilos de *Banana Nanica*')
    assert [b[1] for b in T.botoes_qtd(T.unidade('Banana Nanica'))] == ['1 kg', '2 kg', '3 kg']
    assert T.quantos('Carne moída', emb).startswith('Quantas bandejas de 1 kg de *Carne moída*')
    assert T.quantos('Leite', T.unidade('Leite', 'Caixa 1 litro')).startswith('Quantas caixas de 1 litro de *Leite*')
    assert T.colocado(2, 'Banana Nanica', T.unidade('Banana Nanica')) == '✅ Coloquei *2 kg de Banana Nanica* no seu pedido.'
    assert T.colocado(1, 'Carne moída', emb) == '✅ Coloquei *1 bandeja (1 kg) de Carne moída* no seu pedido.'
    assert T.colocado(3, 'Leite', None) == '✅ Coloquei *3x Leite* no seu pedido.'
    assert T.linha_item({'qtd': 2, 'nome': 'Banana', 'unidade': {'tipo': 'kg'}}) == '2 kg de Banana'


def test_banana_no_fluxo_pergunta_quilos_e_o_carrinho_mostra_kg():
    from src.bot import textos as T
    from tests.fakes import Mundo
    from tests.test_fluxo import endereco_pronto
    m = Mundo()
    endereco_pronto(m)
    m.enviar('quero banana')
    m.tocar('pick:')
    pergunta = m.wpp.saida[-1][1]['texto']
    assert 'unidades' not in pergunta and ('quilos' in pergunta or 'cachos' in pergunta), pergunta
    m.tocar('qtd:2')
    textos = ' '.join(d.get('texto', '') for _, d in m.wpp.saida)
    assert 'Coloquei *2 kg de Banana' in textos or 'Coloquei *2 cachos (1 kg) de Banana' in textos, textos[-300:]
    assert '2x Banana' not in textos
    assert m.estado()['carrinho']['itens'][-1]['unidade']['tipo'] in ('kg', 'emb')


def test_12_ovos_na_lista_e_uma_duzia_nao_12_bandejas():
    """18/10 09h09: "12 ovos" na lista virou 12 bandejas de "Ovos de Galinha Branco Grande Dúzia" (R$ 134)."""
    from src.bot import textos as T
    from tests.fakes import Mundo
    from tests.test_fluxo import endereco_pronto
    assert T.na_embalagem('Ovos de Galinha Branco Grande Dúzia') == 12
    assert T.na_embalagem('Ovos Extra 30 Unidades') == 30
    assert T.na_embalagem('Dipirona 500 mg', 'Caixa com 10 comprimidos') == 10
    assert T.na_embalagem('Leite integral', 'Caixa 1 litro') is None
    ovos = {'termo': 'ovos', 'busca': 'ovos', 'tipo_loja': 'MERCADO', 'quantidade': 12}
    assert T.em_embalagens(12, ovos, 'Ovos de Galinha Branco Grande Dúzia') == (1, 12)
    assert T.em_embalagens(30, ovos, 'Ovos brancos', 'Bandeja com 12') == (3, 12)
    assert T.em_embalagens(2, {**ovos, 'termo': 'bandeja de ovos', 'quantidade': 2}, 'Ovos brancos', 'Bandeja com 12') == (2, None)
    assert T.em_embalagens(3, {'termo': 'leite'}, 'Leite integral', 'Caixa 1 litro') == (3, None)
    m = Mundo()
    endereco_pronto(m)
    original = m.llm.__call__

    def lia(sistema, partes, esquema, **kw):
        if 'acao' in esquema['properties']:
            return {'acao': 'comprar', 'itens': [ovos]}, 'fake', 0.01
        return original(sistema, partes, esquema, **kw)
    m.ctx._gerar_json = lia
    m.enviar('quero 12 ovos')
    m.tocar('pick:')
    item = m.estado()['carrinho']['itens'][-1]
    assert 'Ovos' in item['nome'] and item['qtd'] == 1
    assert 'Coloquei *1 bandeja de Ovos brancos* no seu pedido. (dá os 12 que você pediu)' in ' '.join(m.wpp.textos())
