"""Diário do painel: conversa de verdade (Bot + fakes) vira sessão do dash."""
from src.shared import painel
from src.painel.simulador import MundoAnotado
from tests.test_fluxo import pedido_ate_o_resumo


def test_compra_completa_vira_sessao_concluida_com_valor_e_historico():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    [s] = m.sessoes()
    assert s['status'] == 'completed' and s['stage'] == 9
    assert s['amountCents'] > 0 and s['restaurant'] != 'Sem restaurante'
    assert s['city'] == 'São Carlos'
    tipos = [e['type'] for e in s['entries'] if e['kind'] == 'event']
    for t in ('conversation_started', 'recommendations_shown', 'cart_created', 'payment_selected', 'order_confirmed'):
        assert t in tipos
    falas = [e for e in s['entries'] if e['kind'] == 'message']
    assert falas[0]['role'] == 'customer' and any(e['role'] == 'agent' for e in falas)


def test_cpf_digitado_nunca_vai_pro_diario():
    m = pedido_ate_o_resumo(MundoAnotado())
    tudo = repr(m.eventos())
    assert '529.982.247-25' not in tudo and '52998224725' not in tudo


def test_link_de_login_nao_vai_pro_diario():
    m = MundoAnotado(logado=False)
    m.enviar('oi')
    assert 'exemplo.test/login' not in repr(m.eventos())


def test_carrinho_parado_vira_abandono_e_depois_recuperacao():
    m = MundoAnotado()
    from tests.test_fluxo import endereco_pronto
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    assert m.sessoes()[0]['status'] == 'active'
    assert m.sessoes(depois=31 * 60)[0]['status'] == 'abandoned'
    m.agora += 40 * 60  # volta 40 min depois e fecha
    m.tocar('fim')
    m.tocar('pag:0')
    m.enviar('529.982.247-25')
    m.tocar('ok:')
    [s] = m.sessoes()
    assert s['status'] == 'recovered'
    assert 'cart_recovered' in [e['type'] for e in s['entries']]


def test_mensagem_depois_do_pedido_abre_outra_sessao_mas_lembrete_fica_na_mesma():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    m.enviar(('botao', 'rec:0'))   # "Não precisa": ainda é sobre o pedido
    assert len(m.sessoes()) == 1
    m.agora += 60
    m.enviar('quero leite')
    assert len(m.sessoes()) == 2
    assert m.sessoes()[0]['status'] == 'active'


def test_cancelar_com_carrinho_vira_cancelada():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('cancelar')
    assert m.sessoes()[0]['status'] == 'cancelled'


def test_rastreio_entregue_vai_pra_sessao_do_pedido():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    pedido = m.mcp.chamadas_de('submitOrder') and m.rastreios[-1]
    m.agora += 60
    m.enviar('quero leite')   # puxou outra conversa antes da entrega
    m.diario.anotar(m.wa, 'mcp', tool='trackOrder', ok=True, pedido=pedido, status='DELIVERED')
    antiga = next(s for s in m.sessoes() if s['status'] == 'completed')
    assert antiga['stage'] == 10


def test_erro_do_ifood_aparece_e_diario_quebrado_nao_derruba_o_bot():
    class DictQuebrado(dict):
        def update(self, *a, **kw):
            raise RuntimeError('modal fora do ar')
    m = MundoAnotado()
    m.diario.dic = DictQuebrado()
    m.enviar('bom dia')                      # nada estoura
    assert m.wpp.saida
    eventos = [{'ts': 1, 'wa': '1', 'tipo': 'entrada', 'texto': 'oi'},
               {'ts': 2, 'wa': '1', 'tipo': 'mcp', 'tool': 'searchOffers', 'ok': False, 'erro': 'TIMEOUT'}]
    [s] = painel.montar_sessoes(eventos, agora=10)
    assert s['status'] == 'failed' and 'agent_error' in [e['type'] for e in s['entries']]


