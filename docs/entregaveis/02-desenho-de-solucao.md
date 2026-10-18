# 02 — Desenho de Solução: fluxo geral

Time: Davi, Fabio, Pedro e Breno (Hackathon iFood × SEMCOMP 29, 17–18/10/2026).
Produto: "AiFood, compras pelo WhatsApp", um assistente que faz o pedido no iFood por quem conversa com ele no WhatsApp.

## 1. Visão em uma frase

A pessoa conversa por texto, áudio ou foto. A IA entende o pedido e o código conduz cada passo no MCP do iFood, até a confirmação da pessoa.

## 2. As peças

```
 Pessoa no WhatsApp
        │  texto / áudio / foto / toque em botão
        ▼
 Meta (WhatsApp Cloud API)
        │  webhook
        ▼
 Nosso backend (Python no Modal)
   ├─ junta a rajada de mensagens
   ├─ agentes de IA: só entendem e propõem (JSON)
   ├─ "Maestro" (código): decide, chama o iFood, faz as contas
   └─ diário de eventos ──────────► Dash do time (React)
        │
        ▼
 MCP do iFood (consumidor)
   lojas, ofertas, carrinho, entrega, pagamento, pedido, rastreio
```

## 3. Fluxo principal: do "oi" ao pedido entregue

1. **Primeiro contato.** A pessoa manda "oi" ou já manda o pedido. O bot cumprimenta e mostra ideias (vitrine).
2. **Login no iFood (uma vez).** Botão "Entrar no iFood" abre o login oficial do iFood (OAuth). Ao voltar, o bot retoma o que ela tinha pedido.
3. **Endereço.** Vem da conta iFood dela. Com 1 endereço, usa direto; com vários, confirma o mais provável numa pergunta; sem nenhum, pede e salva.
4. **Entender o pedido.** "pão, leite e café", um áudio ou a foto de uma lista de papel viram itens com quantidade e tipo de loja.
5. **Escolher a loja.** Em lista com vários itens, o bot procura a loja que tem tudo e sai mais barata (itens + entrega). O iFood fecha um pedido por loja.
6. **Mostrar opções.** Carrossel de cards com foto e botão "Quero esse" (até 10 por vez), mais "Mais opções". A pessoa toca ou diz "o do meio".
7. **Carrinho.** Opções obrigatórias (tamanho, sabor) uma de cada vez, depois a quantidade na unidade de venda (unidade, kg, pacote). Se faltar para o pedido mínimo, o bot sugere o que combina.
8. **Fechar.** Com "🧾 Revisar pedido" (ou "pode fechar"), o bot escolhe a entrega padrão, a forma de pagamento (PIX ou vale), aplica o melhor cupom, pede o CPF da nota (pode pular) se não estiver na conta iFood, e mostra o resumo com itens, entrega, pagamento, endereço e total.
9. **Confirmação explícita.** Só um toque em "Confirmar pedido" ou um "sim" da pessoa no resumo faz o pedido ("já pode passar no pix" fecha direto, sem CPF na nota).
10. **Depois do pedido.** O bot acompanha o status no ritmo que o iFood indica e avisa cada mudança ("saiu pra entrega"). Em qualquer momento, "cadê meu pedido?" ou "qual o código de entrega?" são respondidos.

## 4. Fluxos que saem do principal

### 4.1 Compra recorrente
- **Como começa:** na 2ª compra do mesmo item ou categoria, o bot oferece "deixar no automático". Também começa se a pessoa pedir ("toda semana às 18h").
- **No dia:** o lembrete mostra itens, loja, endereço, pagamento e valor da última vez.
- **"Sim, pode pedir":** refaz o carrinho e fecha. Se o preço subiu mais de 10%, mostra o resumo antes.
- **"Hoje não" / "Parar lembretes":** adia ou desliga. Sem o sim, nada é pedido.

### 4.2 Pedido em grupo (kit)
- "somos 6, lanche até R$ 100" vira um kit numa loja só.
- A IA propõe a composição; o código respeita orçamento, restrições ("sem refri") e faz a conta por pessoa.
- Botões: "Quero esse kit", "Outra loja", "Não quero". O carrinho só é criado no "Quero esse kit".

### 4.3 Foto
- Comida: o bot pergunta se procura algo parecido.
- Lista de papel ou produto: vira a lista do pedido.
- Outra coisa: comenta e volta ao ponto da conversa (no meio dos cards, volta ao menu).
- Na etapa do CPF, a foto nem é aberta (pode ser documento).

### 4.4 Quando a pessoa some ou muda de ideia
- Pergunta sem resposta: uma cutucada ("Ainda está por aí?").
- Carrinho parado: depois de alguns minutos, o bot esquece o carrinho local e volta ao menu.
- Em qualquer etapa, "cancelar", "mudar" ou um pedido novo são entendidos; botão antigo gera um aviso só.

### 4.5 Quando o iFood falha
- Freio de chamadas e disjuntor evitam derrubar o gateway e esperam o bloqueio passar.
- No modo de apresentação, a primeira queda liga um catálogo de demonstração e a mesma chamada é refeita nele. O time vê um aviso no dash.

## 5. Quem decide o quê

| Etapa | IA (propõe) | Código (garante) |
|---|---|---|
| Entender a mensagem | intenção, itens, quantidade | regras rápidas antes da IA; plano B sem IA |
| Ler a foto | tipo da foto, itens da lista | CPF/documento nunca vai pra IA |
| Escolher a loja | — | conta itens + entrega, escolhe a mais barata com tudo |
| Montar o kit | composição | orçamento, restrições, conta por pessoa |
| Fechar o pedido | — | entrega, pagamento, cupom, resumo |
| Confirmar | nunca | só toque ou "sim" da pessoa |

## 6. Fora do escopo desta versão
- Cartão de crédito (a API não fornece token de cartão).
- Retirada na loja e entrega agendada.
- Cancelamento e reembolso pela API.
- Dividir o pagamento entre amigos (o bot só informa quanto fica para cada um).
