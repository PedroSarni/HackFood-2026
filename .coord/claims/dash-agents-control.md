---
slug: dash-agents-control
owner: araujo.fabio@usp.br
status: done
started: 2026-10-18 01:45
---

## O que

Gestão e transparência dos agentes (fase 2 do `dash-agentes-mcp`, que o Davi passou inteira pro Fabio).
No back, a ficha de cada agente fica num lugar só: persona, papel, system prompt, fila de modelos, keys
(nome + 4 finais) e plano B. Tem também o liga/desliga sem deploy (`cfg:agentes_off` no armazém), em que
o agente desligado cai no plano B que já existe. No dash, "Agentes" vira a 1ª tela: equipe com animação ao
vivo de quem fala com quem, desempenho por agente e ficha aberta um a um com filtros. A navegação fica
Agentes → Uso do MCP → Dinheiro e é enxugada. Telas duplicadas saem do menu (Inteligência artificial,
Follow-ups e Financeiro, que se junta ao Dinheiro).
NÃO cobre: editar system prompt pelo dash, trocar modelo pelo dash, criar agente novo.

## Arquivos que vou tocar

- `src/agentes/` (novo: `__init__.py` com o roteador e o interruptor, um arquivo por agente)
- `src/shared/painel.py` (usa a ficha; o espião marca "desligado")
- `src/bot/contexto.py` (liga/desliga em `contexto_producao` e publica a ficha do que está no ar)
- `src/painel/servidor.py`, `src/painel/simulador.py`
- `tests/test_agentes.py` (novo), `tests/test_painel.py`
- `Frontend/Rascunho_Dash/` (`agentes.jsx`, `equipe.jsx` novo, `telemetria.js`, `app.jsx`, `styles.css`, testes)
- `docs/como-funciona.md`, `docs/prompts/fabio.md`

## Peças compartilháveis que vou criar

- `src/agentes/__init__.py` — `TODOS`, `POR_ID`, `do_sistema()`, `roteador()`, `fila()`, `config()`, `definir()`,
  `chave_mascarada()`, `foto_do_ar()`, `publicar_ar()`, `fichas()` — pronto

## Onde está (preencher ao terminar)

- `src/agentes/__init__.py` — `Agente`, `TODOS`, `POR_ID`, `do_sistema()`, `roteador()` (liga/desliga + fila do agente),
  `fila()`, `config()`, `definir()`, `so_se_ligado()`, `chave_mascarada()`, `foto_do_ar()`, `publicar_ar()`, `fichas()`
- `src/agentes/{entendimento,foto,relevancia,grupo,tutor,voz,ouvido}.py` — a `FICHA` de cada agente (Lia, Íris, Duda,
  Beto, Tito, Vina, Otto): persona, `modelos` só dele, keys, plano B, onde mexer
- `src/bot/contexto.py` — `contexto_producao` lê `cfg:agentes`, publica `cfg:agentes_ar` e põe o roteador por fora do espião
- `src/shared/painel.py` — `agente_do_sistema` delega pra ficha; desligado vira `pulos` (não erro) em `resumo_agentes`
- `src/painel/servidor.py` — `GET /api/equipe`, `POST /api/equipe/<agente>`, `GET /api/ao-vivo`; `Painel.equipe/definir/ao_vivo`
- `src/painel/simulador.py` — a demo respeita o interruptor
- `Frontend/Rascunho_Dash/equipe.jsx` — `<TeamPage />` (palco ao vivo, cards, filtros, `AgentSheet`); `telemetria.js` —
  `useTeam()`, `useLiveSteps()`; `app.jsx` — menu Agentes → Uso do MCP → Dinheiro → Conversas (+ Mais análises), `<Money />`
- `docs/como-funciona.md` §13.2 — como melhorar um agente sem mexer nos outros
- Deploy: 2026-10-18 ~02h30 (2af1cf6)
