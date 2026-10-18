"""Rotinas automáticas no painel: cutucada, carrinho esquecido, lembrete de recompra e rastreio (o que o bot faz
sozinho), da mensagem marcada no diário até o resumo que o dash desenha (src/shared/painel.resumo_rotinas)."""
import json
import random

import pytest

from src.bot import recorrencia
from src.bot import textos as T
from src.painel import simulador
from src.painel.simulador import MundoAnotado
from src.shared import painel
from tests.test_fluxo import pedido_ate_o_resumo

AGORA = 1_900_000_000.0


def _saida(ts, wa, origem=None, texto='Tá com fome de quê?', formato='Botões'):
    return {'ts': ts, 'wa': wa, 'tipo': 'saida', 'texto': texto, 'formato': formato, **({'origem': origem} if origem else {})}


def _entrada(ts, wa, botao=None):
    return {'ts': ts, 'wa': wa, 'tipo': 'entrada', 'texto': 'x', **({'botao': botao} if botao else {})}


def _mcp(ts, wa, tool, **kw):
    return {'ts': ts, 'wa': wa, 'tipo': 'mcp', 'tool': tool, 'ok': True, **kw}


def _varredura(ts, **kw):
    return {'ts': ts, 'wa': '', 'tipo': 'rotina', 'nome': 'lembretes', 'a_cada': 900, **kw}


@pytest.fixture(autouse=True)
def _sem_template(monkeypatch):
    monkeypatch.delenv('TEMPLATE_LEMBRETE', raising=False)


def test_cada_mensagem_automatica_vira_a_rotina_certa():
    assert painel.rotina_da_saida(_saida(1, 'a', 'followup', T.AINDA_AI)) == 'cutucada'
    assert painel.rotina_da_saida(_saida(1, 'a', 'followup', T.CARRINHO_ABANDONADO + '\n\nE agora?')) == 'abandono'
    assert painel.rotina_da_saida(_saida(1, 'a', 'abandono', T.CARRINHO_ABANDONADO)) == 'abandono'
    assert painel.rotina_da_saida(_saida(1, 'a', 'lembrete')) == 'lembrete'
    assert painel.rotina_da_saida(_saida(1, 'a', texto=T.lembrete({'resumo': '2x Pão'}))) == 'lembrete'  # mostrado na volta
    assert painel.rotina_da_saida(_saida(1, 'a', 'rastreio')) == 'rastreio'
    assert painel.rotina_da_saida(_saida(1, 'a')) is None
    assert painel.regra_da_saida(_saida(1, 'a', 'abandono')) == 'followup'   # a visão de regras segue somando os dois


def test_resumo_conta_disparos_desfechos_canais_e_a_varredura():
    h = AGORA - 5 * 3600
    ev = [
        _saida(h, 'a', 'followup', T.AINDA_AI), _saida(h + 5, 'a', 'followup', T.AINDA_AI),  # mesma rajada: 1 disparo
        _entrada(h + 100, 'a'),                                                          # voltou a falar
        _saida(h + 1000, 'b', 'followup', T.AINDA_AI),                                   # ninguém respondeu
        _saida(AGORA - 60, 'c', 'followup', T.AINDA_AI),                                 # ainda dá tempo
        _saida(h + 2000, 'a', 'abandono', T.CARRINHO_ABANDONADO), _entrada(h + 2500, 'a'),
        _mcp(h + 2600, 'a', 'submitOrder', pedido='p1'),                                   # voltou e comprou
        _saida(h + 4000, 'd', 'lembrete'), _entrada(h + 4100, 'd', 'lem:pedir:x1'), _mcp(h + 4110, 'd', 'submitOrder', pedido='p2'),
        _saida(h + 5000, 'e', texto=T.lembrete({'resumo': 'pão'})), _entrada(h + 5050, 'e', 'lem:parar:y1'),
        _mcp(h + 6000, 'a', 'trackOrder', pedido='p1', status='DISPATCHED'), _saida(h + 6001, 'a', 'rastreio'),
        _mcp(h + 7000, 'a', 'trackOrder', pedido='p1', status='DELIVERED'), _saida(h + 7001, 'a', 'rastreio'),
        _varredura(h + 8000, janela=1, template=0, adiado=2, erro=0, ativos=5, pessoas=3, vencidos=2, proximo=AGORA + 86400),
    ]
    r = painel.resumo_rotinas(ev, {id(e): f'conv-{e["wa"]}' for e in ev}, de=AGORA - 86400, agora=AGORA,
                              nomes={'conv-a': 'Dona Cida'})
    por = {x['id']: x for x in r['rotinas']}
    assert list(por) == ['cutucada', 'abandono', 'lembrete', 'rastreio']
    cut = por['cutucada']
    assert cut['disparos'] == 3 and cut['conversas'] == 3
    assert cut['resultados'] == {'voltou': 1, 'sem resposta': 1, 'esperando': 1}
    assert cut['destaque'] == {'rotulo': 'voltaram a falar', 'n': 1, 'de': 2, 'pct': 50.0}
    assert '3 min' in cut['quando'] and len(cut['serie']) == 24 and sum(cut['serie']) == 3   # último dia: por hora
    assert por['abandono']['resultados'] == {'comprou': 1}
    lem = por['lembrete']
    assert lem['resultados'] == {'comprou': 1, 'parou': 1} and lem['canais'] == {'na janela': 1, 'na volta': 1}
    assert lem['destaque']['rotulo'] == 'viraram pedido' and lem['destaque']['pct'] == 50.0
    ras = por['rastreio']
    assert ras['disparos'] == 2 and ras['resultados'] == {'DISPATCHED': 1, 'DELIVERED': 1}
    assert ras['destaque'] == {'rotulo': 'pedidos entregues', 'n': 1, 'de': 1, 'pct': 100.0}
    v = r['varredura']
    assert v['aCada'] == 900 and v['esperando'] == 2 and v['ativos'] == 5 and v['avisados'] == 1 and v['proximo']
    assert r['disparos'][0]['rotina'] == 'cutucada' and r['disparos'][0]['resultado'] == 'esperando'   # mais novo primeiro
    assert any(d['nome'] == 'Dona Cida' for d in r['disparos'])
    assert T.AINDA_AI not in json.dumps(r, ensure_ascii=False)   # nenhum texto da conversa


