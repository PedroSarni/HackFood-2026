"""Diário do painel: o que o bot ouviu, falou e pediu pro iFood, pro dash (Frontend/Rascunho_Dash).

O fluxo da conversa não sabe que isto existe. Os espiões ficam na borda:
- `EspiaoWhatsApp` embrulha o cliente do WhatsApp e anota cada mensagem que SAI;
- `espiar_mcp` embrulha o chamar(tool, **args) e anota cada chamada ao MCP (só um resumo);
- `espiar_ia` / `espiar_servico` embrulham a IA (Gemini/OpenRouter, Scribe, ElevenLabs) e anotam cada
  chamada como evento 'ia': qual agente, qual modelo respondeu, tempo, ok/erro e só contagens;
- `anotar_entrada` anota o lote de mensagens que ENTRA (chamado na rodada, em src/app.py).

Cada evento vira uma chave `ev:<microssegundos>:<sorteio>` num modal.Dict próprio
(`hackfood-painel`), então containers diferentes nunca brigam pela mesma chave e a ordem das
chaves é a ordem do tempo. A chave `versao` muda a cada gravação: o servidor local do dash
(src/painel/servidor.py) só varre as chaves quando ela muda.

`montar_sessoes(eventos, agora)` transforma o diário nas sessões que o dash desenha (mesmo
formato das fixtures de Frontend/Rascunho_Dash/data.js).

Regra de ouro: o diário nunca derruba o bot. Qualquer erro aqui vira um print e só.
LGPD: CPF digitado é mascarado antes de gravar, link de login não é guardado, e o telefone só
aparece mascarado no dash.
"""
import hashlib
import re
import secrets
import threading
import time
from datetime import datetime, timezone

NOME_DICT = 'hackfood-painel'
RECENTES = 'recentes'       # chave com os últimos eventos: o dash lê só ela (listar o Dict leva ~15 s)
MAX_RECENTES = 120
INATIVIDADE = 6 * 3600      # 6h sem falar: a próxima mensagem abre uma sessão nova
ABANDONO = 30 * 60          # carrinho parado há 30 min = abandonado (mesma regra do rascunho do Pedro)

_CPF = re.compile(r'\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}')


def _mascarar(texto):
    return _CPF.sub('•••.•••.•••-••', str(texto or ''))[:600]


class Diario:
    """Anota eventos e grava em lote. `intervalo=None` grava na hora (testes e simulador)."""

    def __init__(self, dic, agora=time.time, intervalo=0.3):
        self.dic = dic
        self.agora = agora
        self.intervalo = intervalo
        self._fila = {}
        self._trava = threading.Lock()
        self._timer = None

    def anotar(self, wa_id, tipo, **dados):
        try:
            ts = self.agora()
            ev = {'ts': ts, 'wa': str(wa_id), 'tipo': tipo, **{k: v for k, v in dados.items() if v is not None}}
            with self._trava:
                self._fila[f'ev:{int(ts * 1e6):017d}:{secrets.token_hex(3)}'] = ev
                if self.intervalo is None:
                    pass
                elif self._timer is None:
                    self._timer = threading.Timer(self.intervalo, self.descarregar)
                    self._timer.daemon = True
                    self._timer.start()
            if self.intervalo is None:
                self.descarregar()
        except Exception as e:  # noqa: BLE001 - diário nunca derruba o bot
            print(f'painel: anotar falhou: {e!r}')

    def descarregar(self):
        with self._trava:
            lote, self._fila = self._fila, {}
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if not lote:
            return
        try:
            try:  # containers diferentes podem se atropelar aqui: perde-se só a pressa, a varredura do dash cobre
                antes = self.dic.get(RECENTES) or {}
            except Exception:  # noqa: BLE001
                antes = {}
            juntos = {**(antes if isinstance(antes, dict) else {}), **lote}
            lote[RECENTES] = {k: juntos[k] for k in sorted(juntos)[-MAX_RECENTES:]}
            lote['versao'] = max(k for k in lote if k.startswith('ev:'))
            self.dic.update(lote)
        except Exception as e:  # noqa: BLE001
            print(f'painel: gravar {len(lote)} evento(s) falhou: {e!r}')


_producao = None


def diario_producao():
    """Um diário por container, gravando no modal.Dict do painel."""
    global _producao
    if _producao is None:
        import modal
        _producao = Diario(modal.Dict.from_name(NOME_DICT, create_if_missing=True))
    return _producao


# --- espiões ---------------------------------------------------------------------------

