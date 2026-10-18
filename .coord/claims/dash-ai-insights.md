---
slug: dash-ai-insights
owner: araujo.fabio@usp.br
status: done
started: 2026-10-18 03:15
---

## O que

Botão flutuante de IA nas páginas Conversão, Clientes e Mercado do dash. O clique faz uma varredura de arco-íris de
cima a baixo e a borda da tela brilha enquanto a IA pensa. Depois aparecem insights úteis por time do iFood
(Produto, Growth/CRM, Operações...), cada um com evidência, ação, impacto, prazo e métrica.
Quem gera é a nova agente **Analista** (ficha em `src/agentes/analista.py`, mesma fila/interruptor dos outros),
rodando no Modal (as keys só existem lá). O dash manda só números agregados da página, nada de nome de cliente.
NÃO cobre: insights nas outras páginas, agendar/enviar insights pra alguém.

## Arquivos que vou tocar

- `src/painel/analista.py` (novo: prompt, esquema e validação)
- `src/agentes/analista.py` (novo), `src/agentes/__init__.py` (registrar)
- `src/app.py` (função Modal `analisar_pagina`)
- `src/painel/servidor.py` (`POST /api/insights`, com cache)
- `tests/test_analista.py` (novo), `tests/test_agentes.py`
- `Frontend/Rascunho_Dash/` (`insights.jsx` novo, `app.jsx`, `styles.css`, `tests/insights.test.jsx` novo)
- `docs/como-funciona.md`, `docs/prompts/fabio.md`

## Peças compartilháveis que vou criar

- `src/painel/analista.py` — `analisar(pagina, dados, gerar) -> dict` — pronto

## Onde está (preencher ao terminar)

- `src/painel/analista.py` — `SISTEMA`, `ESQUEMA`, `TIMES`, `PAGINAS`, `limpar()`, `analisar()`
- `src/agentes/analista.py` — ficha da Sofia (fila própria: gemini-3.8-flash → 3.5-flash-lite)
- `src/app.py` — função Modal `analisar_pagina(pagina, dados)`
- `src/painel/servidor.py` — `POST /api/insights` (cache 10 min), `chamar_analista()`, `_origem_local()`
- `Frontend/Rascunho_Dash/insights.jsx` — `<InsightsFab />`, `pageSummary()`, `INSIGHT_PAGES`; estilos `.ai-*` em `styles.css`
- Testes: `tests/test_analista.py`, `Frontend/Rascunho_Dash/tests/insights.test.jsx`
- Deploy: 2026-10-18 ~03h40 (9626e97)

