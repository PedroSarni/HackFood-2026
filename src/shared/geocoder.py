"""Geocodificador gratuito que arruma o endereço ANTES de ir pro iFood.

O geocode do createAddress erra fácil com texto bagunçado ("rua episcopal 1500 apto 3 sanca").
Aqui o texto vira um endereço canônico ("Rua Episcopal, 1500 - Centro, São Carlos - SP"), que o
iFood acha de primeira, e de quebra vêm bairro e coordenadas pra completar o que o iFood não
devolver. Tudo invisível pra pessoa: qualquer falha devolve None e o bot segue com o texto original.

Fontes (grátis, sem chave): CEP -> BrasilAPI (cai pro ViaCEP); texto livre -> Nominatim (OSM,
máx. 1 req/s e User-Agent obrigatório).
"""
import functools
import re
import unicodedata

import httpx

NOMINATIM = 'https://nominatim.openstreetmap.org/search'
BRASILAPI = 'https://brasilapi.com.br/api/cep/v2/{}'
VIACEP = 'https://viacep.com.br/ws/{}/json/'
AGENTE = {'User-Agent': 'hackfood-bot/1.0 (araujo.fabio@usp.br)'}
TEMPO = 4

UFS = {'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM', 'bahia': 'BA', 'ceara': 'CE',
       'distrito federal': 'DF', 'espirito santo': 'ES', 'goias': 'GO', 'maranhao': 'MA',
       'mato grosso': 'MT', 'mato grosso do sul': 'MS', 'minas gerais': 'MG', 'para': 'PA',
       'paraiba': 'PB', 'parana': 'PR', 'pernambuco': 'PE', 'piaui': 'PI', 'rio de janeiro': 'RJ',
       'rio grande do norte': 'RN', 'rio grande do sul': 'RS', 'rondonia': 'RO', 'roraima': 'RR',
       'santa catarina': 'SC', 'sao paulo': 'SP', 'sergipe': 'SE', 'tocantins': 'TO'}

_CEP = re.compile(r'\b(\d{5})-?(\d{3})\b')
# complemento atrapalha o geocode: sai antes da busca ("apto 12", "bloco b", "casa 2", "fundos")
_COMPL = re.compile(r'\b(apto?|apart\w*|ap|bloco|bl|casa|sala|lote|lt|quadra|qd|torre|andar|conj\w*|cj)'
                    r'\.?\s*[\w-]{0,4}\b|\bfundos\b', re.I)