class EspiaoWhatsApp:
    """Mesma cara do WhatsApp; anota o que saiu (depois que a Meta aceitou)."""

    def __init__(self, wpp, diario, origem=None):
        self._wpp = wpp
        self._diario = diario
        self._origem = origem

    def __getattr__(self, nome):
        return getattr(self._wpp, nome)

    def _saiu(self, to, texto, opcoes=None, formato='Texto'):
        self._diario.anotar(to, 'saida', texto=_mascarar(texto), opcoes=opcoes or None, formato=formato,
                            origem=self._origem)

    def texto(self, to, texto, *a, **kw):
        r = self._wpp.texto(to, texto, *a, **kw)
        self._saiu(to, texto)
        return r

    def botoes(self, to, texto, botoes, *a, **kw):
        r = self._wpp.botoes(to, texto, botoes, *a, **kw)
        self._saiu(to, texto, [t for _, t in botoes], 'Botões')
        return r

    def carrossel(self, to, texto, cards, *a, **kw):
        r = self._wpp.carrossel(to, texto, cards, *a, **kw)
        self._saiu(to, texto, [str(c[1] or '').split('\n')[0] for c in cards], 'Cards')
        return r

    def lista(self, to, texto, rotulo, linhas, *a, **kw):
        r = self._wpp.lista(to, texto, rotulo, linhas, *a, **kw)
        self._saiu(to, texto, [t for _, t, _ in linhas], 'Lista')
        return r

    def link(self, to, texto, rotulo, url, *a, **kw):
        r = self._wpp.link(to, texto, rotulo, url, *a, **kw)
        self._saiu(to, texto, [rotulo], 'Link')  # a url fica de fora: link de login é segredo
        return r

    def imagem(self, to, link, legenda='', *a, **kw):
        r = self._wpp.imagem(to, link, legenda, *a, **kw)
        self._saiu(to, legenda or '📷 Foto', formato='Foto')
        return r

    def audio(self, to, media_id, *a, transcricao=None, **kw):
        r = self._wpp.audio(to, media_id, *a, transcricao=transcricao, **kw)
        self._saiu(to, f'🎤 {transcricao}' if transcricao else '🎤 Áudio', formato='Áudio')
        return r

    def template(self, to, nome, *a, **kw):
        r = self._wpp.template(to, nome, *a, **kw)
        self._saiu(to, f'Lembrete enviado fora da janela de 24h (template {nome})', formato='Template')
        return r


def _resumo_mcp(tool, args, r):
    """Só o que o dash usa. Nada de token, CPF ou endereço completo."""
    from src.bot.ifood import Ifood, _campo, _lista, _num, _sem_envelope
    d = _sem_envelope(r)
    if not isinstance(d, dict):
        return {}
    if tool == 'searchOffers':
        return {'busca': str(args.get('query') or '')[:80], 'n': len(_lista(d, 'results')),
                'pagina': bool(args.get('nextPageToken'))}
    if tool in ('createCart', 'addItemToCart', 'getCart', 'removeItemFromCart', 'setCartDelivery',
                'setCartPayment', 'setVoucher'):
        car = Ifood._carrinho(d)
        return {'loja': car.get('loja'), 'total': car.get('total'), 'itens': sum(i['qtd'] for i in car['itens']),
                'refazer': bool(args.get('orderId')) or None}
    if tool == 'submitOrder':
        return {'pedido': _campo(d, 'orderId')}
    if tool == 'trackOrder':
        return {'pedido': args.get('orderId'), 'status': _campo(d, 'status.code')}
    if tool in ('listAddresses', 'createAddress'):
        for e in _lista(d, 'addresses', 'results') + [d]:
            cidade = _campo(e, 'city', 'location.city', 'address.city')
            if cidade:
                return {'cidade': cidade}
    if tool == 'getItem':
        return {'preco': _num(_campo(d, 'promotionalUnitPrice', 'unitPrice'))}
    return {}


def espiar_mcp(chamar, diario, wa_id):
    """chamar(tool, **args) que anota cada chamada (ok/erro, tempo e um resumo)."""
    def chamar_espiando(tool, **args):
        t0 = time.time()
        try:
            r = chamar(tool, **args)
        except Exception as e:
            diario.anotar(wa_id, 'mcp', tool=tool, ok=False, ms=round((time.time() - t0) * 1000),
                          erro=str(getattr(e, 'codigo', '') or type(e).__name__)[:80])
            raise
        try:
            resumo = _resumo_mcp(tool, args, r)
        except Exception:  # noqa: BLE001 - resposta estranha: anota sem resumo
            resumo = {}
        diario.anotar(wa_id, 'mcp', tool=tool, ok=True, ms=round((time.time() - t0) * 1000), **resumo)
        return r
    return chamar_espiando


