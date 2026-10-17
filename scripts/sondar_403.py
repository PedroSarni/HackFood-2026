"""Quem o Akamai do iFood está barrando (403 Access Denied)? Uma chamada leve por caso, sem imprimir token.

    .venv/Scripts/python.exe -m modal run scripts/sondar_403.py
"""
import modal

app = modal.App('sondar-403-tmp')
img = modal.Image.debian_slim(python_version='3.12').pip_install('httpx==0.28.1').add_local_python_source('src')


@app.function(image=img, secrets=[modal.Secret.from_name('hackathon-ifood')], timeout=120)
def sondar():
    import time
    import httpx
    from src.shared import ifood_mcp

    corpo = {'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
             'params': {'protocolVersion': ifood_mcp.PROTOCOLO, 'capabilities': {},
                        'clientInfo': {'name': 'hackfood-bot', 'version': '1.0'}}}
    cab = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    saida = [f'ip de saída: {httpx.get("https://api.ipify.org", timeout=10).text}']
    r = httpx.post(ifood_mcp.GATEWAY, json=corpo, headers=cab, timeout=15)
    saida.append(f'sem token: {r.status_code} {"AKAMAI" if "Access Denied" in r.text else ""}')
    estado = modal.Dict.from_name('hackfood-estado')
    for k in [str(k) for k in estado.keys() if str(k).startswith('tok:')]:
        tok = estado.get(k) or {}
        r = httpx.post(ifood_mcp.GATEWAY, json=corpo, timeout=15,
                       headers={**cab, 'Authorization': f'Bearer {tok.get("access_token", "")}'})
        venceu = 'vencido' if ifood_mcp.precisa_renovar(tok) else 'válido'
        saida.append(f'...{k[-4:]} (token {venceu}): {r.status_code} {"AKAMAI" if "Access Denied" in r.text else ""}')
        time.sleep(2)
    return saida


@app.local_entrypoint()
def main():
    print('\n'.join(sondar.remote()))
