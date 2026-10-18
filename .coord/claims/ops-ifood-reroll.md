---
slug: ops-ifood-reroll
owner: Fabio Araujo
status: done
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

- `src/shared/ifood_mcp.py` — `bloqueio_akamai(e)`, `_aposentar_container()` (flag `APOSENTAR_SE_BARRADO`), freio só local
- `src/bot/contexto.py` — `chamador_real(..., ponte=)`: 403 do Akamai -> a mesma chamada pela ponte; `contexto_producao` liga a flag e monta a ponte
- `src/app.py` — função Modal `ponte_mcp(token, ferramenta, args)` (erro volta por valor)
- `scripts/modo.py` — o carimbo `ifood_bloqueado_ate` virou só informativo
- medido em 18/10: 8 containers em 5 IPs (1 barrado); aposentadoria vale em poucos segundos (sonda no Modal)