def test_disparo_fora_do_periodo_nao_conta_mas_a_ultima_passada_do_cron_aparece():
    ev = [_saida(AGORA - 3 * 86400, 'a', 'followup', T.AINDA_AI), _varredura(AGORA - 3 * 86400)]
    dia = painel.resumo_rotinas(ev, {}, de=AGORA - 86400, agora=AGORA)
    assert dia['rotinas'][0]['disparos'] == 0 and dia['disparos'] == []
    assert dia['varredura']['ultima'] and dia['varredura']['execucoes'] == 0   # diz se o cron está vivo
    semana = painel.resumo_rotinas(ev, {}, de=AGORA - 7 * 86400, agora=AGORA)
    assert semana['rotinas'][0]['disparos'] == 1 and len(semana['rotinas'][0]['serie']) == 7
    assert painel.resumo_rotinas([], {}, agora=AGORA)['varredura'] is None


def test_varredura_vai_pro_diario_sem_virar_sessao_e_nunca_derruba_o_cron():
    dic = {}
    diario = painel.Diario(dic, agora=lambda: AGORA, intervalo=None)
    painel.anotar_varredura(diario, {'janela': 1, 'template': 0, 'adiado': 2, 'erro': 0}, 900,
                            {'ativos': 3, 'proximo': AGORA + 60})
    [ev] = [v for k, v in dic.items() if k.startswith('ev:')]
    assert ev['tipo'] == 'rotina' and ev['wa'] == '' and ev['adiado'] == 2 and ev['ativos'] == 3
    assert painel.montar_sessoes([ev], agora=AGORA) == []

    class Quebrado:
        def anotar(self, *a, **k):
            raise RuntimeError('caiu')
    painel.anotar_varredura(Quebrado(), {'janela': 1})


def test_agenda_conta_ligados_vencidos_e_o_proximo():
    dic = {'a': [{'proximo': AGORA - 10, 'avisado': False}, {'proximo': AGORA + 500}],
           'b': [{'proximo': AGORA + 100}, {'proximo': AGORA - 5, 'avisado': True}], 'c': []}
    assert recorrencia.agenda(dic, AGORA) == {'ativos': 4, 'pessoas': 2, 'vencidos': 1, 'proximo': AGORA + 100}

    class Caido(dict):
        def keys(self):
            raise RuntimeError('Modal fora')
    assert recorrencia.agenda(Caido()) == {}


# --- a demo dispara as rotinas com as mesmas funções do bot ------------------------------------

def test_quem_cala_leva_a_cutucada_e_depois_perde_o_carrinho():
    m = pedido_ate_o_resumo(MundoAnotado())
    assert simulador.calar(m, ritmo=0, volta=0) == 'carrinho esquecido'
    saidas = [e for e in m.eventos() if e['tipo'] == 'saida' and e.get('origem')]
    assert [painel.rotina_da_saida(e) for e in saidas] == ['cutucada', 'abandono']
    assert saidas[1]['ts'] - saidas[0]['ts'] == pytest.approx(120, abs=1)
    assert not (m.estado().get('carrinho') or {}).get('itens')
    por = {x['id']: x for x in painel.resumo_rotinas(m.eventos(), {}, agora=m.agora)['rotinas']}
    assert por['cutucada']['disparos'] == 1 and por['abandono']['disparos'] == 1


