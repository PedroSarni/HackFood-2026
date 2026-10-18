"""Claude na frente da fila, Gemini de reserva, e o sino do dash quando os créditos acabam (src/shared/llm.py)."""
import json
from types import SimpleNamespace

import anthropic
import httpx
import httpx2
import pytest

from src.shared import alertas, llm
from tests.fakes import Armazem

ESQUEMA = {'type': 'OBJECT', 'properties': {'acao': {'type': 'STRING', 'enum': ['sim', 'nao']},
                                           'hora': {'type': 'STRING', 'nullable': True},
                                           'itens': {'type': 'ARRAY', 'items': {
                                               'type': 'OBJECT', 'properties': {'termo': {'type': 'STRING'}},
                                               'required': ['termo']}}},
           'required': ['acao']}
SEM_CREDITO = 'Your credit balance is too low to access the Anthropic API.'


class ClaudeFalso:
    """No lugar do anthropic.Anthropic: anota os pedidos e responde (ou levanta) o que o teste mandar."""

    def __init__(self, resposta='{"acao": "sim"}', erro=None):
        self.resposta, self.erro, self.pedidos, self.prazos = resposta, erro, [], []
        self.messages = SimpleNamespace(create=self._criar)

    def with_options(self, timeout=None, **_):
        self.prazos.append(timeout)
        return self

    def _criar(self, **pedido):
        self.pedidos.append(pedido)
        if self.erro:
            raise self.erro
        return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=self.resposta)])


def erro_api(status, tipo, msg):
    body = {'type': 'error', 'error': {'type': tipo, 'message': msg}}
    resp = httpx2.Response(status, request=httpx2.Request('POST', 'https://api.anthropic.com/v1/messages'), json=body)
    classe = {400: anthropic.BadRequestError, 401: anthropic.AuthenticationError, 402: anthropic.APIStatusError,
              429: anthropic.RateLimitError}[status]
    return classe(msg, response=resp, body=body)


def gemini_ok():
    pedidos = []

    def responder(req):
        pedidos.append(req)
        txt = json.dumps({'acao': 'nao'})
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': txt}]}}]})
    return httpx.Client(transport=httpx.MockTransport(responder)), pedidos


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-teste')
    monkeypatch.setenv('GEMINI_API_KEY', 'g')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.delenv('BOT_GEMINI_MODELOS', raising=False)
    monkeypatch.delenv('BOT_LLM', raising=False)
    arm = Armazem()
    monkeypatch.setattr(llm, '_claude', {'fora_ate': 0.0, 'motivo': None, 'alertou': False, 'cliente': None})
    monkeypatch.setattr(llm, 'avisar', lambda *a: alertas.registrar(arm, *a))

    def usar(falso):
        llm._claude['cliente'] = falso
        return falso
    usar.armazem = arm
    return usar


def test_claude_responde_primeiro_sem_pensar_e_com_esquema_fechado(claude):
    falso = claude(ClaudeFalso())
    http, gemini = gemini_ok()
    dados, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert dados == {'acao': 'sim'} and modelo == llm.CLAUDE and not gemini
    p = falso.pedidos[0]
    assert p['model'] == 'claude-sonnet-5-5' and p['system'] == 'sis'
    assert p['thinking'] == {'type': 'between_tools'} and p['output_config']['effort'] == 'low'
    esquema = p['output_config']['format']['schema']
    assert esquema['additionalProperties'] is False
    assert esquema['properties']['itens']['items']['additionalProperties'] is False
    assert esquema['properties']['hora'] == {'anyOf': [{'type': 'string'}, {'type': 'null'}]}
    assert falso.prazos == [llm.MODELOS[0][1]]


def test_sem_credito_o_gemini_assume_o_claude_sai_da_fila_e_o_dash_e_avisado_uma_vez(claude):
    falso = claude(ClaudeFalso(erro=erro_api(400, 'invalid_request_error', SEM_CREDITO)))
    http, gemini = gemini_ok()
    dados, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert dados == {'acao': 'nao'} and modelo.startswith('gemini') and len(gemini) == 1
    dados, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert modelo.startswith('gemini') and len(falso.pedidos) == 1   # pausado: nem tenta o Claude de novo
    a = alertas.listar(claude.armazem)
    assert a['naoLidas'] == 1 and a['alertas'][0]['tipo'] == 'claude_sem_credito'
    assert 'créditos' in a['alertas'][0]['titulo'] and a['alertas'][0]['nivel'] == 'erro'


