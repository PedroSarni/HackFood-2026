---
slug: bot-photo-group-kit
owner: Fabio
status: active
started: 2026-10-17 22:30
---

## O que

Duas features do bot: (1) foto em qualquer momento (até a 1ª mensagem) vira pedido: foto de comida
pergunta "quer algo parecido?" e busca parecidos; foto de lista de compras ou de produto vira a lista
do pedido. (2) Modo "dividir com os amigos": "lanchar em 5 pessoas hambúrguer" monta um kit numa loja
só (principal + bebida + acompanhamento), o Gemini decide as quantidades, o código calcula preço e
quanto fica pra cada. NÃO cobre: pagamento separado por pessoa (o iFood cobra uma conta só).

## Arquivos que vou tocar

- `src/bot/foto.py` (novo), `src/bot/grupo.py` (novo), `src/bot/fluxo.py`, `src/bot/interpretar.py`,
  `src/bot/textos.py`, `src/bot/ifood.py` (taxa de entrega na oferta), `src/shared/mcp_fake.py` (só acrescenta)
- `tests/test_foto_grupo.py` (novo), `tests/fakes.py`, `docs/como-funciona.md`

## Peças compartilháveis que vou criar

- nenhuma em `src/shared/`: a lógica é do bot (`src/bot/foto.py`, `src/bot/grupo.py`)

## Onde está (preencher ao terminar)

-
