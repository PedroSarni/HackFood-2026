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
# 17/10 23h: o 3.1-lite passou a estourar 6 s seguidos e o 3.5-lite responde em ~1,2 s: o 3.5 vai na frente
MODELOS = [('gemini-3.5-flash-lite', 6.0, ''), ('gemini-3.1-flash-lite', 4.0, ''),
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


# --- quebra-galho: OpenRouter --------------------------------------------------------------
# 17/10 23h45: o Gemini estourando (timeout/503) deixava o bot mudo. Secret `hackathon-openrouter`
# (OPENROUTER_API_KEY; vazia ou PREENCHER = desligado). Entra DEPOIS que a fila do Gemini falha.
# BOT_LLM=openrouter pula o Gemini (debug). OPENROUTER_MODELOS="a,b" troca a fila.
# Fila padrão: o mesmo 3.5-flash-lite por outra infraestrutura/cota, e o Haiku, de outro fornecedor.
OPENROUTER = 'https://openrouter.ai/api/v1/chat/completions'
OPENROUTER_MODELOS = ['google/gemini-3.5-flash-lite', 'anthropic/claude-haiku-5.5']
OPENROUTER_PRAZO = 8.0


def _esquema_json(e):
    """Esquema OpenAPI do Gemini (type OBJECT, nullable) -> JSON Schema (type object, [t, null])."""
    if not isinstance(e, dict):
        return e
    s = {}
    for k, v in e.items():
        if k == 'type':
            s['type'] = str(v).lower()
        elif k == 'properties':
            s['properties'] = {n: _esquema_json(p) for n, p in v.items()}
        elif k == 'items':
            s['items'] = _esquema_json(v)
        elif k in ('required', 'enum', 'description'):
            s[k] = v
    if e.get('nullable') and 'type' in s:
        s['type'] = [s['type'], 'null']
        if 'enum' in s:
            s['enum'] = list(s['enum']) + [None]
    return s


def _conteudo_openrouter(partes):
    """Texto e foto vão; áudio não (o Scribe já transcreve antes; aqui só sobra o caso raro)."""
    saida = []
    for p in partes:
        if p[0] == 'texto':
            saida.append({'type': 'text', 'text': p[1]})
        elif str(p[1]).startswith('image/'):
            saida.append({'type': 'image_url',
                          'image_url': {'url': f'data:{p[1]};base64,{base64.b64encode(p[2]).decode()}'}})
        else:
            saida.append({'type': 'text', 'text': '(a pessoa mandou um áudio que não deu pra ouvir)'})
    return saida


def _chamar_openrouter(http, modelo, sistema, partes, esquema, prazo):
    corpo = {'model': modelo, 'temperature': 0.1, 'max_tokens': 2048,
             'messages': [{'role': 'system', 'content': sistema + '\nResponda SÓ o JSON, sem texto em volta.'},
                          {'role': 'user', 'content': _conteudo_openrouter(partes)}],
             'response_format': {'type': 'json_schema',
                                 'json_schema': {'name': 'resposta', 'strict': False, 'schema': _esquema_json(esquema)}}}
    r = http.post(OPENROUTER, json=corpo, timeout=prazo,
                  headers={'Authorization': f'Bearer {_cfg("OPENROUTER_API_KEY")}', 'X-Title': 'HackFood bot'})
    if r.status_code >= 400:
        raise ErroLLM(f'openrouter {modelo} HTTP {r.status_code}: {" ".join(r.text.split())[:200]}')
    try:
        txt = r.json()['choices'][0]['message']['content'] or ''
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ErroLLM(f'openrouter {modelo} resposta estranha: {r.text[:120]!r}') from e
    txt = txt.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:
        return json.loads(txt)
    except ValueError as e:
        raise ErroLLM(f'openrouter {modelo} devolveu JSON inválido: {txt[:120]!r}') from e


def _fila_openrouter():
    if not _cfg('OPENROUTER_API_KEY'):
        return []
    return [m.strip() for m in (_cfg('OPENROUTER_MODELOS') or ','.join(OPENROUTER_MODELOS)).split(',') if m.strip()]


def gerar_json(sistema, partes, esquema, http=None, modelos=None):
    """Uma resposta JSON no formato `esquema` (OpenAPI do Gemini: type OBJECT, STRING...).
    Tenta os modelos em ordem; devolve (dados, modelo_usado, segundos).
    modelos: fila própria [(modelo, prazo, pensamento)] pra quem tem pressa (roteiro do áudio).
    Toda a fila do Gemini falhou: tenta o OpenRouter, se houver key (quebra-galho)."""
    fila_or = _fila_openrouter()
    so_openrouter = _cfg('BOT_LLM') == 'openrouter' and fila_or
    if not _cfg('GEMINI_API_KEY') and not fila_or:
        raise ErroLLM('GEMINI_API_KEY não configurada')
    http = http or httpx.Client()
    erros = []
    t0 = time.monotonic()
    if _cfg('GEMINI_API_KEY') and not so_openrouter:
        parts = _partes(partes)
        for modelo, prazo, pensamento in modelos or _modelos():
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
    for modelo in fila_or:
        try:
            dados = _chamar_openrouter(http, modelo, sistema, partes, esquema, OPENROUTER_PRAZO)
            if erros:
                print(f'gemini falhou, openrouter {modelo} salvou: {erros[-1][:150]}')
            return dados, f'openrouter:{modelo}', time.monotonic() - t0
        except (ErroLLM, httpx.HTTPError) as e:
            erros.append(f'openrouter {modelo}: {e!r}'[:300])
    raise ErroLLM(' | '.join(erros))
