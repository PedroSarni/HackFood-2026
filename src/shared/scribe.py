"""Ouvido do bot: o áudio do WhatsApp vira texto no Scribe (speech-to-text da ElevenLabs).

Secret Modal `hackathon-elevenlabs`: só a ELEVENLABS_API_KEY (vazia ou PREENCHER = desligado, e o
áudio vai pro Gemini ouvir, como antes). Áudio só ENTRA: o bot continua respondendo por escrito.
Transcrito, ele segue o caminho de uma mensagem digitada (src/bot/fluxo.py, `livre`): botão,
endereço, sugestão, tudo igual.

Por que tirar a escuta do Gemini: cada nota de voz era uma chamada multimodal pesada na mesma fila
que deu 503/429 em 17/10 20h27; agora o Gemini só recebe texto.
API: POST /v1/speech-to-text, multipart com `file` + `model_id`, header `xi-api-key`.
"""
import os

import httpx

URL = 'https://api.elevenlabs.io/v1/speech-to-text'
PRAZO = 20.0  # nota de voz curta volta em poucos segundos; estourou, o Gemini ouve no lugar


class ErroScribe(Exception):
    pass


def _cfg(nome, padrao=''):
    v = os.environ.get(nome, '')
    return padrao if v in ('', 'PREENCHER') else v


def ligado():
    return bool(_cfg('ELEVENLABS_API_KEY'))


def transcrever(mime, dados, http=None):
    """bytes de áudio -> texto em português. Levanta ErroScribe se não der: quem chama decide o plano B."""
    if not ligado():
        raise ErroScribe('ELEVENLABS_API_KEY não configurada')
    modelo = _cfg('SCRIBE_MODELO', 'scribe_v2')
    mime = (mime or 'audio/ogg').split(';')[0].strip()
    campos = {'model_id': modelo, 'language_code': 'por', 'tag_audio_events': 'false'}
    if modelo.startswith('scribe_v2'):
        campos['no_verbatim'] = 'true'  # tira "é...", "hum...": "é... sim" casa com o botão Sim
    try:
        r = (http or httpx).post(URL, headers={'xi-api-key': _cfg('ELEVENLABS_API_KEY')}, data=campos,
                                 files={'file': (f'audio.{mime.split("/")[-1]}', dados, mime)},
                                 timeout=PRAZO)
    except httpx.HTTPError as e:
        raise ErroScribe(f'rede: {e!r}') from e
    if r.status_code != 200:
        raise ErroScribe(f'HTTP {r.status_code}: {" ".join(r.text.split())[:200]}')
    texto = ' '.join(str(r.json().get('text') or '').split())
    if not texto:
        raise ErroScribe('não ouviu nada')
    return texto
