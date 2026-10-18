---
slug: dash-rotinas
owner: araujo.fabio@usp.br
status: active
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

- `src/shared/painel.py` — `rotina_da_saida(ev) -> str | None` — stub
- `src/shared/painel.py` — `resumo_rotinas(eventos, rotulos, de=None, conversa=None) -> dict` — stub
- `src/painel/servidor.py` — `GET /api/rotinas?fonte=&dias=` — stub
