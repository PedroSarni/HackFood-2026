---
slug: dash-live-data
owner: Fabio
status: done
started: 2026-10-17 20:45
---

## O que

Dá vida ao rascunho do dash do Pedro (`Frontend/Rascunho_Dash`): o bot passa a anotar um diário
de eventos (mensagem que entra, mensagem que sai, chamada ao MCP) num modal.Dict próprio, e um
servidor LOCAL lê esse diário e empurra as conversas pro dash em tempo real (SSE). Tem também um
simulador local que roda o Bot de verdade com os fakes, pra ver o dash mexer sem WhatsApp.
NÃO cobre: hospedar o dash na internet, login de admin, mexer na lógica do fluxo da conversa.

## Arquivos que vou tocar

- `src/shared/painel.py` (novo), `src/painel/` (novo: servidor local + simulador)
- `src/bot/contexto.py` (embrulhar wpp e chamador com o diário), `src/app.py` (anotar entrada e lembretes)
- `tests/test_painel.py` (novo)
- `Frontend/Rascunho_Dash/` (data.js, app.jsx, live.js, styles.css, vite.config.js, README)

## Peças compartilháveis que vou criar

- `src/shared/painel.py` — `Diario(dic)`, `EspiaoWhatsApp(wpp, diario)`, `espiar_mcp(chamar, diario, wa_id)`, `montar_sessoes(eventos, agora)` — pronto

## Onde está (preencher ao terminar)

- `src/shared/painel.py` — `Diario`, `diario_producao()`, `EspiaoWhatsApp`, `espiar_mcp`, `anotar_entrada`, `montar_sessoes(eventos, agora)`
- `src/bot/contexto.py` — `contexto_producao(..., origem=None)` embrulha wpp/MCP e expõe `ctx.diario`; `src/app.py` anota entrada e lembretes
- `src/painel/servidor.py` — servidor local: `GET /api/sessoes`, `GET /api/stream` (SSE), `--simular`
- `src/painel/simulador.py` — `MundoAnotado`, `jornada()`, `preencher_historico()`, `rodar_ao_vivo()`
- `Frontend/Rascunho_Dash/live.js` — `useLiveSessions()`; `app.jsx` com seletor Ao vivo / Base de exemplo
- `tests/test_painel.py`
