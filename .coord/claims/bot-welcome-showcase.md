---
slug: bot-welcome-showcase
owner: Fabio
status: done
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

- `src/bot/vitrine.py` — agentes `agente_gosto`, `agente_hora`, `agente_precinho`, `agente_descontos`; `montar(api, endereco, hist, recentes, agora, foto_padrao)`
- `src/bot/fluxo.py` — `Bot._mostrar_vitrine()` (no `menu()` sem prefixo e depois do login), botão `vit:<n>` -> `escolher_vitrine`; busca com `preco_max`/`so_promo`
- `src/bot/ifood.py` — `Ifood.buscar(..., preco_max=)` (refinement maxItemPrice)
- `src/bot/textos.py` — `boas_vindas` curtinha, `VITRINE_TOPO`, `card_vitrine`
- `tests/test_vitrine.py`
