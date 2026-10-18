"""A Analista do dash (src/painel/analista.py) e a rota POST /api/insights."""
import json

import pytest

from src import agentes
from src.painel import analista

DADOS = {'periodoDias': 30, 'conversas': 820, 'conversao': 31.5, 'abandonados': 140,
         'motivosAbandono': [{'motivo': 'Pagamento recusado', 'conversas': 52}]}


def resposta_boa(**extra):
    return {'resumo': 'Muita gente para no pagamento.', 'insights': [
        {'titulo': 'Pagamento derruba o funil', 'time': 'Produto', 'evidencia': '52 de 140 abandonos no pagamento',
         'acao': 'Testar Pix como 1ª opção no bot', 'impacto': 'alto', 'prazo': 'esta semana',
         'metrica': 'abandono no pagamento', **extra}]}


def test_analisar_manda_a_pagina_e_os_numeros_e_limpa_a_resposta():
    pedidos = []

    def gerar(sistema, partes, esquema, **kw):
        pedidos.append((sistema, partes[0][1], esquema))
        r = resposta_boa(time='Time inventado', impacto='gigante')
        r['insights'].append({'titulo': '', 'acao': ''})           # vazio: some
        return r, 'gemini-3.8-flash', 4.21
    r = analista.analisar('conversao', DADOS, gerar)
    assert pedidos[0][0] == analista.SISTEMA and '"motivosAbandono"' in pedidos[0][1] and 'Conversão' in pedidos[0][1]
    assert agentes.do_sistema(pedidos[0][0]) == 'analista'
    [i] = r['insights']
    assert i['time'] == 'Produto' and i['impacto'] == 'médio'      # fora da lista cai no padrão
    assert r['modelo'] == 'gemini-3.8-flash' and r['segundos'] == 4.2


def test_analisar_recusa_pagina_desconhecida_base_inteira_e_resposta_vazia():
    with pytest.raises(analista.EntradaRuim):
        analista.analisar('financeiro', DADOS, None)
    with pytest.raises(analista.EntradaRuim):
        analista.analisar('mercado', {'linhas': ['x' * 100] * 500}, None)
    with pytest.raises(ValueError):
        analista.analisar('mercado', DADOS, lambda *a, **k: ({'resumo': 'oi', 'insights': []}, 'm', 1))


def test_analista_tem_ficha_com_fila_propria():
    ficha = agentes.POR_ID['analista']
    assert ficha.nome == 'Sofia' and agentes.fila('analista', env={})[0][0] == 'gemini-3.8-flash'


def test_rota_de_insights_cacheia_avisa_desligado_e_so_aceita_local():
    from fastapi.testclient import TestClient

    from src.painel.servidor import criar_api
    chamadas = []

    def fake(pagina, dados):
        chamadas.append((pagina, dados))
        return {'erro': 'desligado'} if dados.get('desligar') else {**resposta_boa(), 'modelo': 'm', 'segundos': 1}
    cli = TestClient(criar_api({}, analista=fake))
    corpo = {'pagina': 'conversao', 'dados': DADOS}
    r1 = cli.post('/api/insights?fonte=demo', json=corpo).json()
    r2 = cli.post('/api/insights?fonte=demo', json=corpo).json()
    assert r1['insights'][0]['time'] == 'Produto' and r2['cache'] is True and len(chamadas) == 1
    assert chamadas[0][1]['demo'] is True
    cli.post('/api/insights?fonte=demo', json={**corpo, 'novo': True})
    assert len(chamadas) == 2                                      # "gerar de novo" fura o cache
    assert cli.post('/api/insights', json={'pagina': 'conversao', 'dados': {'desligar': 1}}).status_code == 409
    assert cli.post('/api/insights', json={'pagina': 'financeiro', 'dados': {}}).status_code == 400
    assert cli.post('/api/insights', json=corpo, headers={'origin': 'https://malvado.test'}).status_code == 403
    grande = {'pagina': 'mercado', 'dados': {'x': 'y' * 40000}}
    assert cli.post('/api/insights', json=grande).status_code == 413
    assert len(chamadas) == 3
    assert json.dumps(chamadas).count('malvado') == 0
