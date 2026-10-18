# 06 — Feedback sobre o MCP de consumidor do iFood

Time: Davi, Fabio, Pedro e Breno (Hackathon iFood × SEMCOMP 29, 17–18/10/2026).
Servidor testado: `https://consumer-mcp.ifood.com.br/marketplace`, conta de teste, doc de referência do portal v0.27.0.

## 1. Como testamos

- QA manual, uma chamada por vez, em uma conta de teste, no sábado 17/10/2026.
- Cobrimos as 4 áreas (User, Discovery, Cart, Order Tracking): sucesso, entradas inválidas, limites e erros.
- Regras que seguimos: nunca chamamos `submitOrder`, nunca usamos cartão, nenhum token ou secret foi registrado.
- Resultado do QA de 17/10: cerca de 70 achados, cada um com a chamada, o esperado (doc), o real e o impacto. Log completo no anexo.
- Dois cuidados de honestidade: os horários do log são ordem das chamadas, não hora exata; e não testamos o que está na seção 6.

## 2. As 6 dores que mais custam a quem constrói um agente

**1. `cartItemId` muda a cada escrita no carrinho.**
- O que acontece: depois de `addItemToCart`, `updateCartItem`, `removeItemFromCart`, `setCartDelivery`, `setCartPayment`, `setVoucher` ou `removeVoucher`, as linhas sem promoção ganham novo `cartItemId`.
- Por que dói: a doc manda guardar o `cartItemId` devolvido. Quem guarda e depois remove recebe "O item não está mais disponível" e diz ao cliente que o produto acabou.
- Como reproduzir: crie um carrinho com 2 linhas, adicione um item, chame `removeItemFromCart` com o ID que o `addItemToCart` devolveu antes.
- Sugestão: manter o ID por linha, ou devolver `previousCartItemId` e um erro `CART_ITEM_NOT_FOUND` com dica "chame `getCart`".

**2. Erros sem padrão.**
- O que acontece: 4 formatos JSON diferentes (User, Discovery, Cart, Tracking) e 3 formas de texto cru (exceção Java do Jackson, NPE do Kotlin com nome de classe interna, chave de tradução `item.quantity.invalid`). `retryable` só existe em User e Tracking. Em User, `retryable: true` aparece para erro de entrada do usuário.
- Por que dói: o agente precisa decidir entre tentar de novo, perguntar ao usuário ou desistir, e hoje decide por texto.
- Como reproduzir: `getCart` com `cartId="abc"` (exceção Java); `updateCartItem` com `quantity=-2` (chave i18n); `getCart` com UUID inexistente (`GEN-123 "try again"`).
- Sugestão: um envelope único `{error:{code,message,retryable,retryAfterSeconds,userMessage}, agentHints}`, sempre JSON, separando `retryable` de `needsUserInput`.

**3. Mensagens e respostas que enganam.**
- Quatro situações diferentes viram "O item não está mais disponível" (ID de linha antigo, `itemId` no lugar de `cartItemId`, item de outra loja, item realmente indisponível).
- `setVoucher` com cupom não aplicável responde sucesso; só um `agentHints` diz que não se aplica. `listVouchers` marca `available: true` para ele.
- `setCartDelivery` com horário inválido ou de outro método responde sucesso e troca o horário em silêncio (de amanhã 9h para hoje 20h).
- Sugestão: códigos como `CART_MERCHANT_MISMATCH`, `VOUCHER_NOT_APPLICABLE`, `TIMESLOT_NOT_AVAILABLE`, `INVALID_QUANTITY`, retornados como erro, não como sucesso.

