"""Bateria de CEPs/endereços contra o geocode REAL do iFood (passo 1 do createAddress: não salva nada).

Usa o token de quem já logou pelo bot (hackfood-estado, tok:<wa_id>). Compara o texto cru com o
texto arrumado pelo src/shared/geocoder.py. Nunca imprime token.

    .venv/Scripts/python.exe -m modal run scripts/testar_ceps.py
"""
import modal

app = modal.App('testar-ceps-tmp')
img = modal.Image.debian_slim(python_version='3.12').pip_install('httpx==0.28.1').add_local_python_source('src')

CASOS = [
    '13560-010', '13560-010, 1200', '01310-100, 1578', '20040-002, 100', '30130-010, 500',
    '70040-010, 10', '40020-000, 50', '80010-000, 200', '90010-000, 300', '69005-000, 100',
    '13560-970', 'rua episcopal 1500 ap 3 sao carlos', 'av sao carlos 2000 centro sao carlos sp',
    'rua 7 de setembro 300 apto 12 campinas', 'avenida paulista 1578 sao paulo',
]


def _resumo(ifood, texto):
    from src.shared.ifood_mcp import ErroMCP
    try:
        r = ifood.geocodificar(texto)
    except ErroMCP as e:
        return f'ERRO {e.codigo}'
    if r.get('criado'):
        return f'criado direto: {r["criado"].get("texto")}'
    cands = r.get('candidatos') or []
    if not cands:
        return '0 candidatos'
    c = cands[0]
    return (f'{len(cands)} cand. | 1º: {c.get("texto")} | bairro={c.get("bairro") or "-"} '
            f'| coord={"sim" if c.get("lat") is not None else "NÃO"}')


@app.function(image=img, secrets=[modal.Secret.from_name('hackathon-ifood')], timeout=600)
def bateria():
    import time
    from src.bot.contexto import chamador_real
    from src.bot.ifood import Ifood
    from src.shared import geocoder

    estado = modal.Dict.from_name('hackfood-estado')
    contas = [k for k in estado.keys() if str(k).startswith('tok:')]
    if not contas:
        return ['ninguém logado: entre pelo bot primeiro']
    wa = contas[0].removeprefix('tok:')
    ifood = Ifood(chamador_real(estado, wa))
    linhas = [f'conta: ...{wa[-4:]} ({len(contas)} logada(s))']
    for texto in CASOS:
        norm = geocoder.normalizar(texto)
        linhas.append(f'\n> {texto}\n  cru:     {_resumo(ifood, texto)}')
        if norm and norm['texto'] != texto:
            linhas.append(f'  arrumado "{norm["texto"]}": {_resumo(ifood, norm["texto"])}')
        else:
            linhas.append('  arrumado: (gratuito não achou, vai o cru)')
        time.sleep(3)  # Nominatim pede 1 req/s e o Akamai do iFood barra rajada (403)
    return linhas


@app.function(image=img, secrets=[modal.Secret.from_name('hackathon-ifood')], timeout=120)
def cru(texto: str):
    import json
    from src.bot.contexto import chamador_real
    estado = modal.Dict.from_name('hackfood-estado')
    wa = next(k for k in estado.keys() if str(k).startswith('tok:')).removeprefix('tok:')
    return json.dumps(chamador_real(estado, wa)('createAddress', address=texto), ensure_ascii=False, indent=1)[:4000]


@app.local_entrypoint()
def main(cru_de: str = ''):
    print(cru.remote(cru_de) if cru_de else '\n'.join(bateria.remote()))
