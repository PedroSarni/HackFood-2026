"""Otto, o ouvinte: transcreve o áudio da pessoa (ElevenLabs Scribe) antes da Lia entender.

Pra melhorar: src/shared/scribe.py (SCRIBE_MODELO). Não tem prompt: é um serviço de transcrição.
"""
from src.agentes import Agente


def _modelo():
    from src.shared import scribe
    return 'elevenlabs:' + scribe._cfg('SCRIBE_MODELO', 'scribe_v2')


FICHA = Agente(
    id='ouvido', nome='Otto', cargo='Ouvinte', emoji='🎧', cor='#64748b',
    bordao='Pode mandar áudio, com barulho de panela e tudo.',
    faz='Transforma o áudio da pessoa em texto pra Lia entender.',
    plano_b='Sem ele, o próprio Gemini ouve o áudio junto com a Lia (um pouco mais lento).',
    arquivos=('src/agentes/ouvido.py', 'src/shared/scribe.py'),
    tipo='servico', keys=('ELEVENLABS_API_KEY',), servico_modelo=_modelo,
)
