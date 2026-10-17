"""Acompanhar o pedido depois do submitOrder e avisar cada mudança no WhatsApp.

O MCP não tem push: é consulta (trackOrder). O próprio iFood diz quando consultar de novo
(agentHints.retryMessage) e quando parar (agentHints.pollingStop), e a gente segue isso em vez
de um intervalo fixo (docs/contexto-evento.md). Sem dica, consulta a cada INTERVALO.
"""
import re
import time

from src.bot import textos as T
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao

INTERVALO = 60
MIN_INTERVALO = 20
MAX_INTERVALO = 300
DURACAO_MAX = 4 * 3600
FINAIS = {'DELIVERED', 'CONCLUDED', 'CANCELLED', 'CANCELED'}


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
            if falhas >= 5 or 'NOT_FOUND' in str(e.codigo) or 'ACCESS_DENIED' in str(e.codigo):
                return 'erro'
            dormir(INTERVALO)
            continue
        codigo = st.get('codigo')
        if codigo and codigo != ultimo:
            if codigo != 'ORDER_CREATED':  # "registrado" a pessoa já soube na confirmação
                ctx.wpp.texto(wa_id, T.status_pedido(codigo, st.get('descricao')))
            ultimo = codigo
        # a doc manda decidir o fim pelo pollingStop (a lista de códigos terminais não é fechada)
        if st.get('parar') or codigo in FINAIS:
            return codigo or 'parou'
        dormir(segundos_da_dica(st.get('proxima')))
    return 'tempo_esgotado'
