---
slug: bot-kit-consistency
owner: Fabio
status: active
started: 2026-10-18 08:10
---

## O que

O Beto (kit pra grupo) parou de chapar: o principal do kit tem que ser o prato de verdade ("Omelete de Pizza"
não é pizza; carvão não é churrasco), cada comida tem uma receita com o que não pode faltar (churrasco = carne
+ carvão + bebida) e quantidades com limite, e os ajustes do kit ("sem refri", "troca coca por guaraná", "mais
batata", "mais barato", "agora somos 6") são lidos e aplicados pelo CÓDIGO em cima do kit da tela; o modelo
só entra no que o código não entende ("2 são vegetarianos"), e mesmo aí só pode mexer no que foi citado.
NÃO cobre: pagamento dividido, kit com mais de uma loja.

## Arquivos que vou tocar

- `src/bot/grupo.py` (receitas, validação do principal, requantificar, montar), `src/bot/kit_ajuste.py` (novo),
  `src/bot/fluxo.py` (só passa o ajuste novo), `src/agentes/grupo.py` (ficha), `src/shared/mcp_fake.py` (só acrescenta)
- `tests/test_foto_grupo.py`, `tests/test_kit_ajuste.py` (novo), `docs/como-funciona.md` §9.2, `docs/prompts/fabio.md`

## Peças compartilháveis que vou criar

- nenhuma em `src/shared/`: a lógica é do bot

## Onde está (preencher ao terminar)

- (em andamento)