# --- agentes de IA ------------------------------------------------------------------------
# Quem é quem pelo prompt de sistema de cada módulo: nenhum agente precisa saber que é espiado.
# A arquitetura que o dash mostra: o entendimento (interpretar) só devolve JSON; quem orquestra,
# chama os especialistas e o MCP é o código (src/bot/fluxo.py), e os agentes só se falam por ele.
AGENTES = {'entendimento': 'Entendimento', 'foto': 'Foto', 'grupo': 'Kit em grupo', 'voz': 'Voz',
           'ouvido': 'Ouvido', 'relevancia': 'Relevância e sugestão', 'tutor': 'Tutor'}
def agente_do_sistema(sistema):
    """Quem é quem pelo prompt de sistema: a ficha de cada agente mora em src/agentes/."""
    from src import agentes
    return agentes.do_sistema(sistema)


def _curto(v):
    return _mascarar(v)[:40] if isinstance(v, str) else None


def _resumo_ia(agente, dados):
    """Só contagens e valores de enum. Nada do que a pessoa escreveu nem do que a IA respondeu."""
    if not isinstance(dados, dict):
        return {}
    if agente == 'entendimento':
        return {'acao': _curto(dados.get('acao')), 'itens': len(dados.get('itens') or [])}
    if agente == 'foto':
        return {'foto': _curto(dados.get('tipo')), 'itens': len(dados.get('itens') or []),
                'parecidos': len(dados.get('parecidos') or [])}
    if agente == 'grupo':
        return {'itens': len(dados.get('itens') or [])}
    if agente == 'relevancia':
        if 'listas' in dados:
            return {'listas': len(dados.get('listas') or [])}
        return {'mantidas': len(dados.get('manter') or [])}
    return {}


def _erro_ia(e):
    s = str(e)
    m = re.search(r'HTTP (\d{3})', s)
    if m:
        return f'HTTP {m.group(1)}'
    for pista, nome in (('desligado no painel', 'desligado'), ('timed out', 'timeout'), ('Timeout', 'timeout'),
                        ('finishReason', 'finishReason'), ('JSON inválido', 'JSON inválido'),
                        ('não configurada', 'sem key')):
        if pista in s or pista in type(e).__name__:
            return nome
    return type(e).__name__[:40]


def espiar_ia(gerar, diario, wa_id, primeiro=None):
    """gerar(sistema, partes, esquema, **kw) -> (dados, modelo, seg), anotando cada chamada como
    evento 'ia'. `primeiro(kw)` diz o 1º modelo da fila: outro modelo respondendo = caiu pro reserva."""
    def gerar_espiando(sistema, partes, esquema, **kw):
        t0 = time.time()
        try:
            agente = agente_do_sistema(sistema)
        except Exception:  # noqa: BLE001 - registro nunca derruba o bot
            agente = 'outro'
        try:
            r = gerar(sistema, partes, esquema, **kw)
        except Exception as e:
            diario.anotar(wa_id, 'ia', agente=agente, ok=False, ms=round((time.time() - t0) * 1000),
                          erro=_erro_ia(e), tentativas=str(e).count(' | ') + 1)
            raise
        try:
            dados, modelo = r[0], str(r[1])[:60]
            reserva = bool(primeiro and modelo != primeiro(kw)) or None
            resumo = _resumo_ia(agente, dados)
        except Exception:  # noqa: BLE001
            modelo, reserva, resumo = None, None, {}
        diario.anotar(wa_id, 'ia', agente=agente, modelo=modelo, reserva=reserva, ok=True,
                      ms=round((time.time() - t0) * 1000), **resumo)
        return r
    return gerar_espiando


def espiar_servico(fn, diario, wa_id, agente, modelo):
    """Mesma coisa pros serviços de voz: Scribe (ouvido, áudio -> texto) e ElevenLabs (voz, texto -> áudio)."""
    def fn_espiando(*a, **kw):
        t0 = time.time()
        try:
            r = fn(*a, **kw)
        except Exception as e:
            diario.anotar(wa_id, 'ia', agente=agente, modelo=modelo, ok=False,
                          ms=round((time.time() - t0) * 1000), erro=_erro_ia(e))
            raise
        diario.anotar(wa_id, 'ia', agente=agente, modelo=modelo, ok=r is not None,
                      ms=round((time.time() - t0) * 1000), erro=None if r is not None else 'sem resposta')
        return r
    return fn_espiando


