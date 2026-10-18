"""Vina, a locutora: no modo áudio, transforma a resposta num roteiro falado e grava a nota de voz (ElevenLabs).

Pra melhorar: roteiro em src/bot/voz.py (SISTEMA, MODELOS_ROTEIRO, que é a fila curta: áudio tem pressa);
a voz em si em src/shared/voz.py (VOZ_MODELO, VOZ_ID).
"""
from src.agentes import Agente


def _sistemas():
    from src.bot import voz
    return [voz.SISTEMA]


def _fila_do_codigo():
    from src.bot import voz
    return voz.MODELOS_ROTEIRO


FICHA = Agente(
    id='voz', nome='Vina', cargo='Locutora', emoji='🎙️', cor='#ec4899',
    bordao='Prefere ouvir? Eu leio tudo pra você, bem devagarinho.',
    faz='Escreve o roteiro da fala e grava o áudio que vai pro WhatsApp.',
    plano_b='Sem ela, a resposta vai por escrito.',
    arquivos=('src/agentes/voz.py', 'src/bot/voz.py', 'src/shared/voz.py'),
    keys=('ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'ELEVENLABS_API_KEY'),
    sistemas=_sistemas, extra={'fila_do_codigo': _fila_do_codigo},
)
