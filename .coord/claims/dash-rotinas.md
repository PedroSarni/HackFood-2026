---
slug: dash-rotinas
owner: araujo.fabio@usp.br
status: done
started: 2026-10-18 05:05
---

## O que

Seção "Rotinas automáticas" na tela Agentes do dash: o que o bot faz sozinho, sem a pessoa pedir (cutucada aos
3 min, carrinho esquecido aos 5, lembrete de recompra a cada 15 min, avisos do rastreio), com cada disparo, o
resultado e a última varredura do cron. A demo passa a disparar essas rotinas.
NÃO cobre: mudar as regras das rotinas (tempos, textos) nem o fluxo da conversa (`src/bot/fluxo.py`).

## Arquivos que vou tocar

- `src/shared/painel.py`: reconhecer a rotina de cada mensagem, resumo das rotinas, anotar a varredura
- `src/bot/recorrencia.py`: `agenda()` (só lê os lembretes, pra varredura contar)
- `src/app.py`: `pessoa_calada` marca o abandono com origem própria; `lembretes()` anota a varredura
- `src/painel/servidor.py`: `GET /api/rotinas`, campo `rotina` no `/api/ao-vivo`
- `src/painel/simulador.py`: a demo cutuca, esquece carrinho e manda lembrete
- `Frontend/Rascunho_Dash/rotinas.jsx` (novo), `equipe.jsx`, `styles.css`
- `tests/test_rotinas.py`, `Frontend/Rascunho_Dash/tests/rotinas.test.jsx`
- `docs/como-funciona.md`

## Peças compartilháveis que vou criar

- `src/shared/painel.py` — `rotina_da_saida(ev) -> str | None` — pronto
- `src/shared/painel.py` — `resumo_rotinas(eventos, rotulos, de=None, conversa=None) -> dict` — pronto
- `src/painel/servidor.py` — `GET /api/rotinas?fonte=&dias=` — pronto

## Onde está

- `src/shared/painel.py`: `rotina_da_saida()`, `resumo_rotinas()`, `anotar_varredura()`
- `src/bot/recorrencia.py`: `agenda()`; `src/app.py`: origem `abandono` e a passada do cron (`LEMBRETES_MIN`)
- `src/painel/servidor.py`: `GET /api/rotinas`, `rotina` no `/api/ao-vivo`, cache da demo com os clientes
- `src/painel/simulador.py`: `calar()`, `varrer()`, `guardar_clientes()`, `restaurar_clientes()`
- `Frontend/Rascunho_Dash/rotinas.jsx` + `rotinas.css`: `<RoutinesPanel />`; o palco usa `ROUTINES`
- `src/agentes/`: campo `onde` na ficha (a Sofia é do painel e saiu do palco)
- Testes: `tests/test_rotinas.py`, `Frontend/Rascunho_Dash/tests/rotinas.test.jsx`

