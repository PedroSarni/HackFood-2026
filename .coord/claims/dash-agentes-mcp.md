---
slug: dash-agentes-mcp
owner: Davi de Alcantara Lima
status: active
started: 2026-10-18 01:00
---

## O que

Fase 1A: visão "MCP" no dash (uso por tool, erros, latência, conversas, tools da doc nunca chamadas,
sequência por conversa), agregada no servidor local a partir dos eventos `mcp` que o diário já grava.
Fase 1B: rastro dos agentes de IA: embrulho `espiar_ia` no mesmo estilo do `espiar_mcp`, ligado em
`contexto_producao`, gravando eventos tipo `ia` (agente, modelo, ms, ok/erro, resumo mínimo mascarado),
e aba "Agentes" no dash (linha do tempo por conversa, uso %, latência, erros).
NÃO cobre: liga/desliga de agentes (fase 2, só com o Davi pedindo), criar agentes pelo dash, mudar o
fluxo da conversa, compra, CPF, confirmação ou login, e o que o `espiar_mcp` grava.

## Arquivos que vou tocar

- `src/shared/painel.py` (espiões de IA + agregações; `montar_sessoes` só ganha parâmetro opcional)
- `src/bot/contexto.py` (ligar o espião de IA em `contexto_producao`)
- `src/painel/servidor.py` (rotas `/api/mcp` e `/api/agentes`), `src/painel/simulador.py` (espião de IA na demo)
- `tests/test_painel.py` (novos testes)
- `Frontend/Rascunho_Dash/` (`app.jsx`, `agentes.jsx` novo, `telemetria.js` novo, `styles.css`, `tests/agentes.test.jsx` novo)
- `docs/como-funciona.md` (seção curta do painel), `docs/prompts/davi.md`

## Peças compartilháveis que vou criar

- `src/shared/painel.py` — `espiar_ia(gerar, diario, wa_id)`, `espiar_servico(fn, diario, wa_id, agente, modelo)`, `resumo_mcp(...)`, `resumo_agentes(...)` — em implementação

## Onde está (preencher ao terminar)

- 
