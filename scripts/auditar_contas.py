"""Auditoria de vazamento entre usuários: cada WhatsApp logado aponta pra qual conta iFood?

Imprime só hashes curtos (nada de e-mail, telefone, endereço ou token):
    wa (4 últimos dígitos) | conta iFood (hash do e-mail) | endereços salvos (hash de cada) | endereço no estado do bot (hash)

    .venv/Scripts/python.exe -m modal run scripts/auditar_contas.py
"""
import modal

app = modal.App('auditar-contas-tmp')
img = modal.Image.debian_slim(python_version='3.12').pip_install('httpx==0.28.1').add_local_python_source('src')


def _h(x):
    import hashlib
    return hashlib.sha256(str(x or '').encode()).hexdigest()[:8] if x else '-'


@app.function(image=img, secrets=[modal.Secret.from_name('hackathon-ifood')], timeout=300)
def auditar():
    import time
    from src.bot.contexto import chamador_real
    from src.bot.ifood import Ifood

    estado = modal.Dict.from_name('hackfood-estado')
    chaves = [str(k) for k in estado.keys()]
    linhas = [f'chaves: {len(chaves)} | tok: {sum(k.startswith("tok:") for k in chaves)} '
              f'| u: {sum(k.startswith("u:") for k in chaves)}']
    was = sorted({k.split(':', 1)[1] for k in chaves if k.startswith(('tok:', 'u:'))})
    for wa in was:
        u = estado.get(f'u:{wa}') or {}
        end_bot = _h((u.get('endereco') or {}).get('texto'))
        conta, ends = 'sem login', '-'
        if estado.get(f'tok:{wa}'):
            try:
                ifood = Ifood(chamador_real(estado, wa))
                conta = _h(ifood.usuario().get('email'))
                ends = ','.join(_h(e.get('texto')) for e in ifood.enderecos()) or 'nenhum'
            except Exception as e:  # noqa: BLE001
                conta = f'erro {type(e).__name__}'
            time.sleep(2)
        linhas.append(f'wa ...{wa[-4:]} | conta {conta} | ends iFood [{ends}] | end no bot {end_bot}')
    return linhas


@app.local_entrypoint()
def main():
    print('\n'.join(auditar.remote()))