def test_quem_volta_depois_da_cutucada_fecha_o_pedido_e_conta_como_voltou():
    random.seed(1)
    m = pedido_ate_o_resumo(MundoAnotado())
    assert simulador.calar(m, ritmo=0, volta=1) == 'voltou e comprou'
    por = {x['id']: x for x in painel.resumo_rotinas(m.eventos(), {}, agora=m.agora)['rotinas']}
    assert por['cutucada']['resultados'] == {'voltou': 1} and por['abandono']['disparos'] == 0


def test_cron_da_demo_adia_fora_da_janela_e_o_lembrete_aparece_na_volta():
    dic = {}
    m = simulador._cliente(dic, 0)
    m.agora = AGORA - 3600                                         # a última conversa dela foi há 1h
    m.recs_dic[m.wa] = [{'id': 'r1', 'pedido_id': None, 'dias': 7, 'resumo': '2x Pão francês', 'loja': 'Padaria',
                         'total': 5.0, 'proximo': AGORA - 60, 'avisado': False, 'loja_id': None, 'itens': None}]
    total = simulador.varrer(dic, [m], AGORA)
    assert total['adiado'] == 1 and total['janela'] == 0          # ninguém falou com o bot nas últimas 24h
    assert m.agora == AGORA - 3600      # só adiou: o relógio dela não anda (senão ela nunca mais puxava conversa)
    [ev] = [e for e in m.eventos() if e['tipo'] == 'rotina']
    assert ev['adiado'] == 1 and ev['vencidos'] == 1 and ev['ativos'] == 1
    m.agora = AGORA + 600
    simulador._passo(m, 0, 'oi')                                   # a pessoa volta: o lembrete aparece
    assert [painel.rotina_da_saida(e) for e in m.eventos() if e['tipo'] == 'saida'] == ['lembrete']


def test_historico_da_demo_tem_lembrete_ligado_mostrado_na_volta_e_respondido():
    dic = {}
    clientes = [simulador._cliente(dic, n) for n in range(5)]
    simulador.preencher_historico(dic, dias=21, conversas=120, semente=3, clientes=clientes)
    eventos = [v for k, v in dic.items() if k.startswith('ev:')]
    botoes = [str(e.get('botao') or '') for e in eventos if e['tipo'] == 'entrada']
    assert any(b.startswith('rec:') and b != 'rec:0' for b in botoes)          # alguém ligou o lembrete
    lem = {x['id']: x for x in painel.resumo_rotinas(eventos, {})['rotinas']}['lembrete']
    assert lem['disparos'] > 0 and (lem['canais'] or {}).get('na volta')         # venceu, esperou e apareceu na volta
    assert any(b.startswith('lem:') for b in botoes)                             # e a pessoa respondeu
    assert [e for e in eventos if e['tipo'] == 'rotina']                         # o cron deixou rastro


def test_cache_da_demo_traz_clientes_e_lembretes_pra_hoje():
    dic = {}
    m = simulador._cliente(dic, 3)
    m.armazem[f'u:{m.wa}'] = {'ultima_msg': AGORA - 100, 'fase': 'pedido'}
    m.recs_dic[m.wa] = [{'id': 'r1', 'proximo': AGORA + 3600}]
    salvos = json.loads(json.dumps(simulador.guardar_clientes([m]), default=list))
    [volta] = simulador.restaurar_clientes(dic, salvos, desvio=1000)
    assert (volta.wa, volta.nome, volta._fixo) == (m.wa, m.nome, None)
    assert volta.recs_dic[m.wa][0]['proximo'] == AGORA + 4600
    assert volta.armazem[f'u:{m.wa}']['ultima_msg'] == AGORA + 900


# --- o servidor do dash ------------------------------------------------------------------------

def test_servidor_responde_as_rotinas_e_o_ao_vivo_marca_qual_disparou():
    from fastapi.testclient import TestClient

    from src.painel.servidor import DictTravado, Painel, criar_api
    m = pedido_ate_o_resumo(MundoAnotado(diario_dic=DictTravado()))
    simulador.calar(m, ritmo=0, volta=0)

    class Fonte:
        nome, estado = 'demo', 'pronto'

        def novos(self, vistos):
            return m.painel.novos(vistos)
    p = Painel(Fonte())
    p.girar()
    cli = TestClient(criar_api({'demo': p}))
    r = cli.get('/api/rotinas?fonte=demo&dias=30').json()
    por = {x['id']: x for x in r['rotinas']}
    assert por['cutucada']['disparos'] == 1 and por['abandono']['disparos'] == 1
    assert r['disparos'][0]['rotina'] == 'abandono' and r['disparos'][0]['nome'] and r['disparos'][0]['conversa']
    assert 'sessions' not in r and 'Ainda está por aí' not in json.dumps(r, ensure_ascii=False)
    passos = cli.get('/api/ao-vivo?fonte=demo').json()['passos']
    assert [s['rotina'] for s in passos if s.get('rotina')] == ['cutucada', 'abandono']
    assert cli.get('/api/rotinas?fonte=nenhuma').status_code == 404
