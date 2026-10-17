"""Gemini: texto, áudio e foto entram, JSON sai (com esquema garantido pelo próprio modelo).

Secret Modal `llm-conversor` (o mesmo do handwrite_bot, já pago):
  GEMINI_API_KEY           chave do AI Studio
  GEMINI_MODELO            principal (padrão abaixo)
  GEMINI_MODELO_RESERVA    tentado quando o principal falha ou demora

Lição do handwrite: o Gemini às vezes devolve 503 de "alta demanda" ou fica minutos sem
responder. No chat a pessoa está esperando, então cada tentativa tem prazo curto e, estourou,
vai pro modelo reserva em vez de insistir.
"""
import base64
import json
import os
import time

import httpx

GEMINI = 'https://generativelanguage.googleapis.com/v1beta'
MODELO = 'gemini-3.8-flash'
RESERVA = 'gemini-3.1-flash-lite'
PRAZO = (9.0, 7.0)          # segundos por tentativa: principal, reserva
MAX_INLINE = 18 * 1024 * 1024


class ErroLLM(Exception):
    pass


def _cfg(nome, padrao=''):
    v = os.environ.get(nome, '')
    return padrao if v in ('', 'PREENCHER') else v


def _partes(partes):
    """('texto', str) | ('arquivo', mime, bytes) -> parts do Gemini."""
    if sum(len(p[2]) for p in partes if p[0] == 'arquivo') > MAX_INLINE:
        raise ErroLLM('mídia grande demais pro pedido inline')
    return [{'text': p[1]} if p[0] == 'texto' else
            {'inline_data': {'mime_type': p[1], 'data': base64.b64encode(p[2]).decode()}}
            for p in partes]


def _chamar(http, modelo, sistema, parts, esquema, prazo):
    corpo = {'systemInstruction': {'parts': [{'text': sistema}]},
             'contents': [{'role': 'user', 'parts': parts}],
             'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 2048,
                                  'responseMimeType': 'application/json',
                                  'responseSchema': esquema}}
    nivel = _cfg('GEMINI_PENSAMENTO')  # 'low', 'minimal'... vazio = padrão do modelo
    if nivel:
        corpo['generationConfig']['thinkingConfig'] = {'thinkingLevel': nivel}
    r = http.post(f'{GEMINI}/models/{modelo}:generateContent',
                  headers={'x-goog-api-key': _cfg('GEMINI_API_KEY')}, json=corpo, timeout=prazo)
    if r.status_code >= 400:
        try:
            msg = (r.json().get('error') or {}).get('message') or r.text
        except ValueError:
            msg = r.text
        raise ErroLLM(f'{modelo} HTTP {r.status_code}: {" ".join(str(msg).split())[:200]}')
    j = r.json()
    cand = (j.get('candidates') or [{}])[0]
    if cand.get('finishReason') not in (None, 'STOP'):
        raise ErroLLM(f'{modelo} finishReason={cand.get("finishReason")}')
    txt = ''.join(p.get('text', '') for p in (cand.get('content') or {}).get('parts', [])
                  if not p.get('thought'))
    try:
        return json.loads(txt)
    except ValueError as e:
        raise ErroLLM(f'{modelo} devolveu JSON inválido: {txt[:120]!r}') from e


def gerar_json(sistema, partes, esquema, http=None):
    """Uma resposta JSON no formato `esquema` (OpenAPI do Gemini: type OBJECT, STRING...).
    Tenta o principal e depois o reserva; devolve (dados, modelo_usado, segundos)."""
    if not _cfg('GEMINI_API_KEY'):
        raise ErroLLM('GEMINI_API_KEY não configurada')
    http = http or httpx.Client()
    parts = _partes(partes)
    modelos = [(_cfg('GEMINI_MODELO', MODELO), PRAZO[0]),
               (_cfg('GEMINI_MODELO_RESERVA', RESERVA), PRAZO[1])]
    erros = []
    t0 = time.monotonic()
    for modelo, prazo in modelos:
        try:
            return _chamar(http, modelo, sistema, parts, esquema, prazo), modelo, time.monotonic() - t0
        except (ErroLLM, httpx.HTTPError) as e:
            erros.append(f'{modelo}: {e!r}'[:300])
    raise ErroLLM(' | '.join(erros))
