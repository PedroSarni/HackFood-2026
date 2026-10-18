"""Beto, o organizador de kits: "pizza pra 11 pessoas" vira um kit com quantidades e bebida.

Pra melhorar: prompt e regras de quantidade em src/bot/grupo.py (SISTEMA, compor).
"""
from src.agentes import Agente


def _sistemas():
    from src.bot import grupo
    return [grupo.SISTEMA]


FICHA = Agente(
    id='grupo', nome='Beto', cargo='Organizador de kits', emoji='🍕', cor='#f97316',
    bordao='Onze pessoas? Quatro pizzas grandes e duas Cocas de 2 L resolvem.',
    faz='Monta o kit pra grupo: quanto de cada coisa, pra quantas pessoas, na loja que tem tudo.',
    plano_b='Sem ele, uma regra fixa calcula o kit (fatias por pessoa e bebida por cabeça).',
    arquivos=('src/agentes/grupo.py', 'src/bot/grupo.py'),
    sistemas=_sistemas,
)
