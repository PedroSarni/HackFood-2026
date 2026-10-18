"""Compra recorrente: "me lembra de pedir isso toda semana".

O MCP do iFood não tem recorrência nativa (nem pra mercado), então ela é nossa: a partir da 2ª
compra do mesmo item OU da mesma categoria ("hambúrguer" de qualquer loja) o bot oferece.
Cada lembrete guarda o pedido de origem (o iFood refaz o carrinho com createCart(orderId)).
Nada é comprado sozinho: no dia o bot pergunta "podemos pedir?" mostrando itens, endereço,
valor e pagamento, e só o "Sim, pode pedir" fecha o pedido (esse toque é a confirmação).

Modo demo (`modal run scripts/modo.py --rapido on`): qualquer frequência vence em 1 minuto.

Janela de 24h da Meta: mensagem livre só até 24h depois da última mensagem da pessoa. Lembrete
de semana quase sempre cai fora dela, então:
- dentro da janela: manda os botões direto;
- fora, com template aprovado (env TEMPLATE_LEMBRETE): manda o template;
- fora, sem template: marca como pendente e mostra na próxima vez que a pessoa falar com o bot.

Os lembretes moram num dicionário próprio (chave = wa_id) pra varredura não passar pelas
chaves de conversa.
"""
import os
import secrets
import time

JANELA = 23.5 * 3600
DEMO_SEGUNDOS = 60

# palavra no nome do item -> categoria. Ordem importa: a 1ª que bater ganha.
CATEGORIAS = [
    ('hambúrguer', ('hamburguer', 'burger', 'burguer', 'x-', 'x ', 'smash', 'cheddar bacon')),
    ('pizza', ('pizza', 'calzone')),
    ('açaí', ('acai',)),
    ('sushi', ('sushi', 'temaki', 'sashimi', 'uramaki', 'hot roll', 'poke')),
    ('pastel', ('pastel',)),
    ('esfiha', ('esfiha', 'esfirra')),
    ('marmita', ('marmita', 'marmitex', 'prato feito', 'pf ', 'executivo')),
    ('lanche', ('lanche', 'sanduiche', 'beirute', 'hot dog', 'cachorro quente')),
    ('frango', ('frango frito', 'balde', 'fried chicken', 'nuggets')),
    ('sorvete', ('sorvete', 'milkshake', 'milk shake')),
    ('café', ('cafe', 'cappuccino', 'capuccino', 'latte')),
    ('pão', ('pao ', 'paes', 'baguete', 'bisnaga')),
    # carne crua de qualquer marca (Friboi hoje, picanha Seara amanhã) é a 2ª vez da carne. Depois de pastel,
    # esfiha e marmita: "pastel de carne" continua sendo pastel
    ('carne', ('carne', 'picanha', 'alcatra', 'contrafile', 'maminha', 'fraldinha', 'patinho', 'acem', 'cupim',
               'costela', 'file mignon', 'coxao', 'musculo', 'bife')),
]


def categoria(nome):
    """'X-Bacon Duplo' -> 'hambúrguer'. Sem acento e minúsculo; None se não reconhecer."""
    import unicodedata
    t = unicodedata.normalize('NFKD', str(nome or '')).encode('ascii', 'ignore').decode().lower() + ' '
    for cat, chaves in CATEGORIAS:
        if any(t.startswith(c) or f' {c}' in t for c in chaves):
            return cat
    return None


class Recorrencias:
    def __init__(self, dic, agora=time.time):
        self.dic = dic
        self.agora = agora

    def _todas(self, wa_id):
        return list(self.dic.get(wa_id) or [])

    def _gravar(self, wa_id, recs):
        if recs:
            self.dic[wa_id] = recs
        else:
            self.dic.pop(wa_id, None)

    def criar(self, wa_id, pedido, dias, pagamento=None, ciclo=None, hora=None):
        """`ciclo` em segundos substitui `dias` e `hora` só na 1ª vez (modo demo: vence em 1 minuto,
        mas a pessoa vê o combinado normal, "todo dia às 18h")."""
        proximo = self.agora() + (ciclo or int(dias) * 86400)
        if hora and not ciclo:
            proximo = _na_hora(proximo, hora)
        # modelo (sem pedido feito: "todo dia às 7h, 2 pães") se identifica pela loja e pelo que leva
        chave = pedido['id'] or ('modelo', pedido.get('loja_id'), pedido.get('resumo'))
        recs = [r for r in self._todas(wa_id)
                if (r.get('pedido_id') or ('modelo', r.get('loja_id'), r.get('resumo'))) != chave]
        rec = {'id': secrets.token_hex(3), 'pedido_id': pedido['id'], 'dias': int(dias),
               'resumo': pedido.get('resumo', ''), 'loja': pedido.get('loja'),
               'total': pedido.get('total'), 'subtotal': pedido.get('subtotal'), 'pagamento': pagamento, 'ciclo': ciclo, 'hora': hora,
               'proximo': proximo, 'avisado': False,
               'loja_id': pedido.get('loja_id'), 'itens': pedido.get('itens')}
        recs.append(rec)
        self._gravar(wa_id, recs[-10:])
        return rec

    def pegar(self, wa_id, rid):
        return next((r for r in self._todas(wa_id) if r['id'] == rid), None)

    def remover(self, wa_id, rid):
        self._gravar(wa_id, [r for r in self._todas(wa_id) if r['id'] != rid])

    def remover_todas(self, wa_id):
        n = len(self._todas(wa_id))
        self._gravar(wa_id, [])
        return n

    def _mudar(self, wa_id, rid, **campos):
        recs = self._todas(wa_id)
        for r in recs:
            if r['id'] == rid:
                r.update(campos)
        self._gravar(wa_id, recs)

    def avisado(self, wa_id, rid):
        self._mudar(wa_id, rid, avisado=True)

    def respondido(self, wa_id, rid):
        """Pessoa tocou num botão do lembrete: agenda o próximo ciclo."""
        rec = self.pegar(wa_id, rid)
        if rec:
            self._mudar(wa_id, rid, avisado=False, proximo=self.agora() + rec['dias'] * 86400)

    def guardar_valores(self, wa_id, rid, subtotal, total):
        """Pedido saiu pelo lembrete: o próximo já mostra o total com entrega que a pessoa pagou."""
        self._mudar(wa_id, rid, subtotal=subtotal, total=total)

    def vencido_sem_aviso(self, wa_id):
        agora = self.agora()
        return next((r for r in self._todas(wa_id) if r['proximo'] <= agora and not r.get('avisado')), None)


