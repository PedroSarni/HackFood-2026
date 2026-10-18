"""Lia, a intérprete: lê cada mensagem (texto, áudio, botão) e devolve o que a pessoa quer, em JSON.

Pra melhorar: o prompt e o esquema estão em src/bot/interpretar.py (SISTEMA, ESQUEMA); a fila de modelos é aqui.
"""
from src.agentes import Agente


def _sistemas():
    from src.bot import interpretar
    return [interpretar.SISTEMA]


FICHA = Agente(
    id='entendimento', nome='Lia', cargo='Intérprete', emoji='🧠', cor='#7a5af8',
    bordao='"Qero pao e lete"? Pode deixar, eu entendi: pão e leite.',
    faz='Lê toda mensagem e diz ao Maestro o que a pessoa quer: buscar, escolher, mudar, pagar, acompanhar...',
    plano_b='Sem ela, texto curto vira busca direta no iFood ("pão", "leite integral"); frase longa recebe um '
            '"não entendi" com botões.',
    arquivos=('src/agentes/entendimento.py', 'src/bot/interpretar.py'),
    sistemas=_sistemas, essencial=True,
)