_FORMATO = {'texto': 'Texto', 'botao': 'Botão', 'audio': 'Áudio', 'imagem': 'Foto',
            'localizacao': 'Localização', 'outro': 'Outro'}


def anotar_entrada(diario, wa_id, msgs):
    try:
        from src.bot.fluxo import entradas_de
        nome = next((m['_nome'] for m in reversed(msgs) if m.get('_nome')), None)
        for e in entradas_de(msgs):
            texto = e.texto or {'audio': '🎤 Áudio', 'imagem': '📷 Foto'}.get(e.tipo, '')
            diario.anotar(wa_id, 'entrada', texto=_mascarar(texto), botao=e.botao, formato=_FORMATO.get(e.tipo, 'Outro'),
                          nome=nome)
    except Exception as e:  # noqa: BLE001
        print(f'painel: anotar entrada falhou: {e!r}')


# --- do diário pras sessões do dash -----------------------------------------------------

# etapa do funil (1..10, igual ao STAGES de data.js) que cada chamada bem-sucedida alcança
ETAPA_MCP = {'searchOffers': 2, 'getItem': 4, 'createCart': 5, 'addItemToCart': 5,
             'getCartDeliveryMethods': 6, 'setCartDelivery': 6, 'listPaymentMethods': 7, 'listVouchers': 7,
             'setCartPayment': 8, 'submitOrder': 9}
EVENTO_ETAPA = {2: ('intent_identified', 'Intenção identificada'),
                3: ('recommendations_shown', 'Recomendações apresentadas'),
                4: ('recommendation_selected', 'Produto selecionado'),
                5: ('cart_created', 'Carrinho criado'),
                6: ('cart_confirmed', 'Carrinho confirmado · entrega'),
                7: ('checkout_started', 'Checkout iniciado'),
                8: ('payment_selected', 'Pagamento selecionado'),
                9: ('order_confirmed', 'Pedido confirmado'),
                10: ('order_delivered', 'Entrega confirmada')}
ENTREGUE = {'DELIVERED', 'CONCLUDED'}
# toques que ainda são sobre o pedido que acabou de sair (lembrete, "meu pedido"): não abrem sessão
DEPOIS_DO_PEDIDO = ('rec:', 'meu_pedido')


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _cliente(wa):
    return 'CLI-' + hashlib.sha1(f'hackfood:{wa}'.encode()).hexdigest()[:6].upper()


def _telefone(wa):
    d = re.sub(r'\D', '', str(wa))
    return f'(••) •••••-{d[-4:]}' if len(d) >= 4 else '—'


def _brl(texto_ou_num):
    return f'R$ {float(texto_ou_num):.2f}'.replace('.', ',')


def _nova(wa, n, ts, origem='Orgânica'):
    return {'id': f'WA-{_cliente(wa)[4:]}-{n:03d}', 'clientId': _cliente(wa), 'name': None, 'phone': _telefone(wa),
            'city': None, 'restaurant': None, 'status': 'active', 'stage': 1, 'amountCents': 0,
            'startedAt': ts, 'updatedAt': ts, 'origin': origem,
            'campaign': 'Lembrete de recorrência' if origem == 'Follow-up' else '',
            'input': None, 'latency': None, 'firstAccepted': True, 'reason': None, 'reasonEvidence': None,
            'entries': [], 'demo': False,
            # internos (saem antes de mandar pro navegador)
            '_pedido': None, '_abandonou': False, '_cancelou': False, '_ultimo_mcp_ok': True,
            '_esperando': None, '_latencias': [], '_cart_ts': None, '_entregue': False}


def _marcar(s, etapa, ts, detalhe=''):
    """Avança a etapa; o histórico ganha um evento só quando a etapa alcançada é nova."""
    if etapa <= s['stage']:
        return
    s['stage'] = etapa
    tipo, rotulo = EVENTO_ETAPA[etapa]
    s['entries'].append({'kind': 'event', 'type': tipo, 'label': rotulo + (f' · {detalhe}' if detalhe else ''),
                         'at': _iso(ts), 'stage': etapa})