def test_claude_volta_depois_da_pausa_e_avisa_que_voltou(claude, monkeypatch):
    falso = claude(ClaudeFalso(erro=erro_api(400, 'invalid_request_error', SEM_CREDITO)))
    http, _ = gemini_ok()
    llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    falso.erro = None
    llm._claude['fora_ate'] = 0.0   # passou a pausa (recarregaram os créditos)
    _, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert modelo == llm.CLAUDE
    assert [a['tipo'] for a in alertas.listar(claude.armazem)['alertas']] == ['claude_voltou', 'claude_sem_credito']


def test_key_recusada_tambem_avisa_e_rate_limit_so_desvia(claude):
    claude(ClaudeFalso(erro=erro_api(429, 'rate_limit_error', 'slow down')))
    http, _ = gemini_ok()
    _, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert modelo.startswith('gemini') and not alertas.listar(claude.armazem)['alertas']
    llm._claude['fora_ate'] = 0.0
    claude(ClaudeFalso(erro=erro_api(401, 'authentication_error', 'invalid x-api-key')))
    llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert alertas.listar(claude.armazem)['alertas'][0]['tipo'] == 'claude_key'


def test_audio_pula_o_claude_e_foto_vai_pra_ele(claude):
    falso = claude(ClaudeFalso())
    http, gemini = gemini_ok()
    _, modelo, _ = llm.gerar_json('sis', [('texto', 'oi'), ('arquivo', 'audio/ogg', b'ogg')], ESQUEMA, http=http)
    assert modelo.startswith('gemini') and not falso.pedidos and len(gemini) == 1
    _, modelo, _ = llm.gerar_json('sis', [('arquivo', 'image/jpeg', b'jpg'), ('texto', 'isso')], ESQUEMA, http=http)
    bloco = falso.pedidos[0]['messages'][0]['content'][0]
    assert modelo == llm.CLAUDE and bloco['type'] == 'image' and bloco['source']['media_type'] == 'image/jpeg'


def test_sem_key_do_claude_a_fila_segue_no_gemini(claude, monkeypatch):
    falso = claude(ClaudeFalso())
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'PREENCHER')
    http, _ = gemini_ok()
    _, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert modelo.startswith('gemini') and not falso.pedidos


def test_alerta_repetido_junta_e_lido_some_da_contagem():
    arm = Armazem()
    alertas.registrar(arm, 'claude_sem_credito', 'Acabaram os créditos do Claude', 'x', agora=1000)
    alertas.registrar(arm, 'claude_sem_credito', 'Acabaram os créditos do Claude', 'y', agora=1600)
    a = alertas.listar(arm)
    assert len(a['alertas']) == 1 and a['alertas'][0]['vezes'] == 2 and a['naoLidas'] == 1
    assert alertas.marcar_lidas(arm)['naoLidas'] == 0
    alertas.registrar(arm, 'claude_sem_credito', 'Acabaram os créditos do Claude', 'z', agora=2000)
    assert len(alertas.listar(arm)['alertas']) == 2   # já lido: o aviso novo aparece de novo


def test_rotas_do_sino_listam_e_marcam_como_lidas():
    from fastapi.testclient import TestClient

    from src.painel.servidor import criar_api
    arm = Armazem()
    alertas.registrar(arm, 'claude_sem_credito', 'Acabaram os créditos do Claude', 'HTTP 400 credit balance')
    cli = TestClient(criar_api({'real': SimpleNamespace(fonte=SimpleNamespace(armazem=lambda: arm))}))
    r = cli.get('/api/alertas').json()
    assert r['naoLidas'] == 1 and r['alertas'][0]['titulo'] == 'Acabaram os créditos do Claude'
    assert cli.post('/api/alertas/lidas', headers={'origin': 'https://exemplo.com'}).status_code == 403
    assert cli.post('/api/alertas/lidas').json()['naoLidas'] == 0
    assert cli.get('/api/alertas?fonte=demo').status_code == 404


def test_haiku_desliga_o_pensamento_do_jeito_dele(claude):
    # 18/10 08h50: o Haiku 5.5 recusa thinking "between_tools" (HTTP 400, e o bot cairia na reserva, mais lento);
    # desligado ele aceita, e respondeu em ~1 s nos prompts da Duda. O Sonnet continua com between_tools.
    falso = claude(ClaudeFalso())
    http, gemini = gemini_ok()
    dados, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http,
                                      modelos=[(llm.CLAUDE_RAPIDO, 6.0, ''), (llm.CLAUDE, 8.0, '')])
    assert dados == {'acao': 'sim'} and modelo == 'claude-haiku-5-5' and not gemini
    p = falso.pedidos[0]
    assert p['model'] == 'claude-haiku-5-5' and p['thinking'] == {'type': 'disabled'}
    assert p['output_config']['effort'] == 'low' and p['output_config']['format']['type'] == 'json_schema'
    assert falso.prazos == [6.0]
