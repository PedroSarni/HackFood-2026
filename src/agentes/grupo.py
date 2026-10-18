"""Beto, o organizador de kits: "pizza pra 11 pessoas" vira um kit com quantidades e bebida.

Pra melhorar: prompt, receitas (o que é o prato, quanto por pessoa, o que não pode faltar) e regras de quantidade
em src/bot/grupo.py (SISTEMA, RECEITAS, compor); os ajustes do kit ("sem refri", "troca por guaraná") são lidos
pelo código em src/bot/kit_ajuste.py.
"""
from src.agentes import Agente
from src.shared import llm


def _sistemas():
    from src.bot import grupo
    return [grupo.SISTEMA]


FICHA = Agente(
    id='grupo', nome='Beto', cargo='Organizador de kits', emoji='🍕', cor='#f97316',
    bordao='Onze pessoas? Quatro pizzas grandes e duas Cocas de 2 L resolvem.',
    faz='Monta o kit pra grupo: quanto de cada coisa, pra quantas pessoas, na loja que tem tudo.',
    plano_b='Sem ele, a receita monta o kit (fatias por pessoa, bebida por cabeça, carvão no churrasco); os ajustes '
            '("sem refri", "mais batata") o código já aplica sozinho.',
    arquivos=('src/agentes/grupo.py', 'src/bot/grupo.py', 'src/bot/kit_ajuste.py'),
    # 18/10 09h35 (Fabio): o Beto vai de Opus 5.5, SÓ ele (medido: ~8 s por kit, kits coerentes; o Fable levava 8–13 s;
    # o Sonnet fica de reserva). Pensamento 'medium' = effort; o Opus não aceita thinking desligado (src/shared/llm.py).
    modelos=[(llm.CLAUDE_FORTE, 20.0, 'medium')] + llm._modelos(),
    sistemas=_sistemas,
)