def montar_sessoes(eventos, agora=None, demo=False, rotulos=None):
    """Eventos do diário (qualquer ordem) -> sessões no formato do dash, mais nova primeiro.
    `rotulos` (dict, opcional) recebe id(evento) -> id da sessão, pros agregados por conversa."""
    agora = agora or time.time()
    por_pessoa = {}
    for ev in sorted(eventos, key=lambda e: e.get('ts', 0)):
        if ev.get('wa'):
            por_pessoa.setdefault(ev['wa'], []).append(ev)
    sessoes = []
    for wa, evs in por_pessoa.items():
        minhas, nome, cidade = [], None, None
        for ev in evs:
            ts, tipo = ev['ts'], ev['tipo']
            if tipo == 'ia':  # rastro dos agentes: só ganha o rótulo da conversa, a sessão não muda
                if rotulos is not None and minhas:
                    rotulos[id(ev)] = minhas[-1]['id']
                continue
            s = None
            if tipo == 'mcp' and ev.get('tool') == 'trackOrder' and ev.get('pedido'):
                # rastreio pode chegar depois de a pessoa já ter puxado outra conversa
                s = next((x for x in reversed(minhas) if x['_pedido'] == ev['pedido']), None)
            elif ev.get('origem') == 'rastreio':
                s = next((x for x in reversed(minhas) if x['_pedido']), None)
            if s is None:
                s = minhas[-1] if minhas else None
                abrir = (s is None or ts - s['_ultimo'] > INATIVIDADE
                         or (tipo == 'entrada' and s['_pedido'] is not None
                             and not str(ev.get('botao') or '').startswith(DEPOIS_DO_PEDIDO))
                         or ev.get('origem') == 'lembrete')
                if abrir:
                    s = _nova(wa, len(minhas) + 1, _iso(ts), 'Follow-up' if ev.get('origem') == 'lembrete' else 'Orgânica')
                    s['_ultimo'] = ts
                    s['entries'].append({'kind': 'event', 'type': 'followup_sent' if s['origin'] == 'Follow-up' else 'conversation_started',
                                         'label': 'Lembrete de recorrência enviado' if s['origin'] == 'Follow-up' else 'Conversa iniciada',
                                         'at': _iso(ts), 'stage': 1})
                    minhas.append(s)
            if rotulos is not None:
                rotulos[id(ev)] = s['id']
            # carrinho parado 30 min e a pessoa voltou: houve abandono (e talvez recuperação)
            if s['_cart_ts'] and s['stage'] < 9 and not s['_abandonou'] and ts - s['_ultimo'] > ABANDONO:
                s['_abandonou'] = True
                s['entries'].append({'kind': 'event', 'type': 'cart_abandoned', 'label': 'Carrinho parado por mais de 30 minutos',
                                     'at': _iso(s['_ultimo'] + ABANDONO), 'stage': s['stage']})
            s['_ultimo'] = max(s['_ultimo'], ts)
            s['updatedAt'] = _iso(s['_ultimo'])
            if tipo == 'entrada':
                nome = ev.get('nome') or nome
                s['input'] = s['input'] or ev.get('formato')
                if s['_esperando'] is None:
                    s['_esperando'] = ts
                if ev.get('botao') == 'cancelar':
                    s['_cancelou'] = True
                if str(ev.get('botao') or '').startswith('mais:') and s['stage'] < 4:
                    s['firstAccepted'] = False
                s['entries'].append({'kind': 'message', 'role': 'customer', 'text': ev.get('texto') or '',
                                     'at': _iso(ts), 'type': ev.get('formato') or 'Texto'})
            elif tipo == 'saida':
                if s['_esperando'] is not None:
                    s['_latencias'].append(ts - s['_esperando'])
                    s['_esperando'] = None
                texto = ev.get('texto') or ''
                if ev.get('opcoes'):
                    texto += '\n' + ' · '.join(f'[{o}]' for o in ev['opcoes'][:10])
                s['entries'].append({'kind': 'message', 'role': 'agent', 'text': texto, 'at': _iso(ts),
                                     'type': ev.get('formato') or 'Texto'})
            elif tipo == 'mcp':
                tool = ev.get('tool')
                s['_ultimo_mcp_ok'] = bool(ev.get('ok'))
                if not ev.get('ok'):
                    s['entries'].append({'kind': 'event', 'type': 'agent_error', 'label': f'Falha no iFood · {tool} · {ev.get("erro", "")}',
                                         'at': _iso(ts), 'stage': s['stage']})
                    continue
                cidade = ev.get('cidade') or cidade
                if ev.get('loja'):
                    s['restaurant'] = ev['loja']
                if ev.get('total') is not None and s['stage'] < 9:
                    s['amountCents'] = int(round(float(ev['total']) * 100))
                if tool == 'searchOffers':
                    if ev.get('pagina') and s['stage'] < 4:
                        s['firstAccepted'] = False
                    _marcar(s, 3 if ev.get('n') else 2, ts, ev.get('busca', ''))
                elif tool in ETAPA_MCP:
                    if tool in ('createCart', 'addItemToCart'):
                        s['_cart_ts'] = s['_cart_ts'] or ts
                        s['_cancelou'] = False
                    detalhe = ''
                    if tool in ('createCart', 'addItemToCart') and ev.get('total') is not None:
                        detalhe = _brl(ev['total'])
                    if tool == 'submitOrder':
                        s['_pedido'] = ev.get('pedido') or 'sem-id'
                        detalhe = _brl(s['amountCents'] / 100)
                        if s['_abandonou']:
                            s['entries'].append({'kind': 'event', 'type': 'cart_recovered', 'label': 'Compra recuperada confirmada',
                                                 'at': _iso(ts), 'stage': 9})
                    _marcar(s, ETAPA_MCP[tool], ts, detalhe)
                elif tool == 'trackOrder' and ev.get('status') in ENTREGUE and not s['_entregue']:
                    s['_entregue'] = True
                    _marcar(s, 10, ts)
        for s in minhas:
            s['name'] = nome or f'Cliente {s["phone"][-4:]}'
            s['city'] = cidade or 'Não informada'
            s['restaurant'] = s['restaurant'] or 'Sem restaurante'
            s['input'] = s['input'] or 'Texto'
            s['latency'] = round(sum(s['_latencias']) / len(s['_latencias']), 1) if s['_latencias'] else 0
            s['demo'] = demo
            parado = agora - s['_ultimo']
            if s['_pedido']:
                s['status'] = 'recovered' if s['_abandonou'] else 'completed'
            elif s['_cancelou'] and s['_cart_ts']:
                s['status'] = 'cancelled'
                s['entries'].append({'kind': 'event', 'type': 'order_cancelled', 'label': 'Cliente cancelou o pedido',
                                     'at': s['updatedAt'], 'stage': s['stage']})
            elif s['_cart_ts'] and parado > ABANDONO:
                s['status'] = 'abandoned'
                s['reason'], s['reasonEvidence'] = 'Motivo não identificado', 'Sem evidência'
                if not s['_abandonou']:
                    s['entries'].append({'kind': 'event', 'type': 'cart_abandoned', 'label': 'Carrinho sem conclusão após 30 minutos',
                                         'at': _iso(s['_ultimo'] + ABANDONO), 'stage': s['stage']})
            elif not s['_ultimo_mcp_ok']:
                s['status'] = 'failed'
            elif s['stage'] >= 8:
                s['status'] = 'payment'
            elif parado > ABANDONO:
                s['status'] = 'idle'
            else:
                s['status'] = 'active'
            for k in [k for k in s if k.startswith('_')]:
                del s[k]
            sessoes.append(s)
    return sorted(sessoes, key=lambda s: s['updatedAt'], reverse=True)


