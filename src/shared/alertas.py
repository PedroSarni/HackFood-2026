"""Central de notificações do dash: avisos que alguém do time precisa ver (créditos do Claude acabaram, key
recusada, Claude voltou). Moram no armazém (hackfood-estado, chave `alertas`): o bot escreve, o servidor
local do dash lê (GET /api/alertas) e marca como lidas (POST /api/alertas/lidas).

O mesmo problema repetindo (cada container avisa por conta própria, a cada 10 min) não vira uma pilha:
enquanto o aviso não for lido e tiver menos de JUNTAR, ele só ganha +1 em `vezes` e a hora nova.
"""
import secrets
import time

CHAVE = 'alertas'
MAX = 50
JUNTAR = 6 * 3600
NIVEL = {'claude_sem_credito': 'erro', 'claude_key': 'erro', 'claude_voltou': 'ok'}


def registrar(armazem, tipo, titulo, detalhe='', agora=None):
    agora = agora or time.time()
    try:
        lista = [a for a in (armazem.get(CHAVE) or []) if isinstance(a, dict)]
        igual = next((a for a in lista if a.get('tipo') == tipo and not a.get('lida')
                      and agora - float(a.get('ultima') or 0) < JUNTAR), None)
        if igual:
            igual.update(ultima=agora, vezes=int(igual.get('vezes') or 1) + 1, detalhe=detalhe or igual.get('detalhe'))
        else:
            lista.insert(0, {'id': secrets.token_hex(4), 'tipo': tipo, 'nivel': NIVEL.get(tipo, 'aviso'),
                             'titulo': titulo, 'detalhe': detalhe, 'quando': agora, 'ultima': agora,
                             'vezes': 1, 'lida': False})
        armazem[CHAVE] = lista[:MAX]
    except Exception as e:  # noqa: BLE001 - alerta nunca derruba a conversa
        print(f'alertas: registrar {tipo} falhou: {e!r}')


def listar(armazem):
    lista = [a for a in (armazem.get(CHAVE) or []) if isinstance(a, dict)]
    return {'alertas': lista, 'naoLidas': sum(1 for a in lista if not a.get('lida'))}


def marcar_lidas(armazem):
    lista = [dict(a, lida=True) for a in (armazem.get(CHAVE) or []) if isinstance(a, dict)]
    armazem[CHAVE] = lista
    return listar(armazem)