def _sem_acento(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


def _uf(estado):
    estado = (estado or '').strip()
    return estado.upper() if len(estado) == 2 else UFS.get(_sem_acento(estado), estado)


def _numero(texto, rua=''):
    """Número da casa = último número solto que sobra (tira CEP, complemento e os números do
    nome da rua, tipo "Rua 7 de Setembro")."""
    t = _COMPL.sub(' ', _CEP.sub(' ', texto))
    da_rua = re.findall(r'\d+', rua or '')
    nums = re.findall(r'\b\d{1,6}\b', t)
    for n in da_rua:
        if n in nums:
            nums.remove(n)
    return nums[-1] if nums else ''


_GENERICOS = {'jardim', 'jd', 'vila', 'parque', 'pq', 'nucleo', 'residencial', 'conjunto', 'bairro',
              'chacara', 'loteamento', 'cidade', 'recanto', 'de', 'da', 'do', 'das', 'dos'}


def _citou_bairro(bairro, texto):
    """"sylvio villari" conta como "Núcleo Residencial Sylvio Villari": ignora os prefixos genéricos."""
    palavras = re.findall(r'\w+', _sem_acento(bairro))
    nucleo = [p for p in palavras if p not in _GENERICOS] or palavras
    escrito = set(re.findall(r'\w+', _sem_acento(texto)))
    return all(p in escrito for p in nucleo)


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


def _por_cep(cep, texto, http):
    try:
        d = http.get(BRASILAPI.format(cep), timeout=TEMPO).raise_for_status().json()
        coords = (d.get('location') or {}).get('coordinates') or {}
        rua, bairro, cidade, uf = d.get('street'), d.get('neighborhood'), d.get('city'), d.get('state')
        lat, lng = coords.get('latitude'), coords.get('longitude')
    except (httpx.HTTPError, ValueError):
        try:
            d = http.get(VIACEP.format(cep), timeout=TEMPO).raise_for_status().json()
        except (httpx.HTTPError, ValueError):
            return None
        if d.get('erro'):
            return None
        rua, bairro, cidade, uf, lat, lng = d.get('logradouro'), d.get('bairro'), d.get('localidade'), d.get('uf'), None, None
    if not rua:  # CEP geral da cidade: não diz a rua, melhor deixar o Nominatim tentar
        return None
    return _montar(rua, _numero(texto, rua), bairro, cidade, _uf(uf), cep,
                   float(lat) if lat else None, float(lng) if lng else None)


def _nominatim(consulta, perto, http):
    q = {'q': consulta, 'countrycodes': 'br', 'format': 'jsonv2', 'addressdetails': 1, 'limit': 1,
         'accept-language': 'pt-BR'}
    if perto:  # trava perto da pessoa (~30 km), pra "rua das flores 10" não cair em outro estado
        lat, lng = perto
        q.update(viewbox=f'{lng - .3},{lat + .3},{lng + .3},{lat - .3}', bounded=1)
    try:
        r = http.get(NOMINATIM, params=q, headers=AGENTE, timeout=TEMPO).raise_for_status().json()
    except (httpx.HTTPError, ValueError):
        return None
    if not r or not (r[0].get('address') or {}).get('road'):
        return None
    return r[0]


def normalizar(texto, perto=None, http=None):
    """Texto livre -> endereço canônico pro iFood, ou None se não achou (aí use o texto original).
    `perto` = (lat, lng) de onde a pessoa costuma estar, se souber."""
    texto = ' '.join((texto or '').split())
    if len(texto) < 5:
        return None
    perto = tuple(round(float(x), 2) for x in perto) if perto else None
    if http is not None:
        return _normalizar_com(texto, perto, http)
    return _normalizar_cache(texto, perto)


@functools.lru_cache(maxsize=256)
def _normalizar_cache(texto, perto):
    with httpx.Client() as http:
        return _normalizar_com(texto, perto, http)


def _normalizar_com(texto, perto, http):
    try:
        m = _CEP.search(texto)
        if m:
            achado = _por_cep(m.group(1) + m.group(2), texto, http)
            if achado:
                return achado
        limpo = ' '.join(_COMPL.sub(' ', _CEP.sub(' ', texto)).split()).strip(' ,-')
        sem_numero = re.sub(r'\b\d{1,6}\b(?!.*\b\d{1,6}\b)', ' ', limpo)  # às vezes só acha sem o número
        r = None
        for consulta in dict.fromkeys((limpo, sem_numero)):
            r = _nominatim(consulta, perto, http)
            if r:
                break
        if not r:
            return None
        a = r['address']
        cidade = a.get('city') or a.get('town') or a.get('village') or a.get('municipality') or ''
        # sem âncora (perto) e sem a pessoa citar a cidade, o OSM chuta qualquer "Rua 7 de Setembro"
        # do Brasil: aí é melhor o iFood ver o texto cru do que um endereço de outro estado
        if not perto and _sem_acento(cidade) not in _sem_acento(texto):
            return None
        rua = a['road']
        numero = a.get('house_number') or _numero(texto, rua)
        # bairro do OSM é o do trecho da rua, não o do número: só vai se a pessoa escreveu ele
        bairro = next((b for b in (a.get('suburb'), a.get('neighbourhood'), a.get('quarter'))
                       if b and _citou_bairro(b, texto)), '')
        uf = (a.get('ISO3166-2-lvl4') or '').removeprefix('BR-') or _uf(a.get('state'))
        return _montar(rua, numero, bairro, cidade, uf, lat=float(r['lat']), lng=float(r['lon']))
    except Exception as e:  # noqa: BLE001 - ajuda opcional: nunca derruba o fluxo
        print(f'geocoder grátis falhou: {e!r}')
        return None
