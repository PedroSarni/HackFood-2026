"""Boca do bot: texto vira nota de voz (text-to-speech da ElevenLabs), irmã do Scribe (scribe.py).

Só fala com quem PEDIU resposta em áudio (src/bot/voz.py decide quando). Mesmo secret e mesma key
do Scribe, `hackathon-elevenlabs`; a key precisa das permissões `speech_to_text` E `text_to_speech`
(a 1ª key só tinha a do Scribe, trocada em 17/10 22h30). Com a ElevenLabs fora, `falar` levanta
ErroVoz e o fluxo manda as mensagens escritas de sempre.

Variáveis (vazias = padrão):
- VOZ_ID: voz da biblioteca da ElevenLabs (padrão: Roberta, pt-BR, "conversational"). Outras
  testadas em 17/10: Raquel GDzHdQOi6jjf8zaXhCYD, Ana Alice ORgG8rwdAiMYRug8RJwR, Davi 5p9IbzcK4R8rN1fpGdMF;
- VOZ_MODELO: `eleven_flash_v2_5` (~1 s pra uma fala de 10 s, medido) ou `eleven_multilingual_v2`
  (~2,5 s e não aceita language_code);
- VOZ_VELOCIDADE: 0.7 a 1.2 (padrão 1.0).

Formato: o WhatsApp só mostra como nota de voz (play + onda, `voice: true`) ogg/opus mono até
512 KB. `opus_48000_32` dá ~4 KB por segundo: 30 s de fala = ~120 KB.
API: POST /v1/text-to-speech/{voice_id}?output_format=..., JSON {text, model_id}, header `xi-api-key`.
"""
import os
import time

import httpx

URL = 'https://api.elevenlabs.io/v1/text-to-speech/{voz}'
VOZ_PADRAO = 'RGymW84CSmfVugnA5tvA'  # Roberta: pt-BR da biblioteca, tom de conversa
MODELO_PADRAO = 'eleven_flash_v2_5'
FORMATO = 'opus_48000_32'
MIME = 'audio/ogg'
PRAZO = 12.0          # a pessoa está esperando a resposta: estourou, vai por escrito
MAX_CARACTERES = 900  # ~1 min de fala; o roteiro (src/bot/voz.py) já mira bem menos
MAX_BYTES = 512 * 1024
SEM_PERMISSAO_SEG = 600  # key sem permissão: não insiste a cada mensagem, tenta de novo em 10 min

_freio = {'ate': 0.0}


class ErroVoz(Exception):
    pass


def _cfg(nome, padrao=''):
    v = os.environ.get(nome, '')
    return padrao if v in ('', 'PREENCHER') else v


def ligado():
    return bool(_cfg('ELEVENLABS_API_KEY')) and _cfg('VOZ_DESLIGADA') not in ('1', 'true', 'sim')


def falar(texto, http=None):
    """texto -> (mime, bytes) de uma nota de voz ogg/opus mono, pronta pro WhatsApp.
    Levanta ErroVoz se não der: quem chama manda por escrito."""
    if not ligado():
        raise ErroVoz('ELEVENLABS_API_KEY não configurada')
    if time.time() < _freio['ate']:
        raise ErroVoz('key sem permissão de text_to_speech (freio ligado)')
    texto = ' '.join(str(texto or '').split())[:MAX_CARACTERES]
    if not texto:
        raise ErroVoz('nada pra falar')
    modelo = _cfg('VOZ_MODELO', MODELO_PADRAO)
    # pausa no fim: sem ela o flash às vezes come a última palavra e o WhatsApp corta o resto
    # (17/10: 1 em 8 sem a última palavra; com a pausa, 8 em 8 inteiros e ~1 s de folga)
    corpo = {'text': f'{texto} <break time="0.7s" />', 'model_id': modelo,
             'voice_settings': {'stability': 0.45, 'similarity_boost': 0.75, 'style': 0.0,
                                'use_speaker_boost': True, 'speed': float(_cfg('VOZ_VELOCIDADE', '1.0'))}}
    if not modelo.startswith('eleven_multilingual'):
        corpo['language_code'] = 'pt'  # sem isso o flash pode puxar o sotaque pra outra língua
    try:
        r = (http or httpx).post(URL.format(voz=_cfg('VOZ_ID', VOZ_PADRAO)), params={'output_format': FORMATO},
                                 headers={'xi-api-key': _cfg('ELEVENLABS_API_KEY')}, json=corpo, timeout=PRAZO)
    except httpx.HTTPError as e:
        raise ErroVoz(f'rede: {e!r}') from e
    if r.status_code != 200:
        if r.status_code == 401 and 'permission' in r.text:
            _freio['ate'] = time.time() + SEM_PERMISSAO_SEG
        raise ErroVoz(f'HTTP {r.status_code}: {" ".join(r.text.split())[:200]}')
    dados = r.content
    if not dados.startswith(b'OggS'):  # o WhatsApp recusa nota de voz que não é ogg
        raise ErroVoz(f'não veio ogg: {dados[:8]!r} ({r.headers.get("content-type")})')
    if len(dados) > MAX_BYTES:
        raise ErroVoz(f'áudio grande demais pra nota de voz: {len(dados)} bytes')
    return MIME, dados
