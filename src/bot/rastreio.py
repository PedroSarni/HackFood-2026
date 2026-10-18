"""Acompanhar o pedido depois do submitOrder e avisar cada mudança no WhatsApp.

O MCP não tem push: é consulta (trackOrder). O próprio iFood diz quando consultar de novo
(agentHints.retryMessage) e quando parar (agentHints.pollingStop), e a gente segue isso em vez
de um intervalo fixo (docs/contexto-evento.md). Sem dica, consulta a cada INTERVALO.
"""
import re
import time

from src.bot import textos as T
from src.bot import voz
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao

# leve de propósito: o firewall do iFood barra IP por volume (17/10) e pedido de conta de teste nunca
# chega em "entregue", então cada pedido de teste ficava consultando por horas.
INTERVALO = 90
MIN_INTERVALO = 60
MAX_INTERVALO = 300
DURACAO_MAX = 90 * 60
FINAIS = {'DELIVERED', 'CONCLUDED', 'CANCELLED', 'CANCELED'}
PRIMEIRA_ESPERA = 10


def segundos_da_dica(dica, padrao=INTERVALO):
    """'Check again in 2 minutes' / 'consulte novamente em 30 segundos' -> segundos."""
    if isinstance(dica, (int, float)):
        return max(MIN_INTERVALO, min(MAX_INTERVALO, int(dica)))
    m = re.search(r'(\d+)\s*(s|seg|sec|min|m\b|minut)', str(dica or '').lower())
    if not m:
        return padrao
    n = int(m.group(1))
    if m.group(2).startswith(('min', 'm')):
        n *= 60
    return max(MIN_INTERVALO, min(MAX_INTERVALO, n))


def acompanhar(ctx, wa_id, pedido_id, dormir=time.sleep, relogio=time.time):
    """Cada mudança de status vira aviso (em áudio, pra quem pediu tudo áudio: src/bot/voz.py).
    Acabou o acompanhamento, de qualquer jeito: acaba também a sessão do modo áudio."""
    try:
        return _acompanhar(ctx, wa_id, pedido_id, dormir, relogio)
    finally:
        voz.encerrar_depois_do_pedido(ctx, wa_id)


def _acompanhar(ctx, wa_id, pedido_id, dormir, relogio):
    # o "pedido feito" em áudio leva ~3 s pra sair (roteiro + voz): sem essa espera, o 1º status
    # ("a loja confirmou") podia chegar antes dele
    dormir(PRIMEIRA_ESPERA)
    inicio = relogio()
    ultimo = None
    falhas = 0
    while relogio() - inicio < DURACAO_MAX:
        try:
            st = ctx.ifood(wa_id).rastrear(pedido_id)
            falhas = 0
        except SemAutorizacao:
            print(f'rastreio {pedido_id}: sem autorização, parando')
            return 'sem_autorizacao'
        except ErroMCP as e:
            falhas += 1
            print(f'rastreio {pedido_id}: {e!r}')
            if falhas >= 3 or 'NOT_FOUND' in str(e.codigo) or 'ACCESS_DENIED' in str(e.codigo) \
                    or str(e.codigo).startswith('HTTP_4'):  # barrado/recusado: insistir só piora
                return 'erro'
            dormir(INTERVALO)
            continue
        codigo = st.get('codigo')
        if codigo and codigo != ultimo:
            if codigo != 'ORDER_CREATED':  # "registrado" a pessoa já soube na confirmação
                voz.avisar(ctx, wa_id, T.status_pedido(codigo, st.get('descricao')))
            ultimo = codigo
        # a doc manda decidir o fim pelo pollingStop (a lista de códigos terminais não é fechada)
        if st.get('parar') or codigo in FINAIS:
            return codigo or 'parou'
        dormir(segundos_da_dica(st.get('proxima')))
    return 'tempo_esgotado'
