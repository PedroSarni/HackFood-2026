---
slug: bot-best-store
owner: Fabio
status: active
started: 2026-10-17 23:40
---

## O que

Lista com vários itens (mercado ou restaurante) e kit em grupo escolhem a loja que tem TUDO o que a pessoa
pediu e, entre essas, a de melhor custo-benefício (itens + entrega), e não mais a loja do primeiro item
escolhido. Dá pra trocar de loja no meio: o que já está no carrinho vai junto, pelo equivalente da loja nova.
Inclui deixar o mock coerente (mercado grande com quase tudo, pizzaria com Coca), só acrescentando.
NÃO cobre: dividir um pedido em duas lojas (o iFood fecha um pedido por loja), nem a vitrine de boas-vindas.

## Arquivos que vou tocar

- `src/bot/melhor_loja.py` (novo), `src/bot/fluxo.py` (iniciar_compra, buscar, rodapé dos cards, troca de
  loja), `src/bot/grupo.py` (só a escolha da loja do kit), `src/bot/textos.py`, `src/bot/interpretar.py`
  (ação trocar_loja), `src/shared/mcp_fake.py` (só acrescenta)
- `tests/test_melhor_loja.py` (novo), `tests/test_fluxo.py`, `docs/como-funciona.md`

## Peças compartilháveis que vou criar

- nenhuma em `src/shared/`: a escolha da loja é regra do bot (`src/bot/melhor_loja.py`)

## Onde está (preencher ao terminar)

-