**4. Preços e totais que não fecham.**
- `promotionalUnitPrice` maior que `unitPrice` em itens de `getMerchant` (70 → 115,50).
- O mesmo item com preço promocional diferente em `getMerchant` (115,50) e `getItem` (45,50).
- A segunda unidade sai a preço cheio, sem aviso claro de que a promoção vale uma unidade.
- Em um carrinho de mercado: subtotal 7,39 + entrega 0 + taxa 1,99 = 9,38, mas `totalAmount` veio 5,54, sem linha de desconto nem nome de cupom. A diferença (3,84) é exatamente 52% do subtotal (7,39 × 0,52), e a conta de teste tem um cupom "52% OFF em mercados" ativo. Ou seja, o iFood aplicou um cupom automaticamente, mas a API não diz qual nem mostra a linha de desconto (hipótese forte). No site, esse mesmo cupom aparece como disponível para um carrinho de mercado, mas só pode ser aplicado depois de escolher uma forma de pagamento ("Escolha forma de pagamento válida"); na API o desconto já apareceu sem forma de pagamento definida.
- A conta de teste tem 193 cupons no site, e `listVouchers` devolveu 7 para o carrinho, sem explicar o filtro.
- `benefitsTotalAmount` não tem relação estável com o total (às vezes maior que ele).
- `orderMinimumPrice` do carrinho veio 0 em uma pizzaria, enquanto `getMerchant` dizia 25.
- Pedido abaixo do mínimo: o site mostra o aviso "O pedido mínimo para essa loja é de R$ 40,00" e desabilita o botão de pagamento; a API deixou criar o carrinho (R$ 7,39, mínimo de R$ 60), definir a entrega e seguir, sem nenhum aviso. Um agente só descobriria no fim, ao tentar finalizar.
- Sugestão: fonte única de preço, uma lista `discounts[]` com o nome e o valor de cada cupom aplicado (inclusive os automáticos), e documentar `benefitsTotalAmount` e a taxa de serviço.

**5. Descoberta e respostas pouco adequadas a um agente de chat.**
- `getItem` devolveu 61 KB (~15 mil tokens) para um único item (3 grupos com 12, 77 e 77 opções).
- `facets` de `browseOffers` são calculados só sobre a página retornada; `listItemTaxonomy` não existe no servidor (doc diz 24 tools, o servidor tem 23).
- `nextPageToken` é solto da query e a paginação por offset repete ou pula lojas, porque o ranking muda entre chamadas.
- Uma query de 5000 caracteres volta ecoada duas vezes na resposta.
- Sugestão: paginar ou resumir `optionGroups`, limitar a query, calcular facets sobre o universo e prender o token à query.

**6. Endereço falso é aceito.**
- `createAddress` com endereço inexistente devolveu um endereço na Califórnia, com `matchConfidence: "SINGLE"` (a doc promete `PLACE_NOT_FOUND`).
- Para texto ambíguo ("Rua das Flores, 10") devolve 5 cidades sem viés pela localização do usuário.
- Sugestão: restringir ao Brasil, aceitar a localização do usuário como dica e devolver `PLACE_NOT_FOUND` quando número ou cidade não batem.

## 3. Doc × schema × realidade

| Tema | Doc / schema diz | Realidade |
|---|---|---|
| Número de tools | 24 | 23 (falta `listItemTaxonomy`) |
| `options` em `addItemToCart` | doc: obrigatório; schema: opcional | sem `options` estoura exceção; `options=[]` funciona; `createCart` aceita sem |
| `paymentMethodId` | exemplos "PIX", "CREDIT_CARD" | é UUID; o tipo fica em `kind` |
| `sort` | descrição manda `sort:RATING` | `RATING` não existe no enum |
| `getUser` | níveis BASIC/ADVANCED/BEHAVIOR | único parâmetro é `includeProfileData`, sem efeito visível |
| Erros do Cart | `retryable` e detalhes | sem `retryable`, código genérico |
| `ORDER_NOT_FOUND` | — | vem com `retryable: false` |
| Carrinho vazio | fluxo createCart → addItemToCart | `createCart` já exige o 1º item |
| Endereço no Discovery | — | só aceita lat/lng, nunca `addressId` |
| Time slots | "agendado" | existem em mercado (`timeslotId` na resposta, `selectedTimeSlotId` na entrada); omitidos em restaurante |
| Listar pedidos | — | não existe tool; `RECENT_ORDERS` veio vazio na conta de teste |

