"""App Modal do bot: webhook do WhatsApp, login do iFood e os trabalhos em segundo plano.

    deploy:  .venv/Scripts/python.exe -m modal deploy -m src.app
    testes:  .venv/Scripts/python.exe -m pytest

Desenho: o webhook só guarda a mensagem e devolve 200 na hora (a Meta derruba webhook lento).
Quem conversa é `rodada`, que junta a rajada de mensagens da pessoa (src/shared/buffer.py) e
entrega o lote pro Bot (src/bot/fluxo.py). Tudo que é de uma pessoa mora no dicionário
`hackfood-estado`, em chaves com o wa_id dela.
"""
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import time

import modal

# NÃO MUDE APP, ROTULO, BASE nem a região: o callback do OAuth do iFood está cadastrado com esta URL
# e o portal não deixa mais editar (AGENTS.md §0.0). Mudou a URL, o login do iFood quebra.
APP = 'hackfood-bot'
ROTULO = 'hackfood-bot'
BASE = os.environ.get('HACKFOOD_BASE') or f'https://fabio-araujo-silva--{ROTULO}.us-east.modal.run'
CALLBACK = f'{BASE}/ifood/callback'
LOGIN_VALIDADE = 30 * 60      # link "Entrar no iFood" vale 30 min (cada toque gera PKCE novo)

app = modal.App(APP)
imagem = (modal.Image.debian_slim(python_version='3.12')
          .pip_install('fastapi[standard]==0.141.1', 'httpx==0.28.1', 'anthropic==1.15.0')
          .add_local_python_source('src')
          # add_local_python_source só leva .py: sem isso o /logo.png dava 500 no ar
          .add_local_file(pathlib.Path(__file__).parent / 'web' / 'logo.png', '/root/src/web/logo.png'))
segredos = [modal.Secret.from_name('hackathon-whatsapp'),
            # GEMINI_API_KEY própria do HackFood (o `llm-conversor` é do handwrite_bot e a cota estourou)
            modal.Secret.from_name('hackathon-gemini'),
            modal.Secret.from_name('hackathon-ifood'),
            # ELEVENLABS_API_KEY do Scribe (áudio vira texto); PREENCHER = desligado e o Gemini ouve
            modal.Secret.from_name('hackathon-elevenlabs'),
            # palavra secreta de debug (DEBUG_RESET), fora do git; vazia = desligado
            modal.Secret.from_name('hackathon-debug'),
            # OPENROUTER_API_KEY: quebra-galho quando o Gemini estoura (src/shared/llm.py); PREENCHER = desligado
            modal.Secret.from_name('hackathon-openrouter'),
            # ANTHROPIC_API_KEY: o Claude Sonnet é o 1º da fila de todo agente; sem crédito, o Gemini assume
            modal.Secret.from_name('hackathon-anthropic')]

estado = modal.Dict.from_name('hackfood-estado', create_if_missing=True)
entrada = modal.Queue.from_name('hackfood-entrada', create_if_missing=True)


def _cfg(nome):
    v = os.environ.get(nome, '')
    return '' if v == 'PREENCHER' else v


# --- conversa -------------------------------------------------------------------------

@app.function(image=imagem, secrets=segredos, timeout=900, scaledown_window=600)
@modal.concurrent(max_inputs=40)
def rodada(wa_id: str, seq: int, espera: float, mid: str = ''):
    """Uma por mensagem recebida; só a da mensagem mais nova da rajada processa."""
    from src.shared.buffer import Caixa
    from src.shared.whatsapp import WhatsApp
    wpp = WhatsApp()
    wpp.digitando(mid)
    caixa = Caixa(entrada, estado)
    if not caixa.aguardar_silencio(wa_id, seq, espera):
        return 'rajada continua'
    if not caixa.pegar_trava(wa_id, seq):
        return 'outra rodada assumiu'
    try:
        msgs = caixa.retirar(wa_id)
        if not msgs:
            return 'fila vazia'
        from src.bot.contexto import contexto_producao
        from src.bot.fluxo import Bot
        from src.shared import painel
        ctx = contexto_producao(estado, wpp, wa_id)
        painel.anotar_entrada(ctx.diario, wa_id, msgs)
        bot = Bot(ctx)
        try:
            bot.processar(wa_id, msgs)
        finally:
            ctx.diario.descarregar()
        try:  # calou com pergunta aberta ou carrinho cheio: follow-up aos 3 min, abandono aos 5
            marca = bot.marca_followup() or bot.marca_abandono()
            if marca:
                pessoa_calada.spawn(wa_id, marca)
        except Exception as e:  # noqa: BLE001 - o protocolo é bônus, a resposta já foi
            print(f'agendar pessoa_calada falhou: {e!r}')
        return f'{len(msgs)} mensagem(ns)'
    finally:
        caixa.soltar_trava(wa_id, seq)


