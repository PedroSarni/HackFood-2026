# 05 — Documento Técnico Resumido

Time: Davi, Fabio, Pedro e Breno (Hackathon iFood × SEMCOMP 29, 17–18/10/2026).
Repositório: `PedroSarni/AiFood-2026`. Detalhe completo em `docs/como-funciona.md`.

## 1. Tese técnica: "a IA entende, o código garante"

Os modelos de IA só transformam mensagem (texto, áudio, foto) em JSON com formato fixo. Quem decide o próximo passo, chama o iFood, faz contas e conduz o pedido é código determinístico. A confirmação de compra nunca parte de um modelo.

## 2. Arquitetura

```
WhatsApp ──► Meta Cloud API ──► webhook /whatsapp (Modal, responde 200 na hora)
                                     │ fila por pessoa
                                     ▼
                              rodada (junta a rajada)
                                     ▼
                         Bot.processar  (src/bot/fluxo.py, "Maestro")
                           ├─ botão → caminho sem IA
                           ├─ texto/áudio/foto → regras rápidas → agente de IA → intenção JSON
                           └─ src/bot/ifood.py → cliente MCP (ou mock com a mesma interface)
                                     ▼
                         respostas com botões/cards (Graph API)
   funções de fundo: rastreio, lembretes (cron 15 min), cutucada/abandono
   diário de eventos (modal.Dict) ──► servidor local ──► dash React
```

| Camada | Tecnologia |
|---|---|
| Backend | Python no Modal (webhook, funções de fundo, cron) |
| Estado | `modal.Dict` por pessoa (conversa, tokens, lembretes, configuração) |
| Canal | WhatsApp Cloud API (Meta) |
| IA de texto e foto | Claude Sonnet 5.5 primeiro, Gemini como reserva, OpenRouter por último; fila configurável por agente |
| Áudio | ElevenLabs Scribe (ouvir) e ElevenLabs (falar); Gemini ouve se o Scribe estiver fora |
| Dash | React + React Router + Vite, servidor local só em 127.0.0.1 |

## 3. Agentes

Cada agente tem um arquivo em `src/agentes/` com ficha, plano B e fila de modelos própria. Os agentes não se chamam entre si; o código orquestra.

| Agente | Papel | Plano B sem IA |
|---|---|---|
| Lia | entende a mensagem (intenção, itens, quantidade) | regras rápidas e busca pelo texto cru |
| Íris | lê fotos (comida, lista, produto, outra coisa) | pede para escrever |
| Duda | filtra e ordena as ofertas pelo que a pessoa pediu | filtro por palavra no nome do item |
| Beto | composição do kit em grupo | `kit_padrao` |
| Tungs | tutor (como usar o bot) | textos fixos |
| Vina | roteiro da resposta por áudio | resposta em texto |
| Otto | transcrição de áudio | Gemini ouve |
| Sofia | insights no dash | — |

Cada agente pode ser desligado ou trocar de modelo pelo dash, sem deploy.

## 4. Uso do MCP do iFood

Usamos **19 das 23 tools** do MCP de consumidor, com OAuth 2.1 (Authorization Code + PKCE S256, cliente confidencial, escopos `mcp.*`, refresh 5 min antes de vencer).

| Etapa | Tools |
|---|---|
| Conta e endereço | `getUser`, `listAddresses`, `createAddress` (2 passos: candidatos → confirmação) |
| Descoberta | `searchOffers` (só o termo; refinamentos à parte), `getRecommendations`, `getItem` |
| Carrinho | `createCart`, `addItemToCart`, `removeItemFromCart`, `getCart` |
| Checkout | `getCartDeliveryMethods`, `setCartDelivery`, `listPaymentMethods`, `setCartPayment`, `listVouchers`, `setVoucher` |
| Pedido | `submitOrder(userConsent=true)`, `getOrder`, `trackOrder` (no ritmo de `agentHints.retryMessage` até `pollingStop`) |

