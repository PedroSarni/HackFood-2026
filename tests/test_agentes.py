"""O time de agentes (src/agentes/): ficha por agente, liga/desliga e fila de modelos própria."""
import pytest

from src import agentes
from src.shared.llm import ErroLLM
from tests.fakes import Armazem, Mundo
from tests.test_fluxo import endereco_pronto


def test_cada_prompt_de_sistema_aponta_pro_seu_agente():
    vistos = {}
    for a in agentes.TODOS:
        for p in a.prompts():
            assert agentes.do_sistema(p) == a.id
            assert p not in vistos, f'{a.id} e {vistos.get(p)} com o mesmo prompt'
            vistos[p] = a.id
    assert {a.id for a in agentes.TODOS if a.tipo == 'ia'} == {'entendimento', 'foto', 'relevancia', 'grupo',
                                                                'tutor', 'voz'}
    assert agentes.do_sistema('prompt que ninguém tem') == 'outro'


def test_desligado_nao_chama_a_ia_e_cai_no_plano_b():
    chamadas, pulados = [], []
    gerar = agentes.roteador(lambda *a, **kw: chamadas.append(kw) or ({}, 'm', 0.1),
                             {'foto': {'ligado': False}}, ao_pular=pulados.append)
    foto = agentes.POR_ID['foto'].prompts()[0]
    with pytest.raises(ErroLLM):   # Desligado é ErroLLM: todo `except ErroLLM` do fluxo já trata
        gerar(foto, [], {})
    assert chamadas == [] and pulados == ['foto']
    gerar(agentes.POR_ID['tutor'].prompts()[0], [], {})   # os outros seguem
    assert len(chamadas) == 1


def test_fila_e_so_do_agente():
    env = {'AGENTE_FOTO_MODELOS': 'gemini-3.8-flash:12:low'}
    assert agentes.fila('foto', env=env) == [('gemini-3.8-flash', 12.0, 'low')]
    assert agentes.fila('entendimento', env=env)[0][0] != 'gemini-3.8-flash'   # trocar a foto não mexe no resto
    voz = agentes.POR_ID['voz'].extra['fila_do_codigo']()
    assert agentes.fila('voz', pedida=voz, env={}) == voz                      # o roteiro curto da voz é respeitado
    cfg = {'foto': {'modelo': 'gemini-3.8-flash'}}
    f = agentes.fila('foto', cfg, env={})
    assert f[0][0] == 'gemini-3.8-flash' and len({m[0] for m in f}) == len(f)  # principal na frente, sem repetir

    vistas = []
    gerar = agentes.roteador(lambda s, p, e, **kw: vistas.append(kw['modelos']) or ({}, 'm', 0.1), cfg)
    gerar(agentes.POR_ID['foto'].prompts()[0], [], {})
    assert vistas[0][0][0] == 'gemini-3.8-flash'


def test_definir_guarda_no_armazem_e_mascara_a_key():
    arm = Armazem()
    agentes.definir(arm, 'grupo', ligado=False)
    agentes.definir(arm, 'grupo', modelo='gemini-3.8-flash')
    cfg = agentes.config(arm)
    assert not agentes.ligado(cfg, 'grupo') and cfg['grupo']['modelo'] == 'gemini-3.8-flash'
    assert agentes.ligado(cfg, 'foto')
    agentes.definir(arm, 'grupo', ligado=True, limpar_modelo=True)
    assert agentes.config(arm)['grupo'] == {'ligado': True}
    with pytest.raises(KeyError):
        agentes.definir(arm, 'hacker', ligado=False)
    k = agentes.chave_mascarada('GEMINI_API_KEY', {'GEMINI_API_KEY': 'AIzaSecretoa91F'})
    assert k == {'nome': 'GEMINI_API_KEY', 'secret': 'hackathon-gemini', 'configurada': True, 'final': '····a91F'}
    assert agentes.chave_mascarada('GEMINI_API_KEY', {'GEMINI_API_KEY': 'PREENCHER'})['configurada'] is False


def test_ficha_do_ar_nunca_leva_a_key_inteira():
    env = {'GEMINI_API_KEY': 'AIzaSecretoLongo1234', 'ELEVENLABS_API_KEY': 'sk_eleven_9876'}
    foto = agentes.foto_do_ar(env)
    assert 'AIzaSecretoLongo1234' not in repr(foto) and 'sk_eleven_9876' not in repr(foto)
    assert foto['agentes']['foto']['keys'][0]['final'] == '····1234'
    arm = Armazem()
    agentes.publicar_ar(arm, 1000.0)
    agentes.publicar_ar(arm, 1100.0)   # menos de 5 min: não regrava
    assert arm[agentes.CHAVE_AR]['quando'] == 1000.0
    f = agentes.fichas({'foto': {'ligado': False}}, arm[agentes.CHAVE_AR])
    ficha = next(a for a in f['agentes'] if a['id'] == 'foto')
    assert ficha['ligado'] is False and ficha['keysDoAr'] and ficha['prompts'] and ficha['versaoPrompt']


def test_bot_segue_com_o_entendimento_desligado():
    m = Mundo()
    endereco_pronto(m)
    m.ctx._gerar_json = agentes.roteador(m.llm, {'entendimento': {'ligado': False}})
    antes = m.llm.chamadas
    m.wpp.saida.clear()
    m.enviar('leite')            # texto curto: vira busca direta, sem IA
    assert m.wpp.saida
    assert not any(p[0] == agentes.POR_ID['entendimento'].prompts()[0] for p in m.llm.prompts[antes:])


def test_dash_desliga_agente_na_demo_e_o_passo_aparece_ao_vivo():
    import json
    import time as _t

    from fastapi.testclient import TestClient

    from src.painel.servidor import DictTravado, Painel, criar_api
    from src.painel.simulador import MundoAnotado

    m = MundoAnotado(diario_dic=DictTravado())
    m.agora = _t.time()

    class Fonte:
        nome, estado = 'demo', 'pronto'

        def novos(self, vistos):
            return m.painel.novos(vistos)

        def armazem(self):
            return m.painel
    p = Painel(Fonte())
    cli = TestClient(criar_api({'demo': p}))
    r = cli.post('/api/equipe/entendimento?fonte=demo', json={'ligado': False}).json()
    lia = next(a for a in r['agentes'] if a['id'] == 'entendimento')
    assert lia['ligado'] is False and lia['nome'] == 'Lia' and lia['prompts']
    assert cli.post('/api/equipe/foto?fonte=demo', json={'modelo': 'qualquer-um'}).status_code == 400
    assert cli.post('/api/equipe/foto?fonte=demo', content='ligado=0',
                    headers={'content-type': 'application/x-www-form-urlencoded'}).status_code == 415
    assert cli.post('/api/equipe/foto?fonte=demo', json={'ligado': False},
                    headers={'origin': 'https://site-malvado.test'}).status_code == 403

    endereco_pronto(m)
    m.enviar('quero leite integral bem gelado pra hoje')   # frase longa: a Lia seria chamada, mas está desligada
    p.girar()
    passos = json.loads(cli.get('/api/ao-vivo?fonte=demo&desde=0').text)['passos']
    pulo = [x for x in passos if x['tipo'] == 'ia' and x.get('erro') == 'desligado']
    assert pulo and pulo[0]['agente'] == 'entendimento'
    assert 'leite' not in json.dumps(passos)   # sem texto de ninguém
    assert json.loads(cli.get('/api/equipe?fonte=demo').text)['agentes'][0]['ligado'] is False
