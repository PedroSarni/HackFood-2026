"""Interruptor do modo demo (iFood falso), sem deploy: vale na próxima mensagem.

Plano B da apresentação: se o firewall do iFood barrar a gente, liga o mock e a demo segue com
o mesmo fluxo e as mesmas telas (dados falsos). Desliga quando o iFood voltar.

    .venv/Scripts/python.exe -m modal run scripts/modo.py --mock on
    .venv/Scripts/python.exe -m modal run scripts/modo.py --mock off
    .venv/Scripts/python.exe -m modal run scripts/modo.py --rapido on   (recorrência vence em 1 min)
    .venv/Scripts/python.exe -m modal run scripts/modo.py --fechadas on (busca mostra loja fechada, pra testar de madrugada)
    .venv/Scripts/python.exe -m modal run scripts/modo.py --palco on    (iFood caiu? vai sozinho pro mock: src/bot/contexto.py)
    .venv/Scripts/python.exe -m modal run scripts/modo.py --zerar    (zera o disjuntor do 403 do iFood)
    .venv/Scripts/python.exe -m modal run scripts/modo.py            (só mostra como está)
"""
import time

import modal

app = modal.App('modo-tmp')


@app.local_entrypoint()
def main(mock: str = '', rapido: str = '', fechadas: str = '', palco: str = '', zerar: bool = False):
    estado = modal.Dict.from_name('hackfood-estado')
    if mock in ('on', 'off'):
        estado['cfg:mock'] = mock == 'on'
        if mock == 'off':
            estado.pop('cfg:mock_motivo', None)
    if palco in ('on', 'off'):
        estado['cfg:reserva_auto'] = palco == 'on'
    if rapido in ('on', 'off'):
        estado['cfg:demo_rapido'] = rapido == 'on'
    if zerar:  # o container novo já nasce com o freio local zerado; o armazém é o que os outros leem
        estado['ifood_bloqueado_ate'] = 0
    if fechadas in ('on', 'off'):
        estado['cfg:fechadas'] = fechadas == 'on'
    print(f'lojas fechadas na busca: {"APARECEM" if estado.get("cfg:fechadas") else "escondidas"}')
    barrado = float(estado.get('ifood_bloqueado_ate') or 0) - time.time()
    motivo = estado.get('cfg:mock_motivo') or {}
    print(f'modo demo (iFood falso): {"LIGADO" if estado.get("cfg:mock") else "desligado"}'
          + (' (entrou sozinho: o iFood caiu)' if estado.get('cfg:mock') and motivo.get('auto') else ''))
    print(f'modo palco (iFood caiu -> mock sozinho): {"ARMADO" if estado.get("cfg:reserva_auto") is True else "desligado"}')
    print(f'tempo rápido (recorrência em 1 min): {"LIGADO" if estado.get("cfg:demo_rapido") else "desligado"}')
    print('último container barrado pelo iFood: ' + ('há %ds (só informativo: cada container tem o seu IP e o seu freio, '
          'e o barrado se aposenta sozinho)' % (300 - barrado) if barrado > 0 else 'nenhum nos últimos 5 min'))
