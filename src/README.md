# src/: bot de WhatsApp que faz pedidos no iFood (EM CONSTRUÇÃO)

> 🚧 **Ainda em construção pelo Fabio (claim `bot-ifood-agent`).** O que está marcado como
> pronto já roda; o resto está sendo escrito e testado agora. Antes de mexer aqui, combine no
> claim pra não duplicar.

Python no [Modal](https://modal.com), reaproveitando o setup do handwrite_bot (número da Meta,
Gemini pago). Tese do time: **a IA entende, o código garante**. O Gemini só transforma
texto/áudio/foto em intenção; quem conduz o pedido e chama o MCP é o código, etapa por etapa.

## Como roda

```
WhatsApp → POST /whatsapp (webhook, responde 200 na hora)
         → fila da pessoa + rodada(wa_id)          src/shared/buffer.py: junta a rajada de mensagens
         → Bot.processar(lote)                     src/bot/fluxo.py: máquina de etapas
             ├─ botão: caminho direto, sem IA
             ├─ texto/áudio/foto: regras rápidas → Gemini (src/bot/interpretar.py)
             └─ Ifood (src/bot/ifood.py) → MCP do iFood (src/shared/ifood_mcp.py) ou mock
         → respostas com botões                    src/shared/whatsapp.py
```

- Deploy: `.venv/Scripts/python.exe -m modal deploy -m src.app`
- Testes: `.venv/Scripts/python.exe -m pytest`
- No ar: `https://fabio-araujo-silva--hackfood-bot.us-east.modal.run` (`/saude`, `/termos`, `/privacidade`)

## Status

| Peça | Arquivo | Status |
|---|---|---|
| Cliente WhatsApp (texto, botões, lista, link, foto, "digitando...") | `shared/whatsapp.py` | ✅ pronto |
| Gemini com JSON garantido + modelo reserva | `shared/llm.py` | ✅ pronto |
| Junta rajada de mensagens (idoso manda 5 mensagens seguidas) | `shared/buffer.py` | ✅ pronto |
| Cliente MCP (JSON-RPC, sessão, 3 formatos de erro) + OAuth PKCE | `shared/ifood_mcp.py` | ✅ pronto, falta testar com credencial real |
| App Modal: webhook, login do iFood, páginas públicas | `app.py`, `web/` | ✅ no ar (webhook ainda não recebe o número) |
| Fluxo da conversa (login, endereço, busca com 3 cards, "Mais opções", opções do item, carrinho, entrega, pagamento, cupom, CPF, resumo, confirmação) | `bot/fluxo.py` | 🚧 escrito, em teste |
| Tradutor MCP ↔ fluxo (formatos da doc do portal) | `bot/ifood.py` | 🚧 escrito, em teste |
| MCP falso pra demo/teste sem credencial | `shared/mcp_fake.py` | 🚧 ajustando pro formato real da doc |
| Rastreio (segue agentHints) e lembretes de recorrência | `bot/rastreio.py`, `bot/recorrencia.py` | 🚧 escrito, em teste |
| Ordem de prioridade dos itens | `bot/ranking.py` | ⏳ esperando a regra do time |

## Decisões que valem saber

- **"Mais opções"** mostra os próximos 3 da MESMA lista já buscada (índice 3 em diante). Só busca
  de novo quando a lista acaba e o iFood diz que tem mais página.
- **Confirmar compra nunca vem da IA**: `submitOrder(userConsent=true)` só depois do toque em
  *Confirmar pedido* (ou "sim" na tela do resumo). Toque duplo não gera dois pedidos.
- **CPF não passa pela IA**: na etapa do CPF o texto é validado no código.
- **Pagamento**: só PIX e vales. Cartão exige `cardTokenId` e o `listPaymentMethods` sempre devolve
  null (não há API de tokenização). Vai pro entregável 06.