def test_lembrete_abre_sessao_de_follow_up():
    eventos = [{'ts': 1, 'wa': '1', 'tipo': 'saida', 'texto': 'Podemos pedir?', 'origem': 'lembrete'},
               {'ts': 2, 'wa': '1', 'tipo': 'entrada', 'texto': 'Sim, pode pedir', 'botao': 'lem:pedir:a'},
               {'ts': 3, 'wa': '1', 'tipo': 'mcp', 'tool': 'createCart', 'ok': True, 'total': 30.5, 'loja': 'X'},
               {'ts': 4, 'wa': '1', 'tipo': 'mcp', 'tool': 'submitOrder', 'ok': True, 'pedido': 'p1'}]
    [s] = painel.montar_sessoes(eventos, agora=10)
    assert s['origin'] == 'Follow-up' and s['status'] == 'completed' and s['amountCents'] == 3050


# --- visão MCP do dash (agregada no servidor) ---------------------------------------------

def _mcp(ts, wa, tool, ok=True, ms=100, erro=None):
    return {'ts': ts, 'wa': wa, 'tipo': 'mcp', 'tool': tool, 'ok': ok, 'ms': ms, **({'erro': erro} if erro else {})}


def _diario_de_duas_conversas():
    return [{'ts': 1, 'wa': '1', 'tipo': 'entrada', 'texto': 'oi'},
            _mcp(2, '1', 'searchOffers', ms=200), _mcp(3, '1', 'searchOffers', ok=False, ms=900, erro='TIMEOUT'),
            _mcp(4, '1', 'createCart', ms=300),
            {'ts': 100_000, 'wa': '2', 'tipo': 'entrada', 'texto': 'quero leite'},
            _mcp(100_001, '2', 'searchOffers', ms=400)]


def test_resumo_mcp_conta_por_tool_com_erro_latencia_e_conversas():
    eventos, rotulos = _diario_de_duas_conversas(), {}
    painel.montar_sessoes(eventos, agora=200_000, rotulos=rotulos)
    r = painel.resumo_mcp(eventos, rotulos)
    assert r['total'] == 4 and r['conversas'] == 2
    busca = next(t for t in r['tools'] if t['tool'] == 'searchOffers')
    assert busca == {'tool': 'searchOffers', 'dominio': 'offer_discovery_mcp', 'chamadas': 3, 'pct': 75.0,
                     'erros': 1, 'pctErro': 33.3, 'msMedio': 500, 'msMax': 900, 'conversas': 2,
                     'erroComum': 'TIMEOUT'}
    assert r['tools'][0]['tool'] == 'searchOffers'   # mais chamada primeiro
    assert r['sequencia'] is None                    # sem conversa aberta, sem sequência


def test_tools_da_doc_nunca_chamadas_aparecem_e_a_que_so_existe_na_doc_vem_marcada():
    eventos, rotulos = _diario_de_duas_conversas(), {}
    painel.montar_sessoes(eventos, rotulos=rotulos)
    r = painel.resumo_mcp(eventos, rotulos)
    nunca = {t['tool']: t for t in r['nunca']}
    assert len(painel.tools_da_doc()) == 24          # 23 no servidor + listItemTaxonomy, só na doc
    assert 'searchOffers' not in nunca and 'submitOrder' in nunca
    assert nunca['listItemTaxonomy']['soNaDoc'] and not nunca['submitOrder']['soNaDoc']
    assert len(r['tools']) + len(r['nunca']) == 24


def test_filtro_por_conversa_e_periodo_e_sequencia_na_ordem():
    eventos, rotulos = _diario_de_duas_conversas(), {}
    sessoes = painel.montar_sessoes(eventos, agora=200_000, rotulos=rotulos)
    primeira = next(s['id'] for s in sessoes if s['clientId'] == painel._cliente('1'))
    r = painel.resumo_mcp(eventos, rotulos, conversa=primeira)
    assert r['total'] == 3 and r['conversas'] == 1
    assert [(p['tool'], p['ok']) for p in r['sequencia']] == [('searchOffers', True), ('searchOffers', False),
                                                              ('createCart', True)]
    assert r['sequencia'][1]['erro'] == 'TIMEOUT'
    so_a_segunda = painel.resumo_mcp(eventos, rotulos, de=50_000)
    assert so_a_segunda['total'] == 1 and so_a_segunda['conversas'] == 1
    lista = painel.indice_conversas(eventos, rotulos, sessoes)
    assert [c['mcp'] for c in lista] == [1, 3]       # mais nova primeiro, com quantas chamadas teve
    assert painel.indice_conversas(eventos, rotulos, sessoes, de=50_000)[0]['mcp'] == 1


