"""Duda, a curadora: das ofertas que o iFood devolve, fica só com o que a pessoa pediu, na ordem certa.

Pra melhorar: prompts em src/bot/relevancia.py (SISTEMA pra uma busca, SISTEMA_VARIOS pra lista inteira).
Fila própria: Haiku na frente (18/10 08h40, Fabio: o Sonnet levava 2–5 s por filtro no ar, e cada busca tem um),
depois a fila de todo mundo.
"""
from src.agentes import Agente
from src.shared import llm


def _sistemas():
    from src.bot import relevancia
    return [relevancia.SISTEMA, relevancia.SISTEMA_VARIOS]


FICHA = Agente(
    id='relevancia', nome='Duda', cargo='Curadora', emoji='🔎', cor='#10b981',
    bordao='Pediu leite? Então nada de doce de leite no meio.',
    faz='Filtra e ordena as ofertas do iFood pra mostrar só o que bate com o pedido.',
    plano_b='Sem ela, o filtro é por palavra; se a palavra zerar ("refri" x "Coca"), mostra o que o iFood deu.',
    arquivos=('src/agentes/relevancia.py', 'src/bot/relevancia.py'),
    modelos=[(llm.CLAUDE_RAPIDO, 6.0, '')] + llm._modelos(),
    sistemas=_sistemas,
)
