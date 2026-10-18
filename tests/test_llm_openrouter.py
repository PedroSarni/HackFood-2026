"""Quebra-galho do OpenRouter: o Gemini estourou, o bot não fica mudo (src/shared/llm.py)."""
import json

import httpx
import pytest

from src.shared import llm

ESQUEMA = {'type': 'OBJECT', 'properties': {'acao': {'type': 'STRING', 'enum': ['sim', 'nao']},
                                           'hora': {'type': 'STRING', 'nullable': True}}, 'required': ['acao']}


def cliente(gemini_status=503):
    pedidos = []

    def responder(req):
        pedidos.append(req)
        if 'googleapis' in str(req.url):
            return httpx.Response(gemini_status, json={'error': {'message': 'high demand'}})
        corpo = json.loads(req.content)
        assert corpo['response_format']['json_schema']['schema']['properties']['hora']['type'] == ['string', 'null']
        return httpx.Response(200, json={'choices': [{'message': {'content': '```json\n{"acao": "sim"}\n```'}}]})
    return httpx.Client(transport=httpx.MockTransport(responder)), pedidos


@pytest.fixture
def chaves(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'g')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'o')
    monkeypatch.delenv('BOT_LLM', raising=False)
    monkeypatch.delenv('OPENROUTER_MODELOS', raising=False)


def test_gemini_fora_o_openrouter_responde(chaves):
    http, pedidos = cliente()
    dados, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert dados == {'acao': 'sim'} and modelo == f'openrouter:{llm.OPENROUTER_MODELOS[0]}'
    assert sum('googleapis' in str(p.url) for p in pedidos) == len(llm.MODELOS)  # tentou o Gemini antes


def test_sem_key_do_openrouter_continua_so_gemini(chaves, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PREENCHER')
    http, pedidos = cliente()
    with pytest.raises(llm.ErroLLM):
        llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert not any('openrouter' in str(p.url) for p in pedidos)


def test_bot_llm_openrouter_pula_o_gemini(chaves, monkeypatch):
    monkeypatch.setenv('BOT_LLM', 'openrouter')
    http, pedidos = cliente()
    dados, modelo, _ = llm.gerar_json('sis', [('texto', 'pode')], ESQUEMA, http=http)
    assert dados == {'acao': 'sim'} and not any('googleapis' in str(p.url) for p in pedidos)