def test_rotulos_nao_mudam_as_sessoes():
    eventos = _diario_de_duas_conversas()
    assert painel.montar_sessoes(eventos, agora=200_000, rotulos={}) == painel.montar_sessoes(eventos, agora=200_000)


def test_jornada_de_verdade_chega_na_visao_mcp_e_servidor_responde_so_o_resumo():
    from src.painel.servidor import DictTravado, Painel
    m = pedido_ate_o_resumo(MundoAnotado(diario_dic=DictTravado()))
    m.tocar('ok:')

    class Fonte:
        nome, estado = 'demo', 'pronto'

        def novos(self, vistos):
            return m.painel.novos(vistos)
    p = Painel(Fonte())
    p.girar()
    import json
    r = json.loads(p.consulta('mcp'))
    assert r['total'] == len([e for e in m.eventos() if e['tipo'] == 'mcp']) > 0
    assert 'submitOrder' in [t['tool'] for t in r['tools']]
    assert 'sessions' not in r and 'entries' not in json.dumps(r)   # nada de conversa inteira
    [conv] = r['conversasLista']
    aberta = json.loads(p.consulta('mcp', conversa=conv['id']))
    seq = [s['tool'] for s in aberta['sequencia']]
    assert 'submitOrder' in seq and seq.index('searchOffers') < seq.index('submitOrder')
    assert p.consulta('mcp') is p.consulta('mcp')    # em cache até o próximo recálculo


# --- rastro dos agentes de IA -------------------------------------------------------------

def _ia(m):
    return [e for e in m.eventos() if e['tipo'] == 'ia']


def test_cada_modulo_de_ia_vira_o_agente_certo_pelo_prompt_de_sistema():
    from src.bot import foto, grupo, interpretar, relevancia, tutor, voz
    assert [painel.agente_do_sistema(s) for s in (interpretar.SISTEMA, foto.SISTEMA, grupo.SISTEMA, relevancia.SISTEMA,
                                                    relevancia.SISTEMA_VARIOS, tutor.SISTEMA, voz.SISTEMA, 'outro prompt')] == \
        ['entendimento', 'foto', 'grupo', 'relevancia', 'relevancia', 'tutor', 'voz', 'outro']


def test_entendimento_vira_evento_ia_sem_texto_da_pessoa():
    m = MundoAnotado()
    from tests.test_fluxo import endereco_pronto
    endereco_pronto(m)
    m.enviar('quero leite pra minha vó na rua das flores 529.982.247-25')
    ia = [e for e in _ia(m) if e['agente'] == 'entendimento'][-1]
    assert ia['ok'] and ia['modelo'] == 'fake' and isinstance(ia['ms'], int)
    assert ia['acao'] == 'comprar' and ia['itens'] >= 1
    tudo = repr(_ia(m))
    for proibido in ('leite', 'flores', '529', 'vó'):
        assert proibido not in tudo


def test_foto_vira_evento_do_agente_foto_com_o_tipo():
    m = MundoAnotado()
    from tests.test_fluxo import endereco_pronto
    endereco_pronto(m)
    m.enviar(('foto', 'midia1', 'quero esse'))
    foto = [e for e in _ia(m) if e['agente'] == 'foto']
    assert foto and foto[0]['foto'] == 'comida' and foto[0]['parecidos'] == 2
    assert 'quero esse' not in repr(_ia(m)) and 'bacon' not in repr(_ia(m))


def test_ia_fora_do_ar_vira_erro_no_rastro_e_o_bot_segue():
    m = MundoAnotado()
    from tests.test_fluxo import endereco_pronto
    endereco_pronto(m)
    m.llm.falhar = True
    antes = len(m.wpp.saida)
    m.enviar('quero leite')
    assert len(m.wpp.saida) > antes                    # o bot respondeu do mesmo jeito
    erro = [e for e in _ia(m) if not e['ok']]
    assert erro and erro[0]['agente'] == 'entendimento' and erro[0]['erro'] == 'ErroLLM'


