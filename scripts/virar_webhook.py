"""Aponta o webhook SÓ do número do bot pra uma URL (override_callback_uri) e mostra a config.

    padrão (bot do hackathon):  .venv/Scripts/python.exe -m modal run scripts/virar_webhook.py
    desfazer:                   .venv/Scripts/python.exe -m modal run scripts/virar_webhook.py --url <URL antiga>

A Meta faz um GET de verificação na URL antes de aceitar (o endpoint precisa estar no ar).
"""
import json
import os

import modal

app = modal.App('virar-webhook-tmp')
img = modal.Image.debian_slim(python_version='3.12').pip_install('httpx==0.28.1').add_local_python_source('src')
NOVO = 'https://fabio-araujo-silva--hackfood-bot.us-east.modal.run/whatsapp'


@app.function(image=img, secrets=[modal.Secret.from_name('hackathon-whatsapp')], timeout=120)
def virar(url: str):
    from src.shared.whatsapp import WhatsApp
    w = WhatsApp()
    r = w.apontar_webhook(url, os.environ['WHATSAPP_VERIFY_TOKEN'])
    conf = w.graph('GET', w.phone_id, params={'fields': 'webhook_configuration,display_phone_number'})
    return r, conf


@app.local_entrypoint()
def main(url: str = NOVO):
    r, conf = virar.remote(url)
    print('resposta:', json.dumps(r))
    print('config agora:', json.dumps(conf, ensure_ascii=False))
