"""Tito, o tutor: quando a pessoa trava ou sai do roteiro, explica com calma o próximo passo.

Pra melhorar: prompt e situações em src/bot/tutor.py (SISTEMA, SITUACOES).
"""
from src.agentes import Agente


def _sistemas():
    from src.bot import tutor
    return [tutor.SISTEMA]


FICHA = Agente(
    id='tutor', nome='Tito', cargo='Tutor', emoji='🧑‍🏫', cor='#eab308',
    bordao='Calma, sem pressa: toca no botão verde que eu te mostro o resto.',
    faz='Escreve a ajuda do momento quando dá erro ou a pessoa se perde.',
    plano_b='Sem ele, vai o texto fixo de ajuda daquela situação.',
    arquivos=('src/agentes/tutor.py', 'src/bot/tutor.py'),
    sistemas=_sistemas,
)
