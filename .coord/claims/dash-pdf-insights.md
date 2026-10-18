---
slug: dash-pdf-insights
owner: Pedro Sarni
status: done
started: 2026-10-17 21:51
---

## O que

Reorganizar o PDF com gráficos e indicadores agregados das páginas do dashboard, removendo a tabela individual de conversas. Preservar os mesmos cálculos, período, filtros globais e fonte selecionada na tela.

## Arquivos que vou tocar

- Frontend/Rascunho_Dash/pdf-report.js
- Frontend/Rascunho_Dash/data.js
- Frontend/Rascunho_Dash/app.jsx
- Frontend/Rascunho_Dash/report-download.js
- Frontend/Rascunho_Dash/tests/pdf.test.js
- Frontend/Rascunho_Dash/tests/analytics.test.js
- Frontend/Rascunho_Dash/tests/export.test.jsx
- Frontend/Rascunho_Dash/README.md
- docs/prompts/pedro.md
- .coord/claims/dash-pdf-insights.md

## Peças compartilháveis que vou criar

- Nenhuma nova peça genérica prevista. Reutilizar e, se necessário, estender `metrics`, `groupBy`, `filterSessions` e os formatos existentes em `Frontend/Rascunho_Dash/data.js`, já compartilhados pelo dashboard e pelo PDF.

## Onde está

- Implementação concluída localmente após resposta do Pedro "já pode commitar" à solicitação de autenticar ou autorizar trabalho local. Interpretação comunicada antes das edições; envio sujeito à autenticação no GitHub.
- `Frontend/Rascunho_Dash/data.js` — `metrics` compartilha os indicadores das páginas, distribuição de resultados, IA, clientes, financeiro e a série diária de vendas; `groupBy` mantém os mesmos rankings.
- `Frontend/Rascunho_Dash/pdf-report.js` — `createAnalyticsPdf` gera visão geral, conversão, follow-ups/clientes agregados, cidades, restaurantes e financeiro/IA, sem registros individuais; rankings paginados. `reportContext` recebe a data da exportação.
- `Frontend/Rascunho_Dash/app.jsx` e `report-download.js` — exportam o recorte atual e anterior, filtros, fonte e data no momento do clique; reutilizam os cálculos das telas.
- `Frontend/Rascunho_Dash/tests/` — 24 testes aprovados; build aprovado. Seis páginas verificadas visualmente com 907 sessões da demonstração local, além do recorte vazio real.
