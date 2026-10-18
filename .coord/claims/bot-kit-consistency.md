---
slug: bot-kit-consistency
owner: Fabio
status: done
started: 2026-10-18 08:10
---

## O que

O Beto (kit pra grupo) parou de chapar: o principal do kit tem que ser o prato de verdade ("Omelete de Pizza"
não é pizza; carvão não é churrasco), cada comida tem uma receita com o que não pode faltar (churrasco = carne
+ carvão + bebida) e quantidades com limite, e os ajustes do kit ("sem refri", "troca coca por guaraná", "mais
batata", "mais barato", "agora somos 6") são lidos e aplicados pelo CÓDIGO em cima do kit da tela; o modelo
só entra no que o código não entende ("2 são vegetarianos"), e mesmo aí só pode mexer no que foi citado.
De quebra, o kit ficou mais rápido com o iFood real: getItem e buscas da loja em paralelo, um filtro só.
NÃO cobre: pagamento dividido, kit com mais de uma loja.

## Arquivos que toquei

- `src/bot/grupo.py`, `src/bot/kit_ajuste.py` (novo), `src/bot/fluxo.py` (2 linhas: só o ajuste novo vai pro kit),
  `src/agentes/grupo.py` (ficha), `src/shared/mcp_fake.py` (só acrescenta: padaria com omelete, churrasco no mercado),
  `scripts/validar_foto_grupo.py` (compor devolve 3 valores)
- `tests/test_foto_grupo.py`, `tests/test_kit_ajuste.py` (novo), `tests/fakes.py` (o fake entende mais ajustes),
  `docs/como-funciona.md` §9.2, `docs/prompts/fabio.md`

## Peças compartilháveis que criei

- nenhuma em `src/shared/`: a lógica é do bot

## Onde está

- `src/bot/grupo.py` — `RECEITAS` (por comida: o que é o prato, `cabeca`/`nunca` do que não é, quanto por pessoa,
  o que acompanha, `essenciais`), `receita_de`, `e_o_prato`, `quantas_principais`, `quantidade_de`, `_validar`
  (o crivo do que o modelo devolve), `requantificar` ("agora somos 6"), `baratear` (a escada do "mais barato"),
  `_Loja` (buscar/reabrir/baratear pro ajuste), `montar` (ajuste em cima do kit da tela; `ajustes`/`restricoes`
  guardados no kit e valendo no "Outra loja"), `_em_paralelo` (getItem e buscas juntos), `compor` → (escolha,
  explicação, falta_o_prato)
- `src/bot/kit_ajuste.py` — `ler(ajuste, cands, kit, tema)` → operações (tira/troca/mais/menos/qtd/poe/barato/
  pessoas/nada/livre), `aplicar(ops, kit, cands, pessoas, tema, loja)`, `explicar(frases)`, `conferir` (o modelo
  só mexe no que citou)
- `tests/test_kit_ajuste.py` (19 testes: receita, omelete, churrasco, cada ajuste, a escada do barato, outra loja)