@app.function(image=imagem, secrets=segredos, timeout=600)
def pessoa_calada(wa_id: str, marca: float):
    """Protocolo de quem calou (decisão do Fabio): aos FOLLOWUP_SEG cutuca uma vez; aos ABANDONO_SEG,
    se ainda calada com itens no carrinho, esquece o carrinho. `marca` é o ultima_msg da rodada:
    se a pessoa falou de novo, ele muda e o Bot não faz nada."""
    from src.bot.contexto import contexto_producao
    from src.bot.fluxo import ABANDONO_SEG, FOLLOWUP_SEG, Bot
    from src.shared.whatsapp import WhatsApp
    trava = f'trava:{wa_id}'
    for limite, passo in ((FOLLOWUP_SEG, 'followup'), (ABANDONO_SEG, 'abandonar_carrinho')):
        time.sleep(max(0.0, marca + limite - time.time()))
        if (estado.get(f'u:{wa_id}') or {}).get('ultima_msg') != marca:
            return 'a pessoa falou'
        # mesma trava das rodadas: com uma resposta em andamento a pessoa falou, e não falamos por cima
        if not estado.put(trava, {'seq': -2, 'ts': time.time()}, skip_if_exists=True):
            return 'rodada em andamento'
        ctx = contexto_producao(estado, WhatsApp(), wa_id, origem='followup')  # EspiaoWhatsApp + diário
        try:
            getattr(Bot(ctx), passo)(wa_id, marca)
        finally:
            ctx.diario.descarregar()
            atual = estado.get(trava)
            if atual and atual.get('seq') == -2:
                estado.pop(trava, None)
    return 'protocolo completo'


@app.function(image=imagem, secrets=segredos, timeout=120)
def analisar_pagina(pagina: str, dados: dict):
    """A Analista do dash (src/painel/analista.py): insights por time a partir dos números agregados de uma página.
    Chamada pelo servidor local do painel (POST /api/insights); usa a fila e o interruptor da ficha dela."""
    from src import agentes
    from src.painel import analista
    from src.shared import alertas, llm
    llm.avisar = lambda *a: alertas.registrar(estado, *a)
    cfg = agentes.config(estado)
    if not agentes.ligado(cfg, 'analista'):
        return {'erro': 'desligado'}
    try:
        return analista.analisar(pagina, dados, agentes.roteador(llm.gerar_json, cfg))
    except analista.EntradaRuim as e:
        return {'erro': 'entrada', 'detalhe': str(e)}
    except Exception as e:  # noqa: BLE001 - o dash mostra o aviso e deixa tentar de novo
        print(f'analista falhou em {pagina}: {e!r}')
        return {'erro': 'modelo', 'detalhe': str(e)[:300]}


@app.function(image=imagem, secrets=segredos, timeout=120)
def depois_do_login(wa_id: str):
    """O OAuth terminou no navegador: avisa no WhatsApp e retoma o que a pessoa tinha pedido."""
    from src.bot.contexto import contexto_producao
    from src.bot.fluxo import Bot
    from src.shared.whatsapp import WhatsApp
    caixa_trava = f'trava:{wa_id}'
    # mesma trava das rodadas: não fala por cima de uma resposta em andamento
    for _ in range(60):
        if estado.put(caixa_trava, {'seq': -1, 'ts': time.time()}, skip_if_exists=True):
            break
        time.sleep(0.5)
    try:
        Bot(contexto_producao(estado, WhatsApp(), wa_id)).logou(wa_id)
    finally:
        atual = estado.get(caixa_trava)
        if atual and atual.get('seq') == -1:
            estado.pop(caixa_trava, None)


@app.function(image=imagem, secrets=segredos, timeout=4 * 3600)
def acompanhar_pedido(wa_id: str, pedido_id: str):
    """Consulta o status do pedido no ritmo que o iFood pede e avisa cada mudança."""
    from src.bot.contexto import contexto_producao
    from src.bot.rastreio import acompanhar
    from src.shared.whatsapp import WhatsApp
    acompanhar(contexto_producao(estado, WhatsApp(), wa_id, origem='rastreio'), wa_id, pedido_id)


@app.function(image=imagem, secrets=segredos, timeout=120)
def ferramentas_reais(wa_id: str):
    """Diagnóstico: tools/list do gateway real com o token de quem já entrou. A doc não traz
    os inputSchema; isto mostra os nomes e parâmetros de verdade.
        .venv/Scripts/python.exe -m modal run -m src.app::ferramentas_reais --wa-id 55...
    """
    from src.bot.contexto import chamador_real
    from src.shared import ifood_mcp
    chamador_real(estado, wa_id)('getUser')  # renova o token se precisar
    tok = estado.get(f'tok:{wa_id}')
    tools = ifood_mcp.ClienteMCP(tok['access_token']).ferramentas()
    return [{'name': t.get('name'), 'inputSchema': t.get('inputSchema')} for t in tools]


