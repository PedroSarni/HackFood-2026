"""Gemini: texto, áudio e foto entram, JSON sai (com esquema garantido pelo próprio modelo).

Secret Modal `hackathon-gemini`: só a GEMINI_API_KEY, key própria do HackFood (até 17/10 20h
era o `llm-conversor` do handwrite_bot, e a cota dele estourou). Override dos modelos por
BOT_GEMINI_MODELOS="modelo:prazo:pensamento,modelo:prazo:pensamento".

Medido em 2026-10-17 com 12 mensagens típicas de idoso ("qero pao e lete", "o do meio"...):
- gemini-3.1-flash-lite sem thinkingConfig: 12/12 certas, média ~1 s (com thinkingLevel=low, ~1-3 s);
- gemini-3.8-flash: estourou 9 s na maioria e não aceita thinkingLevel=minimal;
- depois de ~30 chamadas seguidas o lite deu 429 (cota): o reserva tem cota própria;
- às 20h27 o 3.1-lite e o 3.8 deram 503 ("high demand") juntos e o bot ficou sem Gemini.
  O gemini-3.5-flash-lite respondeu em ~1,3 s, então entrou como 2º da fila (503 volta em
  ~1,5 s, a fila anda rápido). O 2.5-flash-lite não serve: dá 404 pra key nova.
Por isso o lite é o principal e o 3.8 fica de reserva. No chat a pessoa está esperando:
cada tentativa tem prazo curto e, estourou, vai pro próximo em vez de insistir. Se todos
falharem, o fluxo ainda busca pelo texto cru, se ele for curto (src/bot/fluxo.py, `livre`).
"""
import base64
import json
import os
import time

import httpx

GEMINI = 'https://generativelanguage.googleapis.com/v1beta'
MODELOS = [('gemini-3.1-flash-lite', 6.0, ''), ('gemini-3.5-flash-lite', 6.0, ''),
           ('gemini-3.8-flash', 9.0, 'low')]
MAX_INLINE = 18 * 1024 * 1024


class ErroLLM(Exception):
    pass


def _cfg(nome, padrao=''):
    v = os.environ.get(nome, '')
    return padrao if v in ('', 'PREENCHER') else v


def _modelos():
    bruto = _cfg('BOT_GEMINI_MODELOS')
    if not bruto:
        return MODELOS
    saida = []
    for parte in bruto.split(','):
        nome, _, resto = parte.strip().partition(':')
        prazo, _, pensamento = resto.partition(':')
        saida.append((nome, float(prazo or 8), pensamento))
    return saida


def _partes(partes):
    """('texto', str) | ('arquivo', mime, bytes) -> parts do Gemini."""
    if sum(len(p[2]) for p in partes if p[0] == 'arquivo') > MAX_INLINE:
        raise ErroLLM('mídia grande demais pro pedido inline')
    return [{'text': p[1]} if p[0] == 'texto' else
            {'inline_data': {'mime_type': p[1], 'data': base64.b64encode(p[2]).decode()}}
            for p in partes]


def _chamar(http, modelo, sistema, parts, esquema, prazo, pensamento):
    corpo = {'systemInstruction': {'parts': [{'text': sistema}]},
             'contents': [{'role': 'user', 'parts': parts}],
             'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 2048,
                                  'responseMimeType': 'application/json',
                                  'responseSchema': esquema}}
    if pensamento:
        corpo['generationConfig']['thinkingConfig'] = {'thinkingLevel': pensamento}
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
    Tenta os modelos em ordem; devolve (dados, modelo_usado, segundos)."""
    if not _cfg('GEMINI_API_KEY'):
        raise ErroLLM('GEMINI_API_KEY não configurada')
    http = http or httpx.Client()
    parts = _partes(partes)
    erros = []
    t0 = time.monotonic()
    for modelo, prazo, pensamento in _modelos():
        try:
            return _chamar(http, modelo, sistema, parts, esquema, prazo, pensamento), modelo, time.monotonic() - t0
        except (ErroLLM, httpx.HTTPError) as e:
            if pensamento and 'thinking' in str(e).lower():  # nível não suportado: tenta sem
                try:
                    return (_chamar(http, modelo, sistema, parts, esquema, prazo, ''), modelo,
                            time.monotonic() - t0)
                except (ErroLLM, httpx.HTTPError) as e2:
                    e = e2
            erros.append(f'{modelo}: {e!r}'[:300])
    raise ErroLLM(' | '.join(erros))