# --- agregados pro dash: o servidor resume, o navegador só recebe o resumo e a conversa aberta ---

DOC_MCP = 'regras da api/ifood-mcp-developer-portal.json'
SO_NA_DOC = {'listItemTaxonomy'}   # o servidor tem 23 tools; esta só existe na doc (docs/contexto-evento.md §4)
MAX_SEQUENCIA = 300
MAX_CONVERSAS = 200
_tools_doc = None


def tools_da_doc():
    """[(tool, domínio)] na ordem da doc do iFood. Doc ilegível: lista vazia (o dash só não mostra as nunca chamadas)."""
    global _tools_doc
    if _tools_doc is None:
        import json
        import pathlib
        try:
            doc = json.loads((pathlib.Path(__file__).resolve().parents[2] / DOC_MCP).read_text(encoding='utf-8'))
            _tools_doc = [(t['nome'], dominio) for dominio, m in doc['mcps'].items() for t in m.get('tools', [])]
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f'painel: lista de tools da doc ilegível: {e!r}')
            _tools_doc = []
    return _tools_doc


def _recorte(eventos, rotulos, tipos, de=None, conversa=None):
    """(evento, conversa) dos tipos pedidos, no período e na conversa, em ordem de tempo."""
    for ev in sorted((e for e in eventos if e.get('tipo') in tipos), key=lambda e: e.get('ts', 0)):
        if de and ev.get('ts', 0) < de:
            continue
        conv = rotulos.get(id(ev))
        if conversa and conv != conversa:
            continue
        yield ev, conv


