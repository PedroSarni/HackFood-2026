"""LLM do bot: texto, áudio e foto entram, JSON sai (com esquema garantido pelo próprio modelo).

18/10: o Claude Sonnet 5.5 (secret `hackathon-anthropic`, ANTHROPIC_API_KEY) é o 1º de toda fila e o
Gemini virou reserva. Áudio pula o Claude (a API não ouve). Sem crédito ou com a key recusada, o Claude
sai da fila por CLAUDE_PAUSA e o dash recebe um alerta (`avisar`, ligado em src/shared/alertas.py).

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
CLAUDE = 'claude-sonnet-5-5'
CLAUDE_FORTE = 'claude-fable-5-1'   # 18/10 09h30: só o Beto (kit em grupo) vai de Fable, a pedido do Fabio
CLAUDE_RAPIDO = 'claude-haiku-5-5'  # 18/10 08h40: quem tem pressa (roteiro da voz, filtro de relevância) vai de Haiku
# 17/10 23h: o 3.1-lite passou a estourar 6 s seguidos e o 3.5-lite responde em ~1,2 s: o 3.5 vai na frente
MODELOS = [(CLAUDE, 8.0, ''), ('gemini-3.5-flash-lite', 6.0, ''), ('gemini-3.1-flash-lite', 4.0, ''),
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
             # 2048 estourou no 3.5-flash-lite às 22h38 (MAX_TOKENS: gastou pensando); o JSON é pequeno
             'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 4096,
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


# --- principal: Claude ----------------------------------------------------------------------
# pensamento '' = sem pensar (between_tools, effort low: é o mais rápido, ~1,6 s medido em 18/10);
# 'low'/'medium'/'high' = pensa (adaptive) com esse effort. Sem retry do SDK: a fila já é o retry.
CLAUDE_PAUSA = 600       # s fora da fila depois de "sem crédito" ou key recusada (e um alerta só)
CLAUDE_PAUSA_429 = 60    # rate limit: sai rapidinho e o Gemini segura
_claude = {'fora_ate': 0.0, 'motivo': None, 'alertou': False, 'cliente': None}
avisar = None            # (tipo, titulo, detalhe) -> None; a produção liga no armazém (src/shared/alertas.py)


def _e_claude(modelo):
    return str(modelo).startswith('claude-')


def _claude_pronto():
    return bool(_cfg('ANTHROPIC_API_KEY')) and time.time() >= _claude['fora_ate']


def _alertar(tipo, titulo, detalhe=''):
    if avisar:
        try:
            avisar(tipo, titulo, detalhe)
        except Exception as e:  # noqa: BLE001 - alerta é bônus, a resposta segue pelo Gemini
            print(f'alerta {tipo} falhou: {e!r}')


def _tirar_claude(segundos, motivo, alerta=None):
    _claude['fora_ate'] = time.time() + segundos
    _claude['motivo'] = motivo
    print(f'claude fora da fila por {segundos}s: {motivo[:200]}')
    if alerta:
        _claude['alertou'] = True
        _alertar(*alerta, motivo[:300])


def _esquema_claude(e):
    """Esquema OpenAPI do Gemini -> JSON Schema da saída estruturada do Claude (objetos fechados, nullable = anyOf)."""
    if not isinstance(e, dict):
        return e
    s = {}
    if 'type' in e:
        s['type'] = str(e['type']).lower()
    if 'properties' in e:
        s['properties'] = {n: _esquema_claude(p) for n, p in e['properties'].items()}
        s['additionalProperties'] = False
    if 'items' in e:
        s['items'] = _esquema_claude(e['items'])
    for k in ('required', 'enum', 'description'):
        if k in e:
            s[k] = e[k]
    if e.get('nullable'):
        desc = s.pop('description', None)
        s = {'anyOf': [s, {'type': 'null'}]}
        if desc:
            s['description'] = desc
    return s


def _conteudo_claude(partes):
    """Texto, foto e PDF; com áudio devolve None (o Claude não ouve: a fila segue pro Gemini)."""
    saida = []
    for p in partes:
        if p[0] == 'texto':
            if p[1]:
                saida.append({'type': 'text', 'text': p[1]})
            continue
        dado = base64.b64encode(p[2]).decode()
        if str(p[1]).startswith('image/'):
            saida.append({'type': 'image', 'source': {'type': 'base64', 'media_type': p[1], 'data': dado}})
        elif p[1] == 'application/pdf':
            saida.append({'type': 'document', 'source': {'type': 'base64', 'media_type': p[1], 'data': dado}})
        else:
            return None
    return saida


def _cliente_claude():
    if _claude['cliente'] is None:
        import anthropic
        _claude['cliente'] = anthropic.Anthropic(api_key=_cfg('ANTHROPIC_API_KEY'), max_retries=0)
    return _claude['cliente']


def _chamar_claude(modelo, sistema, conteudo, esquema, prazo, pensamento):
    import anthropic
    pedido = {'model': modelo, 'max_tokens': 8192, 'system': sistema,
              'messages': [{'role': 'user', 'content': conteudo}],
              'output_config': {'effort': pensamento or 'low',
                                'format': {'type': 'json_schema', 'schema': _esquema_claude(esquema)}}}
    if not pensamento:
        # sem pensar: o Sonnet 5.5 só aceita "between_tools" (disabled dá 400); o Haiku 5.5 é o contrário
        # (between_tools dá 400, 18/10 08h50; desligado ele aceita e respondeu em ~1 s nos prompts da Duda)
        pedido['thinking'] = {'type': 'disabled'} if 'haiku' in modelo else {'type': 'between_tools'}
    try:
        r = _cliente_claude().with_options(timeout=prazo).messages.create(**pedido)
    except anthropic.APIStatusError as e:
        msg = f'{modelo} HTTP {e.status_code} {e.type}: {" ".join(str(e.message).split())[:200]}'
        texto = str(e.message).lower()
        if e.status_code == 402 or e.type == 'billing_error' or 'credit balance' in texto:
            _tirar_claude(CLAUDE_PAUSA, msg, ('claude_sem_credito', 'Acabaram os créditos do Claude'))
        elif e.status_code in (401, 403):
            _tirar_claude(CLAUDE_PAUSA, msg, ('claude_key', 'A key do Claude foi recusada'))
        elif e.status_code == 429:
            _tirar_claude(CLAUDE_PAUSA_429, msg)
        raise ErroLLM(msg) from e
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        raise ErroLLM(f'{modelo}: {e!r}'[:200]) from e
    if _claude['alertou']:  # voltou depois de uma pausa por crédito/key: avisa uma vez
        _alertar('claude_voltou', 'O Claude voltou a responder', 'O bot já está usando o Claude de novo.')
    _claude.update(motivo=None, alertou=False)
    if r.stop_reason in ('refusal', 'max_tokens'):
        raise ErroLLM(f'{modelo} stop_reason={r.stop_reason}')
    txt = next((b.text for b in r.content if b.type == 'text'), '')
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
    Claude e Gemini dividem a fila (o nome diz quem é); falhou tudo: OpenRouter, se houver key (quebra-galho)."""
    fila_or = _fila_openrouter()
    so_openrouter = _cfg('BOT_LLM') == 'openrouter' and fila_or
    if not _cfg('GEMINI_API_KEY') and not _cfg('ANTHROPIC_API_KEY') and not fila_or:
        raise ErroLLM('nenhuma key de LLM configurada (ANTHROPIC_API_KEY, GEMINI_API_KEY)')
    http = http or httpx.Client()
    erros = []
    t0 = time.monotonic()
    if not so_openrouter:
        parts = conteudo = None
        for modelo, prazo, pensamento in modelos or _modelos():
            if _e_claude(modelo):
                if not _claude_pronto():
                    continue
                conteudo = conteudo if conteudo is not None else _conteudo_claude(partes) or []
                if not conteudo:  # áudio: o Claude não ouve, quem atende é o Gemini
                    continue
                try:
                    return (_chamar_claude(modelo, sistema, conteudo, esquema, prazo, pensamento), modelo,
                            time.monotonic() - t0)
                except ErroLLM as e:
                    erros.append(f'{modelo}: {e!r}'[:300])
                    continue
            if not _cfg('GEMINI_API_KEY'):
                continue
            parts = parts or _partes(partes)
            try:
                if erros and _e_claude(erros[-1].split(':')[0]):
                    print(f'claude falhou, indo de {modelo}: {erros[-1][:150]}')
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