Decisões em cima do MCP:
- **Uma busca, várias páginas:** `searchOffers` traz até 25 itens; "Mais opções" pagina localmente antes de pedir a próxima página.
- **Melhor loja para listas:** busca cada item e escolhe a loja com todos os itens e menor total (itens × quantidade + entrega).
- **Opções do item:** o mapeamento para o carrinho é ambíguo na doc; o bot tenta um formato e cai no outro se o iFood recusar.
- **Recorrência construída por nós:** o MCP não tem; guardamos um modelo do pedido e refazemos com `createCart`.
- **Proteção do gateway:** freio local (0,35 s entre chamadas por container), disjuntor de 5 min ao ver o 403 do firewall, container bloqueado se aposenta e uma ponte refaz a chamada de outro IP.
- **Contingência de apresentação:** com o "modo palco" armado, a chamada real tem prazo de 10 s e uma tentativa; na primeira queda o mock (mesma interface, catálogo de demonstração) assume e a mesma chamada é refeita. Desligado por padrão: fora do palco, falha real é erro real.

## 5. Decisões técnicas

- **Rajada de mensagens:** fila por pessoa + espera de silêncio adaptativa (0,6 s botão; ~4 s "oi"; ~2,5 s texto; teto 9 s) + trava; mensagens reordenadas pelo horário da Meta.
- **Regras antes da IA:** "sim", "não", números, "menu", "cancelar" são resolvidos sem modelo (rápido e sem custo).
- **JSON garantido:** esquema fixo de intenção (`ESQUEMA` em `interpretar.py`); resposta fora do esquema cai no plano B.
- **Confirmação no código:** `submitOrder` só depois do toque em "Confirmar pedido" ou de um "sim" da pessoa no resumo ("já pode passar no pix" fecha direto); trava contra toque duplo.
- **Dinheiro só no código** e "por pessoa" arredondado para cima no centavo; o modelo nunca calcula valor.
- **Pagamento só PIX e vales:** cartão exige `cardTokenId`, que nenhuma tool fornece.
- **Botões com identificador:** botão antigo é reconhecido e gera um aviso só; o "sim" de uma foto antiga não vale para a nova.
- **Configuração sem deploy:** interruptores no armazém (`scripts/modo.py`: mock, palco, lojas fechadas, lembrete rápido, cutucada).

## 6. Segurança e privacidade

- CPF validado só no código (dígitos verificadores), nunca enviado a modelo, enviado ao iFood só no fechamento.
- Na etapa do CPF, foto não é aberta; documento pessoal nunca é transcrito nem registrado.
- Diário do dash grava as mensagens com CPF mascarado, sem token nem link de login; telefone mascarado no dash; servidor do dash só em 127.0.0.1.
- Keys só nos secrets do Modal; o dash mostra só os 4 últimos caracteres.
- "sair" revoga o login iFood; "apagar meus dados" apaga o que guardamos.
- Bot recusa assunto fora de pedido (política da Meta contra chatbot genérico).

## 7. Qualidade

- **521 testes automatizados** (pytest) cobrindo fluxo, recorrência, kit, CPF, foto, áudio e rotinas, contra o mock com a mesma interface do MCP.
- Testes do dash com Vitest.
- QA manual no WhatsApp durante a madrugada de 18/10 (mock e MCP real), com os problemas registrados em `docs/qa-18-10.md` e a maioria corrigida.
- Regras de colaboração no repo: claims por feature (`.coord/claims/`), hooks de autoria e de arquivos protegidos.

## 8. Limitações conhecidas

- Sem cartão, sem retirada, sem entrega agendada, sem cancelamento pela API.
- `submitOrder` não devolve código PIX nem QR.
- Bloqueio do gateway por rajada de requisições torna o MCP real instável em demonstração.
- Kit em grupo: ajustes em sequência ainda são o ponto mais frágil.
- Quantidade segue a unidade de venda do item (unidade, quilo, pacote, bandeja), lida do nome e da descrição; item sem unidade escrita pode ser contado errado.
- Detalhes das dores do MCP no entregável 06.
