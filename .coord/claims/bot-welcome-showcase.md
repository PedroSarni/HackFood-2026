---
slug: bot-welcome-showcase
owner: Fabio
status: active
started: 2026-10-18 00:55
---

## O que

Primeira mensagem simplesinha + vitrine: um carrossel de categorias de recomendação ("Tô afim de
Lanches", "Até R$ 45", "Descontos pra você", "Pedir de novo"...) montado por agentes internos que
olham o gosto da pessoa (histórico nosso, pedidos recentes do iFood, hora do dia, promoções). Tocar
num card busca aquela categoria. NÃO cobre: mudar o fluxo de busca/carrinho, nem o menu de botões.

## Arquivos que vou tocar

- `src/bot/vitrine.py` (novo), `src/bot/fluxo.py` (menu de boas-vindas e botão `vit:`), `src/bot/textos.py`,
  `src/bot/ifood.py` (busca com teto de preço)
- `tests/test_vitrine.py` (novo)

## Peças compartilháveis que vou criar

- nenhuma em `src/shared/`: os agentes são do bot (`src/bot/vitrine.py`)

## Onde está (preencher ao terminar)

-
