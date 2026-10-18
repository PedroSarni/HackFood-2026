"""Boca do bot: texto vira nota de voz (text-to-speech da ElevenLabs).

STUB — dono: Fabio (claim bot-ifood-agent). Em implementação: use esta assinatura, não reimplemente.
"""


class ErroVoz(Exception):
    pass


def ligado():
    return False


def falar(texto, http=None):
    """texto -> (mime, bytes) de uma nota de voz ogg/opus mono, pronta pro WhatsApp."""
    raise ErroVoz('TODO: falar')
