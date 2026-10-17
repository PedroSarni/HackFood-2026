---
slug: bot-ifood-agent
owner: Fabio
status: active
started: 2026-10-17 16:00
---

## O que

Bot de WhatsApp que faz compras no iFood pelo MCP, em Python no Modal (`src/`). Ouve o usuário
(texto, áudio, foto, várias mensagens seguidas), entende com Gemini e o código conduz
login/cadastro, busca, carrinho, pagamento, confirmação, rastreio e recorrência (lembrete com 1
toque). Feito pra quem não sabe usar o celular: botões sempre, 3 cards com foto + "Mais opções"
(reaproveita a lista já buscada a partir do índice 3, sem buscar de novo).
Inclui o mock do MCP (o "mcp-mock" citado em docs/estado.md): mesmas tools, dados falsos, pra
ninguém ficar parado esperando credencial.
NÃO cobre: lado do restaurante, cancelamento/reembolso (a API não tem), painel web, entregáveis.

## Arquivos que vou tocar

- `src/` (app Modal, bot, web), `tests/`
- `docs/whatsapp.md`, `.env.example`, `requirements.txt`

## Peças compartilháveis que vou criar

- `src/shared/whatsapp.py` — `WhatsApp(...).texto/botoes/lista/link/imagem/digitando/baixar_midia` — pronto
- `src/shared/ifood_mcp.py` — `ClienteMCP(token).chamar(tool, **args)` + OAuth (`pkce`, `url_login`, `trocar_codigo`, `renovar`) — pronto
- `src/shared/mcp_fake.py` — `McpFake().chamar(tool, **args)`: MCP falso com as 24 tools — stub
- `src/shared/buffer.py` — `Caixa`: junta rajada de mensagens por pessoa — pronto
- `src/shared/geocoder.py` — `normalizar(texto)`: texto com CEP -> endereço canônico pro iFood (BrasilAPI/ViaCEP, grátis) — pronto
- `src/shared/llm.py` — `gerar_json(sistema, partes, esquema)`: Gemini com texto/áudio/foto — pronto

## Onde está (preencher ao terminar)

-