def _pct(parte, todo):
    return round(100 * parte / todo, 1) if todo else 0.0


def _linha_uso(nome, n, erros, ms, conversas, total):
    return {'chamadas': n, 'pct': _pct(n, total), 'erros': erros, 'pctErro': _pct(erros, n),
            'msMedio': round(sum(ms) / len(ms)) if ms else None, 'msMax': max(ms) if ms else None,
            'conversas': len(conversas), **nome}


def resumo_mcp(eventos, rotulos, de=None, conversa=None):
    """Uso do MCP por tool (chamadas, % do total, % de erro, latência, conversas), as tools da doc
    que nunca foram chamadas no recorte e, com `conversa`, a sequência das chamadas na ordem."""
    por, convs, total, seq = {}, set(), 0, []
    for ev, conv in _recorte(eventos, rotulos, ('mcp',), de, conversa):
        tool = str(ev.get('tool') or '?')
        t = por.setdefault(tool, {'n': 0, 'erros': 0, 'ms': [], 'conv': set(), 'codigos': {}})
        t['n'] += 1
        total += 1
        if isinstance(ev.get('ms'), (int, float)):
            t['ms'].append(ev['ms'])
        if not ev.get('ok'):
            t['erros'] += 1
            cod = str(ev.get('erro') or '?')
            t['codigos'][cod] = t['codigos'].get(cod, 0) + 1
        if conv:
            t['conv'].add(conv)
            convs.add(conv)
        if conversa and len(seq) < MAX_SEQUENCIA:
            seq.append({'at': _iso(ev['ts']), 'tool': tool, 'ok': bool(ev.get('ok')), 'ms': ev.get('ms'),
                        'erro': ev.get('erro')})
    dominio = dict(tools_da_doc())
    tools = []
    for tool, t in sorted(por.items(), key=lambda kv: (-kv[1]['n'], kv[0])):
        linha = _linha_uso({'tool': tool, 'dominio': dominio.get(tool)}, t['n'], t['erros'], t['ms'], t['conv'], total)
        linha['erroComum'] = max(t['codigos'], key=t['codigos'].get) if t['codigos'] else None
        tools.append(linha)
    nunca = [{'tool': tool, 'dominio': d, 'soNaDoc': tool in SO_NA_DOC} for tool, d in tools_da_doc() if tool not in por]
    return {'total': total, 'conversas': len(convs), 'tools': tools, 'nunca': nunca,
            'sequencia': seq if conversa else None}


def indice_conversas(eventos, rotulos, sessoes, de=None, limite=MAX_CONVERSAS):
    """As conversas do recorte pro filtro do dash (mais nova primeiro), com quantas chamadas tiveram."""
    conta = {}
    for ev, conv in _recorte(eventos, rotulos, ('entrada', 'saida', 'mcp', 'ia'), de):
        if conv:
            c = conta.setdefault(conv, {'mcp': 0, 'ia': 0})
            if ev['tipo'] in c:
                c[ev['tipo']] += 1
    saida = []
    for s in sessoes:  # já vêm da mais nova pra mais velha
        if s['id'] in conta:
            saida.append({'id': s['id'], 'nome': s['name'], 'inicio': s['startedAt'], 'fim': s['updatedAt'],
                          **conta[s['id']]})
            if len(saida) >= limite:
                break
    return saida


# regras sem IA que o dash mostra ao lado dos agentes, reconhecidas pela mensagem que mandaram
REGRAS = {'followup': 'Follow-up', 'recorrencia': 'Recorrência', 'vitrine': 'Vitrine'}
RAJADA = 30   # s: as mensagens de um mesmo disparo da regra contam uma vez só


def regra_da_saida(ev):
    from src.bot.textos import VITRINE_TOPO
    if ev.get('origem') == 'followup':
        return 'followup'
    if ev.get('origem') == 'lembrete':
        return 'recorrencia'
    if ev.get('formato') == 'Cards' and str(ev.get('texto') or '').startswith(VITRINE_TOPO):
        return 'vitrine'
    return None


_RESUMO_IA = ('acao', 'itens', 'foto', 'parecidos', 'mantidas', 'listas', 'tentativas')