## 4. O que funciona bem

- Fluxo de endereço em dois passos (`createAddress`) com `candidateId` e coordenadas.
- `listPaymentMethods` devolve PIX e cartão de teste com UUID.
- Cálculo do total bateu em todas as respostas de carrinho, exceto no caso do mercado com agendamento.
- `agentHints` ajudam quando corretos (por exemplo, o erro de `setCartDelivery` com método inválido).
- Erros de Tracking são estruturados e acionáveis (`INVALID_ORDER_ID`, `ORDER_NOT_FOUND`).
- Leitura idempotente, UTF-8 e emoji preservados, paginação por token funciona quando a lista está estável.

## 5. Sugestões priorizadas

1. IDs de linha estáveis no carrinho.
2. Envelope de erro único e sempre JSON, sem vazar exceção interna.
3. Códigos de erro semânticos no lugar de "item indisponível" e "algo deu errado".
4. Preço com fonte única, com linha explícita de desconto.
5. Respostas do tamanho de um chat (opções resumidas, query limitada, paginação presa à query).
6. Geocoding restrito ao Brasil e com a localização do usuário como dica.
7. Listar pedidos (`listOrders`) e expor os escopos do token (`grantedScopes`).

## 6. O que não testamos

- `submitOrder` (proibido) e, por consequência, `trackOrder`/`getOrder` com pedido real e o formato de `RECENT_ORDERS`.
- Pagamento com cartão.
- Loja fechada, `customizations`, voucher aplicado com sucesso.
- Escopos do token (não há tool de introspecção; inferimos pelo comportamento).

## 7. Bloqueio por rajada (403 do Akamai)

- Ao usar o MCP real com várias chamadas seguidas, recebemos `403 Access Denied` em uma página HTML do Akamai, fora do formato MCP. Aconteceu mais de uma vez durante o fim de semana, inclusive no meio de uma conversa de cliente.
- Pelo que observamos, o bloqueio é por IP de saída: o mesmo bot, vindo de outro container (outro IP), passava. Não conhecemos o limite, a janela nem o tempo de bloqueio, e a resposta não traz `Retry-After`.
- Para quem hospeda um agente em nuvem (IP compartilhado e rotativo), um bloqueio sem aviso afeta todos os usuários ao mesmo tempo.
- Sugestão: responder `429` com `Retry-After` e documentar o limite por cliente (ou por token do usuário, não por IP).
- Nossa mitigação: freio local de ~3 chamadas por segundo, disjuntor de 5 minutos ao ver o 403, container barrado se aposenta e uma ponte refaz a chamada de outro IP. Na apresentação, um modo de contingência troca para um catálogo de demonstração na primeira queda.

## 8. Achados de 18/10 com o MCP real

- **CPF só aparece no `addItemToCart`/`createCart`.** Uma loja real (farmácia/mercado) respondeu `MERCH-007 "este restaurante obriga a digitação do CPF"` ao adicionar o primeiro item. A doc diz que o CPF vai no `submitOrder`. Um agente só descobre a exigência depois que a pessoa já escolheu o produto, e a mensagem diz "restaurante" para uma loja que não é restaurante.
  - Sugestão: expor `requiresCpf` em `searchOffers`/`getMerchant`, ou aceitar o CPF depois, só no `submitOrder`.
- **Total parcial com taxas.** Em um item de R$ 36,99, o total do carrinho veio R$ 47,97 (entrega + taxa). O agente precisa somar sozinho para explicar a diferença; um campo `fees[]` com nome e valor resolveria.
- **Catálogo sem marca.** Buscar "carne friboi" em um mercado real não trouxe nenhum produto da marca; trouxe patinho e acém sem marca no nome. O agente precisa de `brand` como campo filtrável.
- **Lista pesada para chat.** `searchOffers` devolve até 25 itens por página; para um carrossel de WhatsApp (3 cards) a maior parte é descartada.
