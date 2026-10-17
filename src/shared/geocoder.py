"""Resolve CEP ANTES de ir pro iFood.

O geocode do createAddress entende bem texto bagunçado com nome de rua ("rua episcopal 1500 ap 3
sao carlos" acha certinho), mas CEP solto o deixa perdido: em 17/10 "01310-100, 1578" virou
Canadá, "20040-002, 100" Amsterdã e "13560-010, 1200" Belo Horizonte. Então só quando a mensagem
tem CEP: CEP -> rua/bairro/cidade (BrasilAPI, cai pro ViaCEP; grátis, sem chave) e o iFood recebe
"Avenida Paulista, 1578 - Bela Vista, São Paulo - SP, 01310-100". Invisível pra pessoa: qualquer
falha devolve None e o bot segue com o texto original.
"""
import functools
import re

import httpx

BRASILAPI = 'https://brasilapi.com.br/api/cep/v2/{}'
VIACEP = 'https://viacep.com.br/ws/{}/json/'
TEMPO = 4

_CEP = re.compile(r'\b(\d{5})-?(\d{3})\b')
_COMPL = re.compile(r'\b(apto?|apart\w*|ap|bloco|bl|casa|sala|lote|lt|quadra|qd|torre|andar|conj\w*|cj)'
                    r'\.?\s*[\w-]{0,4}\b', re.I)


def _numero(texto, rua=''):
    """Número da casa = último número solto que sobra (tira CEP, complemento e os números do
    nome da rua, tipo "Rua 7 de Setembro")."""
    nums = re.findall(r'\b\d{1,6}\b', _COMPL.sub(' ', _CEP.sub(' ', texto)))
    for n in re.findall(r'\d+', rua or ''):
        if n in nums:
            nums.remove(n)
    return nums[-1] if nums else ''


def _montar(rua, numero, bairro, cidade, uf, cep='', lat=None, lng=None):
    texto = rua + (f', {numero}' if numero else '')
    if bairro:
        texto += f' - {bairro}'
    if cidade:
        texto += f', {cidade}' + (f' - {uf}' if uf else '')
    if cep:
        texto += f', {cep[:5]}-{cep[5:]}'
    return {'texto': texto, 'rua': rua, 'numero': numero, 'bairro': bairro or '', 'cidade': cidade or '',
            'uf': uf or '', 'cep': cep, 'lat': lat, 'lng': lng}


def _consultar(cep, http):
    """CEP -> (rua, bairro, cidade, uf, lat, lng) ou None."""
    try:
        d = http.get(BRASILAPI.format(cep), timeout=TEMPO).raise_for_status().json()
        coords = (d.get('location') or {}).get('coordinates') or {}
        return (d.get('street'), d.get('neighborhood'), d.get('city'), d.get('state'),
                coords.get('latitude'), coords.get('longitude'))
    except (httpx.HTTPError, ValueError):
        pass
    try:
        d = http.get(VIACEP.format(cep), timeout=TEMPO).raise_for_status().json()
    except (httpx.HTTPError, ValueError):
        return None
    if d.get('erro'):
        return None
    return d.get('logradouro'), d.get('bairro'), d.get('localidade'), d.get('uf'), None, None


def normalizar(texto, http=None):
    """Texto com CEP -> endereço canônico pro iFood; sem CEP (ou CEP que não resolve) -> None."""
    texto = ' '.join((texto or '').split())
    m = _CEP.search(texto)
    if not m:
        return None
    cep = m.group(1) + m.group(2)
    if http is not None:
        return _resolver(cep, texto, http)
    return _resolver_cache(cep, texto)


@functools.lru_cache(maxsize=256)
def _resolver_cache(cep, texto):
    with httpx.Client() as http:
        return _resolver(cep, texto, http)


def _resolver(cep, texto, http):
    try:
        achado = _consultar(cep, http)
        if not achado or not achado[0]:  # CEP geral da cidade não diz a rua: vai o texto cru
            return None
        rua, bairro, cidade, uf, lat, lng = achado
        return _montar(rua, _numero(texto, rua), bairro, cidade, (uf or '').upper(), cep,
                       float(lat) if lat else None, float(lng) if lng else None)
    except Exception as e:  # noqa: BLE001 - ajuda opcional: nunca derruba o fluxo
        print(f'consulta de CEP falhou: {e!r}')
        return None
