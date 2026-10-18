---
slug: dash-agentes-mcp
owner: Davi de Alcantara Lima
status: done
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

- `src/shared/painel.py` — `espiar_ia(gerar, diario, wa_id, primeiro=None)`, `espiar_servico(fn, diario, wa_id, agente, modelo)`, `resumo_mcp(eventos, rotulos, de, conversa)`, `resumo_agentes(...)`, `indice_conversas(...)` — pronto

## Onde está (preencher ao terminar)

Fase 1 (1A + 1B) pronta. Fase 2 (liga/desliga) cancelada: o claim dash-agents-control (Fabio) já cobre
interruptor, escolha de modelo e crachá.

- `src/shared/painel.py` — `espiar_ia`, `espiar_servico`, `agente_do_sistema`, `AGENTES`, `REGRAS`, `regra_da_saida`,
  `resumo_mcp`, `resumo_agentes`, `indice_conversas`, `tools_da_doc`; `montar_sessoes(..., rotulos=None)`
- `src/bot/contexto.py` — `contexto_producao` liga o espião de IA (Gemini/OpenRouter, Scribe, ElevenLabs); `_primeiro_modelo`
- `src/painel/servidor.py` — `GET /api/mcp`, `GET /api/agentes`, `Painel.consulta()` (cache por recálculo)
- `src/painel/simulador.py` — a demo também espiona a IA de mentira
- `Frontend/Rascunho_Dash/agentes.jsx` — `<McpPage />`, `<AgentsPage />`; `telemetria.js` — `useSummary()`, `summaryUrl()`
- `tests/test_painel.py`, `Frontend/Rascunho_Dash/tests/agentes.test.jsx`
