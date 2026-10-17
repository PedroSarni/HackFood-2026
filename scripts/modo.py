"""Interruptor do modo demo (iFood falso), sem deploy: vale na próxima mensagem.

Plano B da apresentação: se o firewall do iFood barrar a gente, liga o mock e a demo segue com
o mesmo fluxo e as mesmas telas (dados falsos). Desliga quando o iFood voltar.

    .venv/Scripts/python.exe -m modal run scripts/modo.py --mock on
    .venv/Scripts/python.exe -m modal run scripts/modo.py --mock off
    .venv/Scripts/python.exe -m modal run scripts/modo.py            (só mostra como está)
"""
import time

import modal

app = modal.App('modo-tmp')


@app.local_entrypoint()
def main(mock: str = ''):
    estado = modal.Dict.from_name('hackfood-estado')
    if mock in ('on', 'off'):
        estado['cfg:mock'] = mock == 'on'
    barrado = float(estado.get('ifood_bloqueado_ate') or 0) - time.time()
    print(f'modo demo (iFood falso): {"LIGADO" if estado.get("cfg:mock") else "desligado"}')
    print(f'disjuntor do iFood: {"pausado por mais %ds" % barrado if barrado > 0 else "liberado"}')
