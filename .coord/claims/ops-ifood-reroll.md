---
slug: ops-ifood-reroll
owner: Fabio Araujo
status: active
started: 2026-10-18 07:40
---

## O que

O Akamai do iFood bloqueia por IP de saída, e o Modal tem vários (medido em 18/10: 8 containers em 5 IPs, 1 bloqueado).
Hoje o disjuntor é compartilhado: um container com IP bloqueado faz todos os outros (com IP bom) pararem por 5 min.
Agora: disjuntor só local; o container que vê o 403 se aposenta (para de pegar mensagens, o Modal abre outro em
outro IP) e a chamada que falhou é refeita por uma ponte (função separada, cai em outra máquina) antes de desistir.
Não cobre: proxy/IP fixo, mudar app/label/região.

## Arquivos que vou tocar

- src/shared/ifood_mcp.py, src/bot/contexto.py, src/app.py, tests/test_pecas.py, tests/test_reserva.py

## Peças compartilháveis que vou criar

- `src/app.py` — função Modal `ponte_mcp(token, ferramenta, args)` — pronto

## Onde está (preencher ao terminar)

- 
