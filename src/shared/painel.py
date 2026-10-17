"""Diário do painel: o que o bot ouviu, falou e pediu pro iFood, pro dash (Frontend/Rascunho_Dash).

O fluxo da conversa não sabe que isto existe. Os espiões ficam na borda:
- `EspiaoWhatsApp` embrulha o cliente do WhatsApp e anota cada mensagem que SAI;
- `espiar_mcp` embrulha o chamar(tool, **args) e anota cada chamada ao MCP (só um resumo);
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
            lote['versao'] = max(lote)
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


def montar_sessoes(eventos, agora=None, demo=False):
    """Eventos do diário (qualquer ordem) -> sessões no formato do dash, mais nova primeiro."""
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