@app.function(image=imagem, secrets=segredos, timeout=600, schedule=modal.Period(minutes=15))
def lembretes():
    """Recorrência: avisa quem tem compra repetida vencendo (botão "Pedir de novo")."""
    from src.bot.recorrencia import disparar_vencidos
    from src.shared import painel
    from src.shared.whatsapp import WhatsApp
    diario = painel.diario_producao()
    try:
        return disparar_vencidos(estado, painel.EspiaoWhatsApp(WhatsApp(), diario, 'lembrete'))
    finally:
        diario.descarregar()


@app.function(image=imagem, secrets=segredos, timeout=900)
def lembrete_na_hora(wa_id: str, quando: float):
    """Modo demo: espera até `quando` e manda o lembrete só dessa pessoa (sem esperar o cron)."""
    from src.bot.recorrencia import disparar_vencidos
    from src.shared.whatsapp import WhatsApp
    from src.shared import painel
    time.sleep(max(0, min(840, quando - time.time())) + 1)
    diario = painel.diario_producao()
    try:
        return disparar_vencidos(estado, painel.EspiaoWhatsApp(WhatsApp(), diario, 'lembrete'), so=wa_id)
    finally:
        diario.descarregar()


# --- web ------------------------------------------------------------------------------

@app.function(image=imagem, secrets=segredos, timeout=60, scaledown_window=600)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label=ROTULO)
def web():
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

    from src.shared import ifood_mcp
    from src.shared.buffer import Caixa, espera_para
    from src.web import paginas

    api = FastAPI(docs_url=None, redoc_url=None)
    caixa = Caixa(entrada, estado)
    numero = _cfg('WHATSAPP_NUMERO')
    voltar = f'https://wa.me/{numero}' if numero else 'https://wa.me/'

    @api.get('/', response_class=HTMLResponse)
    async def inicio():
        return paginas.tela('🛒', paginas.NOME, 'Faça seus pedidos conversando no WhatsApp.',
                            'Abrir no WhatsApp', voltar)

    @api.api_route('/termos', methods=['GET', 'HEAD'], response_class=HTMLResponse)
    async def termos():
        return paginas.termos()

    @api.api_route('/privacidade', methods=['GET', 'HEAD'], response_class=HTMLResponse)
    async def privacidade():
        return paginas.privacidade()

    @api.api_route('/exclusao', methods=['GET', 'HEAD'], response_class=HTMLResponse)
    async def exclusao():
        return paginas.exclusao()

    @api.get('/saude')
    async def saude():
        return {'ok': True, 'app': APP, 'ts': int(time.time())}

    @api.get('/logo.png')
    async def logo():
        from fastapi.responses import Response
        dados = (pathlib.Path(paginas.__file__).parent / 'logo.png').read_bytes()  # no ar o app.py fica em /root
        return Response(dados, media_type='image/png', headers={'cache-control': 'public, max-age=86400'})

    # --- WhatsApp ---

    @api.get('/whatsapp')
    async def verificar(request: Request):
        q = request.query_params
        if (q.get('hub.mode') == 'subscribe'
                and hmac.compare_digest(q.get('hub.verify_token', ''), _cfg('WHATSAPP_VERIFY_TOKEN'))):
            return PlainTextResponse(q.get('hub.challenge', ''))
        return PlainTextResponse('token errado', status_code=403)

    @api.post('/whatsapp')
    async def receber(request: Request):
        corpo = await request.body()
        segredo = _cfg('META_APP_SECRET')
        if segredo:
            assin = request.headers.get('x-hub-signature-256', '')
            esperada = 'sha256=' + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(assin, esperada):
                return PlainTextResponse('assinatura invalida', status_code=403)
        try:
            evento = json.loads(corpo)
        except ValueError:
            return {'status': 'ignorado'}
        permitidos = {x.strip() for x in _cfg('MEU_NUMERO').split(',') if x.strip()}
        for ent in evento.get('entry', []):
            for ch in ent.get('changes', []):
                val = ch.get('value', {})
                nomes = {c.get('wa_id'): (c.get('profile') or {}).get('name')
                         for c in val.get('contacts', []) if isinstance(c, dict)}
                for msg in val.get('messages', []):
                    wa_id = msg.get('from', '')
                    if not wa_id or (permitidos and wa_id not in permitidos):
                        continue
                    mid = msg.get('id', '')
                    # a Meta reenvia em retry: put atômico faz o dedup
                    if mid and not await estado.put.aio(f'visto:{mid}', time.time(), skip_if_exists=True):
                        continue
                    if nomes.get(wa_id):
                        msg['_nome'] = nomes[wa_id]
                    seq = await _guardar(caixa, wa_id, msg)
                    await rodada.spawn.aio(wa_id, seq, espera_para(msg), mid)
                for st in val.get('statuses', []):
                    if isinstance(st, dict) and st.get('status') == 'failed':
                        print('envio falhou:', json.dumps(st, ensure_ascii=False)[:600])
        return {'status': 'ok'}  # sempre 200, senão a Meta desativa o webhook

    # --- login do iFood ---

    @api.get('/login/{codigo}', response_class=HTMLResponse)
    async def login(codigo: str, request: Request):
        pedido = await estado.get.aio(f'login:{codigo}')
        if not pedido or time.time() - pedido.get('criado', 0) > LOGIN_VALIDADE:
            return paginas.tela('⏰', 'Esse link venceu',
                                'Volte pro WhatsApp e toque de novo em "Entrar no iFood".',
                                'Voltar pro WhatsApp', voltar)
        from src.bot.contexto import modo_mock
        if modo_mock(estado):
            # modo demo: sem OAuth de verdade. 1º a tela de consentimento (nossa, não do iFood);
            # só quando a pessoa toca em "Permitir" (go=1) marca como logada e segue a conversa.
            if request.query_params.get('go') != '1':
                return paginas.login_demo(f'{BASE}/login/{codigo}?go=1', voltar)
            await estado.put.aio(f'tok:{pedido["wa_id"]}', {'access_token': 'mock', 'refresh_token': 'mock',
                                                            'expira_em': time.time() + 30 * 86400})
            await depois_do_login.spawn.aio(pedido['wa_id'])
            return paginas.logou('Modo de demonstração. Pode voltar pro '
                                 'WhatsApp: já te mandei uma mensagem lá.', 'Voltar pro WhatsApp', voltar)
        verificador, desafio = ifood_mcp.pkce()
        state = secrets.token_urlsafe(24)
        await estado.put.aio(f'oauth:{state}', {'wa_id': pedido['wa_id'], 'verificador': verificador,
                                                'criado': time.time()})
        url = ifood_mcp.url_login(_cfg('IFOOD_CLIENT_ID'), CALLBACK, state, desafio,
                                  _cfg('IFOOD_ESCOPOS') or None)
        return RedirectResponse(url, status_code=302)

    @api.get('/ifood/callback', response_class=HTMLResponse)
    async def callback(request: Request):
        q = request.query_params
        sessao = await estado.pop.aio(f'oauth:{q.get("state", "")}', None)
        if not sessao or time.time() - sessao.get('criado', 0) > LOGIN_VALIDADE:
            return paginas.tela('⏰', 'Esse link venceu',
                                'Volte pro WhatsApp e toque de novo em "Entrar no iFood".',
                                'Voltar pro WhatsApp', voltar)
        if q.get('error') or not q.get('code'):
            print(f'login recusado: {q.get("error")} {q.get("error_description", "")[:200]}')
            return paginas.tela('🙂', 'Tudo bem', 'Você não autorizou agora. Quando quiser, é só '
                                'voltar pro WhatsApp e tocar em "Entrar no iFood".',
                                'Voltar pro WhatsApp', voltar)
        try:
            tokens = ifood_mcp.trocar_codigo(_cfg('IFOOD_CLIENT_ID'), _cfg('IFOOD_CLIENT_SECRET'),
                                             q['code'], sessao['verificador'], CALLBACK)
        except ifood_mcp.ErroMCP as e:
            print(f'troca do code falhou: {e!r}')
            return paginas.tela('😕', 'Não deu certo', 'Volte pro WhatsApp e tente entrar de novo.',
                                'Voltar pro WhatsApp', voltar)
        await estado.put.aio(f'tok:{sessao["wa_id"]}', tokens)
        await depois_do_login.spawn.aio(sessao['wa_id'])
        return paginas.logou('Pode voltar pro WhatsApp: já te mandei '
                             'uma mensagem lá.', 'Voltar pro WhatsApp', voltar)

    return api


async def _guardar(caixa, wa_id, msg):
    """Caixa.guardar em versão assíncrona (o webhook não pode bloquear o loop)."""
    from src.shared.buffer import nova_seq
    seq = nova_seq()
    await entrada.put.aio(msg, partition=wa_id)
    await estado.put.aio(f'prim:{wa_id}', time.time(), skip_if_exists=True)
    await estado.put.aio(f'ult:{wa_id}', seq)
    return seq


def novo_link_login(wa_id):
    """Link curto pro botão "Entrar no iFood"; o PKCE é gerado no toque, não aqui."""
    codigo = secrets.token_urlsafe(12)
    estado[f'login:{codigo}'] = {'wa_id': wa_id, 'criado': time.time()}
    return f'{BASE}/login/{codigo}'
