"""Compra recorrente: "me lembra de pedir isso toda semana".

Cada lembrete guarda o pedido de origem (o iFood refaz o carrinho com createCart(orderId)).
Nada é comprado sozinho: o lembrete só oferece o botão "Pedir de novo" e o fluxo normal
termina no resumo com "Confirmar pedido".

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

    def criar(self, wa_id, pedido, dias):
        recs = [r for r in self._todas(wa_id) if r.get('pedido_id') != pedido['id']]
        rec = {'id': secrets.token_hex(3), 'pedido_id': pedido['id'], 'dias': int(dias),
               'resumo': pedido.get('resumo', ''), 'loja': pedido.get('loja'),
               'proximo': self.agora() + int(dias) * 86400, 'avisado': False}
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

    def vencido_sem_aviso(self, wa_id):
        agora = self.agora()
        return next((r for r in self._todas(wa_id) if r['proximo'] <= agora and not r.get('avisado')), None)


def botoes_lembrete(rec):
    from src.bot import textos as T
    return [(f'lem:pedir:{rec["id"]}', T.B_LEMBRETE_PEDIR), (f'lem:hoje:{rec["id"]}', T.B_LEMBRETE_HOJE_NAO),
            (f'lem:parar:{rec["id"]}', T.B_LEMBRETE_PARAR)]


def disparar_vencidos(estado, wpp, dic_rec=None, agora=None):
    """Cron: avisa quem tem lembrete vencido. Devolve contadores pro log."""
    import modal

    from src.bot import textos as T
    dic_rec = dic_rec if dic_rec is not None else modal.Dict.from_name('hackfood-recorrencias', create_if_missing=True)
    agora = agora or time.time()
    template = os.environ.get('TEMPLATE_LEMBRETE', '')
    cont = {'janela': 0, 'template': 0, 'adiado': 0, 'erro': 0}
    store = Recorrencias(dic_rec, agora=lambda: agora)
    for wa_id in list(dic_rec.keys()):
        rec = store.vencido_sem_aviso(wa_id)
        if not rec:
            continue
        u = estado.get(f'u:{wa_id}') or {}
        try:
            if agora - float(u.get('ultima_msg') or 0) < JANELA:
                wpp.botoes(wa_id, T.lembrete(rec.get('resumo', '')), botoes_lembrete(rec))
                u['fase'] = 'lembrete'
                u['pergunta'] = {'texto': T.lembrete(rec.get('resumo', '')),
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
