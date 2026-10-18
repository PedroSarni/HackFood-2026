---
slug: bot-photo-group-kit
owner: Fabio
status: done
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

- `src/bot/foto.py` — `ler(llm, estado, fotos, textos)`: prompt/esquema da foto (comida | lista | produto | outro)
- `src/bot/grupo.py` — `montar(...)` (kit numa loja), `compor` (Gemini decide, `kit_padrao` de reserva),
  `opcoes_automaticas`, `por_pessoa`, `pessoas_em` / `tema_em` / `bebidas_em` (regras sem IA)
- `src/bot/fluxo.py` — `receber_fotos`, `foto_sim`, `buscar_parecidos`; `grupo`, `grupo_pessoas`, `_montar_kit`,
  `kit_ok`, `responder_kit`, `_dividir_pedido`, `_pessoas`; fases `foto`, `kit`, `grupo_pessoas`, `grupo_tema`;
  botões `foto:sim|nao:<id>`, `kit:ok|outra|nao:<id>`, `grupo_n:<n>`; `buscar` dividido em `_coletar` + `_mostrar_lista`
- `src/bot/interpretar.py` — `acao=grupo` (numero = pessoas, texto = restrição); `src/bot/textos.py` — textos da foto e do kit,
  `dividido()` no total, no resumo e no "Pedido feito"
- `src/shared/mcp_fake.py` — Burger House (`l2`) e refri de 2 litros na lanchonete; `src/bot/ifood.py` — `taxa_entrega` na oferta
- `tests/test_foto_grupo.py`; `scripts/validar_foto_grupo.py` (prompts contra o Gemini real); `docs/como-funciona.md` §9.1 e §9.2