def preco_da_ultima_vez(rec):
    """('total', valor) quando já se sabe quanto a pessoa pagou com entrega; senão ('subtotal', valor) dos
    itens (automático montado sem pedido ainda). O lembrete compara a mesma grandeza que mostra."""
    if not rec.get('pedido_id') and 'subtotal' not in rec:  # modelo antigo guardava o subtotal em 'total'
        return 'subtotal', rec.get('total')
    if rec.get('total'):
        return 'total', rec['total']
    return 'subtotal', rec.get('subtotal')


def _na_hora(ts, hora):
    """Mesmo dia de `ts`, no horário 'HH:MM' de Brasília (UTC-3, sem horário de verão desde 2019)."""
    try:
        h, _, m = str(hora).partition(':')
        alvo = int(h) * 3600 + int(m or 0) * 60
    except ValueError:
        return ts
    meia_noite = ts - (ts - 3 * 3600) % 86400
    return meia_noite + alvo


def botoes_lembrete(rec):
    from src.bot import textos as T
    return [(f'lem:pedir:{rec["id"]}', T.B_LEMBRETE_PEDIR), (f'lem:hoje:{rec["id"]}', T.B_LEMBRETE_HOJE_NAO),
            (f'lem:parar:{rec["id"]}', T.B_LEMBRETE_PARAR)]


def disparar_vencidos(estado, wpp, dic_rec=None, agora=None, so=None):
    """Cron: avisa quem tem lembrete vencido. Devolve contadores pro log."""
    import modal

    from src.bot import textos as T
    dic_rec = dic_rec if dic_rec is not None else modal.Dict.from_name('hackfood-recorrencias', create_if_missing=True)
    agora = agora or time.time()
    template = os.environ.get('TEMPLATE_LEMBRETE', '')
    cont = {'janela': 0, 'template': 0, 'adiado': 0, 'erro': 0}
    store = Recorrencias(dic_rec, agora=lambda: agora)
    for wa_id in ([so] if so else list(dic_rec.keys())):
        rec = store.vencido_sem_aviso(wa_id)
        if not rec:
            continue
        u = estado.get(f'u:{wa_id}') or {}
        try:
            if agora - float(u.get('ultima_msg') or 0) < JANELA:
                texto = T.lembrete(rec, u.get('endereco'), (u.get('pagamento_preferido') or {}).get('nome'))
                wpp.botoes(wa_id, texto, botoes_lembrete(rec))
                u['fase'] = 'lembrete'
                u['pergunta'] = {'texto': texto,
                                 'botoes': [list(b) for b in botoes_lembrete(rec)],
                                 'titulos': [b[1] for b in botoes_lembrete(rec)]}
                estado[f'u:{wa_id}'] = u
                cont['janela'] += 1
            elif template and template != 'PREENCHER':
                wpp.template(wa_id, template, componentes=[
                    {'type': 'body', 'parameters': [{'type': 'text', 'text': rec.get('resumo', '')[:900]}]}])
                cont['template'] += 1
            else:
                cont['adiado'] += 1
                continue  # fica "vencido sem aviso": aparece quando a pessoa voltar
            store.avisado(wa_id, rec['id'])
        except Exception as e:  # noqa: BLE001
            print(f'lembrete {wa_id} falhou: {e!r}')
            cont['erro'] += 1
    return cont


def agenda(dic_rec, agora=None):
    """Pro painel (src/shared/painel.anotar_varredura): quantos lembretes estão ligados, de quantas pessoas, quando
    vence o próximo e quantos venceram sem aviso (janela fechada: esperam a pessoa voltar). Só conta; nunca falha."""
    agora = agora or time.time()
    try:
        ativos = pessoas = vencidos = 0
        proximo = None
        for wa_id in list(dic_rec.keys()):
            recs = list(dic_rec.get(wa_id) or [])
            pessoas += bool(recs)
            for r in recs:
                ativos += 1
                if float(r.get('proximo') or 0) <= agora:
                    vencidos += not r.get('avisado')
                elif proximo is None or r['proximo'] < proximo:
                    proximo = r['proximo']
        return {'ativos': ativos, 'pessoas': pessoas, 'vencidos': vencidos, 'proximo': proximo}
    except Exception as e:  # noqa: BLE001 - a varredura segue sem a agenda
        print(f'agenda dos lembretes falhou: {e!r}')
        return {}