def _passo(ev, regra=None):
    """Um passo da linha do tempo, sem texto nenhum da conversa."""
    base = {'at': _iso(ev['ts'])}
    if ev['tipo'] == 'entrada':
        return {**base, 'tipo': 'mensagem', 'formato': ev.get('formato') or 'Texto', 'botao': bool(ev.get('botao'))}
    if ev['tipo'] == 'ia':
        agente = ev.get('agente') or 'outro'
        return {**base, 'tipo': 'ia', 'agente': agente, 'nome': AGENTES.get(agente, 'Outro'), 'modelo': ev.get('modelo'),
                'reserva': bool(ev.get('reserva')), 'ms': ev.get('ms'), 'ok': bool(ev.get('ok')), 'erro': ev.get('erro'),
                'resumo': {k: ev[k] for k in _RESUMO_IA if ev.get(k) is not None}}
    if ev['tipo'] == 'mcp':
        return {**base, 'tipo': 'mcp', 'tool': ev.get('tool'), 'ok': bool(ev.get('ok')), 'ms': ev.get('ms'), 'erro': ev.get('erro')}
    if regra:
        return {**base, 'tipo': 'regra', 'agente': regra, 'nome': REGRAS[regra]}
    return {**base, 'tipo': 'resposta', 'formato': ev.get('formato') or 'Texto', 'origem': ev.get('origem')}


def resumo_agentes(eventos, rotulos, de=None, conversa=None):
    """Uso de cada agente de IA (chamadas, % do total, erros, latência, modelos e quantas vezes caiu
    pro reserva), os disparos das regras sem IA e, com `conversa`, a linha do tempo dela:
    mensagem -> entendimento -> especialistas e MCP (pelo código) -> resposta."""
    ia, regras, ultimo, total = {}, {}, {}, 0
    linha = [] if conversa else None
    for ev, conv in _recorte(eventos, rotulos, ('entrada', 'saida', 'mcp', 'ia'), de, conversa):
        regra = None
        if ev['tipo'] == 'ia' and ev.get('erro') == 'desligado':
            # desligado no dash: não é chamada nem erro, é o plano B entrando (conta à parte)
            a = ia.setdefault(ev.get('agente') or 'outro', {'n': 0, 'erros': 0, 'ms': [], 'conv': set(), 'modelos': {}, 'reserva': 0})
            a['pulos'] = a.get('pulos', 0) + 1
        elif ev['tipo'] == 'ia':
            a = ia.setdefault(ev.get('agente') or 'outro', {'n': 0, 'erros': 0, 'ms': [], 'conv': set(), 'modelos': {}, 'reserva': 0})
            a['n'] += 1
            total += 1
            if isinstance(ev.get('ms'), (int, float)):
                a['ms'].append(ev['ms'])
            if not ev.get('ok'):
                a['erros'] += 1
            if ev.get('modelo'):
                a['modelos'][ev['modelo']] = a['modelos'].get(ev['modelo'], 0) + 1
            if ev.get('reserva'):
                a['reserva'] += 1
            if conv:
                a['conv'].add(conv)
        elif ev['tipo'] == 'saida':
            regra = regra_da_saida(ev)
            if regra:
                chave = (ev.get('wa'), regra)
                novo = ev['ts'] - ultimo.get(chave, float('-inf')) > RAJADA
                ultimo[chave] = ev['ts']
                if novo:
                    r = regras.setdefault(regra, {'n': 0, 'conv': set()})
                    r['n'] += 1
                    if conv:
                        r['conv'].add(conv)
                else:
                    regra = None
        if linha is not None and len(linha) < MAX_SEQUENCIA:
            if regra:
                linha.append(_passo(ev, regra))
            linha.append(_passo(ev))
    agentes = []
    for agente in list(AGENTES) + sorted(set(ia) - set(AGENTES)):
        a = ia.get(agente, {'n': 0, 'erros': 0, 'ms': [], 'conv': set(), 'modelos': {}, 'reserva': 0})
        linha_uso = _linha_uso({'agente': agente, 'nome': AGENTES.get(agente, 'Outro'), 'tipo': 'ia'},
                               a['n'], a['erros'], a['ms'], a['conv'], total)
        linha_uso['modelos'] = [{'modelo': m, 'n': n} for m, n in sorted(a['modelos'].items(), key=lambda kv: -kv[1])]
        linha_uso['reserva'] = a['reserva']
        linha_uso['pulos'] = a.get('pulos', 0)
        agentes.append(linha_uso)
    agentes.sort(key=lambda a: -a['chamadas'])
    lista_regras = [{'agente': r, 'nome': nome, 'tipo': 'regra', 'disparos': regras.get(r, {}).get('n', 0),
                     'conversas': len(regras.get(r, {}).get('conv', ()))} for r, nome in REGRAS.items()]
    return {'total': total, 'agentes': agentes, 'regras': lista_regras, 'linha': linha}
