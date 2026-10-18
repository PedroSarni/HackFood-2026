"""Íris, a leitora de fotos: lista de mercado escrita à mão, print de carrinho, foto de produto ou de prato.

Pra melhorar a leitura de imagem: prompt e limpeza em src/bot/foto.py; a fila de modelos (o modelo de visão)
é `modelos` aqui embaixo. Ex.: trocar só o modelo da foto, sem mexer nos outros agentes:
    modelos=[('gemini-3.8-flash', 12.0, 'low'), ('gemini-3.5-flash-lite', 6.0, '')]
"""
from src.agentes import Agente


def _sistemas():
    from src.bot import foto
    return [foto.SISTEMA]


FICHA = Agente(
    id='foto', nome='Íris', cargo='Leitora de fotos', emoji='📷', cor='#0ea5e9',
    bordao='Manda a foto da lista, até com letra de médico eu leio.',
    faz='Olha a foto e diz o que tem nela: lista de compras, produto, prato ou documento (que ela recusa).',
    plano_b='Sem ela, o bot pede pra pessoa escrever o que está na foto.',
    arquivos=('src/agentes/foto.py', 'src/bot/foto.py'),
    sistemas=_sistemas,
)
