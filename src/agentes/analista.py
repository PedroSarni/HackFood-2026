"""Sofia, a analista: no dash, lê os números de uma página e escreve insights pros times do iFood.

Não conversa com cliente: roda quando alguém toca no botão de IA (Conversão, Clientes, Mercado).
Pra melhorar: prompt e validação em src/painel/analista.py; a fila de modelos é aqui (análise aguenta um modelo
mais lento e mais esperto que o do chat).
"""
from src.agentes import Agente


def _sistemas():
    from src.painel import analista
    return [analista.SISTEMA]


FICHA = Agente(
    id='analista', nome='Sofia', cargo='Analista', emoji='📊', cor='#0f766e',
    bordao='Número sem ação é enfeite. Me diz a página que eu digo quem mexe no quê.',
    faz='Lê os números da página do dash e escreve insights com time dono, ação, prazo e métrica.',
    plano_b='Sem ela, o dash mostra só os números; o botão de IA avisa que ela está de folga.',
    arquivos=('src/agentes/analista.py', 'src/painel/analista.py'),
    sistemas=_sistemas,
    onde='painel',   # o Maestro não rege a Sofia: ela fica fora do palco da conversa
    modelos=[('claude-sonnet-5-5', 40.0, 'low'), ('gemini-3.8-flash', 25.0, 'low'), ('gemini-3.5-flash-lite', 12.0, '')],
)