def test_rastro_quebrado_nao_derruba_o_bot(monkeypatch):
    class DictQuebrado(dict):
        def update(self, *a, **kw):
            raise RuntimeError('modal fora do ar')
    m = MundoAnotado()
    m.diario.dic = DictQuebrado()
    m.enviar('quero leite')
    assert m.wpp.saida

    def pifou(sistema):
        raise RuntimeError('mapa de agentes pifou')
    monkeypatch.setattr(painel, 'agente_do_sistema', pifou)
    dic = {}
    gerar = painel.espiar_ia(lambda s, p, e, **kw: ([1, 2], 'm', 0.1), painel.Diario(dic, intervalo=None), '1')
    assert gerar('x', [], {}) == ([1, 2], 'm', 0.1)   # resposta estranha e agente desconhecido: passa igual
    [ev] = [v for k, v in dic.items() if k.startswith('ev:')]
    assert ev['agente'] == 'outro' and ev['ok']


def test_modelo_reserva_e_openrouter_aparecem():
    dic = {}
    d = painel.Diario(dic, intervalo=None)
    primeiro = lambda kw: 'gemini-3.5-flash-lite'  # noqa: E731
    painel.espiar_ia(lambda s, p, e, **kw: ({}, 'gemini-3.5-flash-lite', 1), d, '1', primeiro)('x', [], {})
    painel.espiar_ia(lambda s, p, e, **kw: ({}, 'gemini-3.1-flash-lite', 1), d, '1', primeiro)('x', [], {})
    painel.espiar_ia(lambda s, p, e, **kw: ({}, 'openrouter:anthropic/claude-haiku-5.5', 1), d, '1', primeiro)('x', [], {})
    evs = sorted((v for k, v in dic.items() if k.startswith('ev:')), key=lambda e: e['ts'])
    assert [e.get('reserva') for e in evs] == [None, True, True]
    assert evs[2]['modelo'] == 'openrouter:anthropic/claude-haiku-5.5'

    def tudo_caiu(s, p, e, **kw):
        from src.shared.llm import ErroLLM
        raise ErroLLM("gemini-3.5-flash-lite: ErroLLM('x HTTP 503: alta demanda') | openrouter a: ErroLLM('y')")
    try:
        painel.espiar_ia(tudo_caiu, d, '1', primeiro)('x', [], {})
    except Exception:  # noqa: BLE001 - o erro sobe igual pro fluxo
        pass
    ultimo = max((v for k, v in dic.items() if k.startswith('ev:')), key=lambda e: e['ts'])
    assert ultimo['ok'] is False and ultimo['erro'] == 'HTTP 503' and ultimo['tentativas'] == 2


def test_primeiro_modelo_da_fila(monkeypatch):
    from src.bot.contexto import _primeiro_modelo
    from src.shared import llm
    monkeypatch.setenv('GEMINI_API_KEY', 'k')
    monkeypatch.delenv('BOT_GEMINI_MODELOS', raising=False)
    monkeypatch.delenv('BOT_LLM', raising=False)
    assert _primeiro_modelo({}) == llm.MODELOS[0][0]
    assert _primeiro_modelo({'modelos': [('gemini-x', 3.0, '')]}) == 'gemini-x'
    monkeypatch.setenv('GEMINI_API_KEY', '')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'k')
    monkeypatch.delenv('OPENROUTER_MODELOS', raising=False)
    assert _primeiro_modelo({}) == f'openrouter:{llm.OPENROUTER_MODELOS[0]}'


def test_ouvido_e_voz_viram_agentes():
    m = MundoAnotado(transcritor=lambda mime, dados: 'quero leite', locutor=lambda texto: None)
    from tests.test_fluxo import endereco_pronto
    endereco_pronto(m)
    m.enviar(('audio', 'a1'))
    ouvido = [e for e in _ia(m) if e['agente'] == 'ouvido']
    assert ouvido and ouvido[0]['ok'] and ouvido[0]['modelo'] == 'fake'
    assert 'leite' not in repr(ouvido)
    d = painel.Diario({}, intervalo=None)
    falar = painel.espiar_servico(lambda texto: None, d, '1', 'voz', 'elevenlabs:x')
    assert falar('oi') is None    # sem áudio: o fluxo manda escrito, o rastro marca que não veio
    [ev] = [v for k, v in d.dic.items() if k.startswith('ev:')]
    assert ev['agente'] == 'voz' and ev['ok'] is False and ev['erro'] == 'sem resposta'


def test_eventos_ia_nao_mudam_as_sessoes():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    com = m.eventos()
    sem = [e for e in com if e['tipo'] != 'ia']
    assert len(sem) < len(com)
    assert painel.montar_sessoes(com, agora=m.agora) == painel.montar_sessoes(sem, agora=m.agora)


