# WhatsApp: contexto da base do projeto

O produto deste hackathon **é um bot de WhatsApp**. Toda feature passa por aqui: a pessoa manda mensagem
no número, o nosso backend recebe pelo webhook, decide e responde pela Graph API da Meta.

A conexão (número, token, app da Meta) foi **emprestada do projeto `handwrite_bot`** do Fabio, que já
estava em produção. Ninguém precisa configurar Meta Business, número ou token de novo.

## O que já existe (e está funcionando)

| Item | Valor |
|---|---|
| API | **WhatsApp Cloud API oficial da Meta** (não é Baileys/Evolution/Z-API) |
| Número | o do handwrite_bot (peça ao Fabio; nome verificado hoje: "handwrite bot") |
| Phone number ID | `WHATSAPP_PHONE_ID` no `.env` (é o id da API, não o número) |
| App da Meta | o mesmo app do handwrite_bot |
| Token | System User, **não expira**, escopos `whatsapp_business_messaging` + `whatsapp_business_management` |
| Graph API | `https://graph.facebook.com/v23.0` |
| Hospedagem usada até agora | [Modal](https://modal.com), workspace `fabio-araujo-silva` |
| Webhook atual | aponta para o deploy novo: `https://fabio-araujo-silva--hackfood-bot.us-east.modal.run/whatsapp` (URL antiga do handwrite no backup do Fabio) |

### Onde estão as credenciais

- **Modal:** secret `hackathon-whatsapp` (cópia só deste projeto; não mexa no `whatsapp-meta`, que é do handwrite).
- **Local:** `.env` na raiz (fora do git). Peça ao Fabio. Os nomes das variáveis estão em `.env.example`.

| Variável | Para quê |
|---|---|
| `WHATSAPP_TOKEN` | `Authorization: Bearer` em toda chamada da Graph API |
| `WHATSAPP_PHONE_ID` | entra no caminho: `POST /{PHONE_ID}/messages`, `POST /{PHONE_ID}/media` |
| `WHATSAPP_VERIFY_TOKEN` | nosso; a Meta ecoa na verificação do webhook (GET) |
| `META_APP_SECRET` | valida o header `X-Hub-Signature-256` dos POSTs. Hoje está `PREENCHER` (desligado) |
| `MEU_NUMERO` | allowlist de wa_id separados por vírgula; `PREENCHER`/vazio = responde a todo mundo |

Convenção herdada: valor `PREENCHER` = não configurado (trate como string vazia).

## Status da conta (checado em 2026-10-17; dados do número reconferidos na Graph API em 2026-10-18)

- Recebe mensagem e responde dentro de 24h: **OK** (testado ponta a ponta).
- Mensagem iniciada por nós (template): **BLOQUEADA**, erro 141006 (método de pagamento da WABA com problema,
  visto em 17/10). Até o Fabio trocar o cartão no Meta Business Suite, não conte com template nem mensagem proativa.
- Número (`GET /{PHONE_ID}`): limite **TIER_250** (250 conversas iniciadas por nós a cada 24h; a empresa não é
  verificada), qualidade GREEN, nome "handwrite bot" com `name_status` AVAILABLE_WITHOUT_REVIEW (pode ser usado
  sem revisão). Não é Official Business Account (`is_official_business_account: false`), então **Groups API
  não está disponível**. E grupos não aceitam botões nem listas de qualquer jeito.
- **18/10 a partir das 05:01: a Meta parou de entregar TODA resposta** (até dentro da janela de 24h), erro
  `131042 Business eligibility payment issue`: a conta do WhatsApp Business está sem moeda configurada no
  faturamento. O bot recebe, entende e responde normalmente (log "envio falhou" no Modal), quem barra é a Meta.
  Só o Fabio resolve: Meta Business Suite → Faturamento e pagamentos → conta do WhatsApp → definir país/moeda.
- Política da Meta desde 15/01/2026: proibido chatbot de IA de uso geral. IA para tarefa do negócio (pedir comida)
  pode. O bot deve recusar papo fora do assunto em vez de virar um ChatGPT no zap.

## Virada do número para o deploy novo (feita em 17/10, antes das 16h37)

O número já entrega mensagens para o nosso endpoint (`/whatsapp` no Modal). A virada troca o callback
**só deste número**, sem mexer no app. O jeito usado é `scripts/virar_webhook.py` (padrão: URL nova;
`--url <URL antiga>` desfaz). O equivalente em curl:

```sh
curl -X POST "https://graph.facebook.com/v23.0/$WHATSAPP_PHONE_ID" \
  -H "Authorization: Bearer $WHATSAPP_TOKEN" -H "Content-Type: application/json" \
  -d '{"webhook_configuration":{"override_callback_uri":"<URL_NOVA>","verify_token":"'$WHATSAPP_VERIFY_TOKEN'"}}'
```

A Meta faz um GET de verificação na URL nova antes de aceitar, então o endpoint já precisa responder ao
`hub.challenge`. Para voltar ao handwrite: mesma chamada com a URL antiga (está no backup).
Backup completo da config antiga: na máquina do Fabio, fora do git.

## Como o webhook funciona (lições do handwrite, já testadas em produção)

- **GET `/`**: verificação. Se `hub.mode == "subscribe"` e `hub.verify_token` bate (use `hmac.compare_digest`),
  devolva `hub.challenge` em texto puro. Senão, 403.
- **POST `/`**: eventos. **Responda 200 na hora** e processe em segundo plano (fila/spawn). Webhook lento
  ou que devolve erro é desativado pela Meta. Devolva 200 até para payload estranho.
- **Dedup por `message.id`**: a Meta reenvia em retry, e a mesma mensagem pode chegar mais de uma vez.
- Formato: `entry[].changes[].value` traz `messages[]` (o que chegou), `contacts[]` (o `profile.name` de
  quem mandou) e `statuses[]` (sent/delivered/read/**failed** das nossas mensagens).
- Tipos de `message.type` que já tratamos: `text`, `document`, `image`, `interactive` (resposta de botão
  ou lista) e `button` (quick reply de template).
- O `from` vem **sem o nono dígito** em números BR (ex.: `55DD8XXXXXXX`). Normalize antes de comparar.

### Responder

```json
POST /{PHONE_ID}/messages
{"messaging_product": "whatsapp", "to": "<wa_id>", "type": "text", "text": {"body": "oi"}}
```

- Botões: `type: "interactive"`, com `interactive.type` igual a `button` (até 3) ou `list` (até 10 itens).
- Arquivo: `POST /{PHONE_ID}/media` (multipart, `messaging_product=whatsapp`) devolve um `id`; depois mande
  `type: "document"` ou `"image"` com `{"id": ...}`. Para baixar mídia recebida: `GET /{media_id}` devolve
  uma `url`, que você baixa com o mesmo Bearer.
- "Digitando...": `POST /{PHONE_ID}/messages` com
  `{"status": "read", "message_id": "<id recebido>", "typing_indicator": {"type": "text"}}`. Dura até 25 s.

### Janela de 24h (pegadinha principal)

Texto livre só pode ser mandado até **24h depois da última mensagem da pessoa**. Fora da janela, só
**template aprovado** pela Meta. A Graph devolve 200 do mesmo jeito, e a falha (erro **131047**) chega
depois como `statuses[].status == "failed"` no webhook. Mensagem proativa precisa de template.
