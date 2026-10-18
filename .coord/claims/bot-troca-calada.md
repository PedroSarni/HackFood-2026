---
slug: bot-troca-calada
owner: araujo.fabio@usp.br
status: done
started: 2026-10-18 08:15
---

## O que

A troca do iFood real pro catálogo de reserva (e a volta) sem a pessoa perceber: em vez do "precisei recomeçar seu
pedido", o carrinho, o produto da vez e o card de antes vão junto pro outro lado pelo nome. O que não existe lá sai
como produto que acabou. NÃO cobre: endereço cadastrado só de um lado, pagamento já escolhido (é escolhido de novo).

## Arquivos que vou tocar

- `src/bot/fluxo.py` (começo da rodada, `_protegido`, `escolher_oferta`, `_mudar_de_loja` só a anotação das linhas)
- `src/bot/contexto.py` (`com_reserva`), `src/bot/ifood.py` (`IfoodTrocou`), `src/bot/textos.py`
- `tests/test_achados_qa.py`, `tests/test_reserva.py`, `tests/test_fluxo.py`, `docs/como-funciona.md`,
  `docs/qa-18-10.md`, `docs/prompts/fabio.md`

## Peças compartilháveis que vou criar

- nenhuma em `src/shared/`: a troca é do fluxo do bot

## Onde está (preencher ao terminar)

- `src/bot/fluxo.py` — `_trocar_de_ifood()`, `_transplantar()`, `_traduzir_escolha()`, `_mesmo_produto()`,
  `_do_outro_ifood()`; `_protegido()` refaz a ação depois da troca; `escolher_oferta()` traduz o card de antes
- `src/bot/contexto.py` — `presa_ao_pedido()`; `src/bot/ifood.py` — `IfoodTrocou`
- `src/bot/textos.py` — `PEDIDO_RECOMECADO` (novo texto), `PEDIDO_ATUALIZADO`, `indisponiveis()`, `no_lugar()`
- `docs/como-funciona.md` §modos do iFood, "Troca com pedido montado"