def test_resumo_agentes_uso_regras_e_linha_do_tempo():
    from src.bot.textos import VITRINE_TOPO
    eventos = [{'ts': 1, 'wa': '1', 'tipo': 'entrada', 'texto': 'oi', 'formato': 'Texto'},
               {'ts': 2, 'wa': '1', 'tipo': 'saida', 'texto': VITRINE_TOPO, 'formato': 'Cards'},
               {'ts': 10, 'wa': '1', 'tipo': 'entrada', 'texto': 'quero pizza', 'formato': 'Texto'},
               {'ts': 11, 'wa': '1', 'tipo': 'ia', 'agente': 'entendimento', 'modelo': 'g1', 'ok': True, 'ms': 800, 'acao': 'comprar', 'itens': 1},
               {'ts': 12, 'wa': '1', 'tipo': 'mcp', 'tool': 'searchOffers', 'ok': True, 'ms': 300},
               {'ts': 13, 'wa': '1', 'tipo': 'ia', 'agente': 'relevancia', 'modelo': 'g2', 'reserva': True, 'ok': True, 'ms': 1200, 'mantidas': 3},
               {'ts': 14, 'wa': '1', 'tipo': 'ia', 'agente': 'relevancia', 'ok': False, 'ms': 4000, 'erro': 'timeout'},
               {'ts': 15, 'wa': '1', 'tipo': 'saida', 'texto': 'Achei estas', 'formato': 'Cards'},
               {'ts': 200, 'wa': '1', 'tipo': 'saida', 'texto': 'Ainda está por aí?', 'formato': 'Botões', 'origem': 'followup'},
               {'ts': 201, 'wa': '1', 'tipo': 'saida', 'texto': 'Qual?', 'formato': 'Botões', 'origem': 'followup'},
               {'ts': 900, 'wa': '1', 'tipo': 'saida', 'texto': 'Esvaziei', 'formato': 'Botões', 'origem': 'followup'}]
    rotulos = {}
    [s] = painel.montar_sessoes(eventos, agora=1000, rotulos=rotulos)
    r = painel.resumo_agentes(eventos, rotulos)
    assert r['total'] == 3
    por = {a['agente']: a for a in r['agentes']}
    assert set(painel.AGENTES) <= set(por)              # todos aparecem, mesmo sem chamada
    assert por['relevancia']['chamadas'] == 2 and por['relevancia']['pct'] == 66.7
    assert por['relevancia']['erros'] == 1 and por['relevancia']['msMax'] == 4000 and por['relevancia']['reserva'] == 1
    assert por['entendimento']['modelos'] == [{'modelo': 'g1', 'n': 1}] and por['foto']['chamadas'] == 0
    regras = {x['agente']: x['disparos'] for x in r['regras']}
    assert regras == {'followup': 2, 'recorrencia': 0, 'vitrine': 1}   # 200 e 201 são o mesmo disparo
    assert r['linha'] is None
    aberta = painel.resumo_agentes(eventos, rotulos, conversa=s['id'])
    assert [p['tipo'] for p in aberta['linha'][:9]] == ['mensagem', 'regra', 'resposta', 'mensagem', 'ia', 'mcp', 'ia', 'ia', 'resposta']
    assert aberta['linha'][4]['resumo'] == {'acao': 'comprar', 'itens': 1}
    assert 'quero pizza' not in repr(aberta) and 'Achei estas' not in repr(aberta)


def test_servidor_responde_agentes_da_jornada_de_verdade():
    from src.painel.servidor import DictTravado, Painel
    import json
    m = pedido_ate_o_resumo(MundoAnotado(diario_dic=DictTravado()))

    class Fonte:
        nome, estado = 'demo', 'pronto'

        def novos(self, vistos):
            return m.painel.novos(vistos)
    p = Painel(Fonte())
    p.girar()
    r = json.loads(p.consulta('agentes'))
    assert r['total'] == len(_ia(m)) > 0 and r['conversasLista'][0]['ia'] == r['total']
    aberta = json.loads(p.consulta('agentes', conversa=r['conversasLista'][0]['id']))
    tipos = [x['tipo'] for x in aberta['linha']]
    assert tipos[0] == 'mensagem' and 'ia' in tipos and 'mcp' in tipos and tipos[-1] == 'resposta'
