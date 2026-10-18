# 01 — Proposta de Negócio

Time: Davi, Fabio, Pedro e Breno (Hackathon iFood × SEMCOMP 29, 17–18/10/2026).
Produto: "Compras pelo WhatsApp", um assistente de compras do iFood que funciona dentro do WhatsApp.

## 1. O problema

Pedir no app de delivery exige navegar por telas, filtros, carrinho e pagamento. Para quem tem pouca prática com aplicativos, cada uma dessas telas é um ponto de desistência. Essas pessoas já usam o celular, mas muitas vezes só para conversar.

Dados que sustentam isso (IBGE, PNAD Contínua TIC 2023):
- O uso de internet entre pessoas com 60 anos ou mais subiu de 24,7% (2016) para 66,0% (2023).
- Entre quem usa internet, 91,1% enviam ou recebem mensagens por aplicativos (texto, voz ou imagem).

Leitura do time (argumento, não dado medido): a conversa é a interface que esse público já domina, e o app de delivery não é. Existe uma base grande e crescente de pessoas conectadas que o iFood ainda atende com uma interface pensada para outro perfil.

## 2. Para quem

- Pessoas idosas ou com pouca familiaridade digital, que conversam no WhatsApp mas evitam apps.
- Pessoas que repetem quase sempre a mesma compra (mercado da semana, lanche de sempre).
- Grupos que querem dividir um pedido (lanche com amigos).

## 3. Proposta de valor

Pedir do iFood como quem manda uma mensagem a alguém de confiança.

- **Fala do jeito que a pessoa quer:** texto, áudio ou foto (lista de papel, embalagem, foto de comida). O assistente entende e responde, por escrito ou por áudio quando a pessoa pede.
- **Nunca deixa a pessoa perdida:** toda mensagem termina dizendo o que fazer; poucas opções por vez, com botões grandes e "Mais opções".
- **Repete a compra com 1 toque:** "toda semana às 18h". O assistente lembra, mostra itens, endereço e valor, e só fecha com o "sim" da pessoa.
- **Ajuda a fechar o pedido:** quando falta pouco para o pedido mínimo, sugere o que combina; para grupos, monta um kit numa loja só e diz quanto fica para cada um.
- **Segurança por desenho ("a IA entende, o código garante"):** o pedido só é fechado com a confirmação explícita da pessoa (um toque em "Confirmar pedido" ou um "sim" dela); o CPF nunca passa pela IA; a pessoa pode apagar seus dados.

## 4. O que já existe: o Ailo

O iFood já tem o Ailo, um agente próprio no WhatsApp (lançado em out/2025, hoje em beta). Ele resolve bem o pedido de restaurante para quem já é cliente: reconhece a pessoa pelo número, sugere pratos pelo histórico e explica a sugestão ("chega em 30 min e a entrega é R$ 5"). É a prova de que o WhatsApp é um bom canal para o iFood.

Nossa proposta olha para o espaço ao lado, e é complementar:
- **Compra da semana, não só a refeição do dia:** mercado, padaria e farmácia, com várias coisas no mesmo pedido.
- **Quem pouco usa o app:** pessoas que conversam no WhatsApp, mas não abrem o app de delivery. O pedido sai por texto, áudio ou foto (a lista de papel).
- **Compra que se repete:** "toda semana às 18h". O assistente lembra e só fecha com o "sim" da pessoa.
- **Pedido em grupo:** um kit numa loja só, com o valor por pessoa.

Os dois produtos usam o mesmo ecossistema (lojas, pagamento, entrega e rastreio do iFood), então uma pessoa pode começar em um e continuar no outro. A nossa leitura é que o Ailo atende quem já pede restaurante pelo app, e o nosso assistente atende o mercado e a farmácia da semana de quem não usa o app.

## 5. Por que isso interessa ao iFood

Hipóteses do time, a validar com dados reais do iFood:
- **Novo canal para um público pouco atendido:** o pedido continua sendo do iFood (loja, pagamento, entrega, rastreio). O assistente só muda a porta de entrada.
- **Mais frequência:** a recorrência transforma a compra habitual em hábito automático. O MCP do iFood não tem recorrência nativa, e a gente construiu uma por cima.
- **Ticket e conclusão:** sugestões para atingir o pedido mínimo e itens que combinam (refri com lanche) reduzem pedidos que travam antes do fim.
- **Sem integração nova:** usa o MCP oficial de consumidor, com o login do próprio cliente no iFood.

## 6. Como medir se funciona

Propostas de métrica (ainda não medidas):
- Pedidos concluídos sem ajuda humana, sobre conversas iniciadas.
- Mensagens até o pedido fechado.
- Pessoas com compra recorrente ativa e quanto delas confirma o lembrete.
- Quantas desistem em cada etapa (endereço, escolha, pagamento).

## 7. Viabilidade e limites

- Funciona de ponta a ponta: login no iFood, endereço, busca, carrinho, resumo, confirmação, rastreio e lembrete, com testes automatizados e QA manual no MCP real.
- Limites que encontramos no MCP e que afetam o produto (detalhes no entregável 06): sem tool de listar pedidos, bloqueio de requisições em rajada, e respostas pesadas para um chat. O assistente já se protege com freio de chamadas e um modo de contingência para apresentações.
- Pagamento: o assistente oferece só o que um bot consegue pagar com segurança, PIX e vales. Cartão não entra nesta versão.

## 8. Próximos passos

- Medir com usuários reais do público-alvo.
- Ampliar as lojas e categorias suportadas.

## Fontes

- IBGE, Agência de Notícias: [Em 2023, 88,0% das pessoas com 10 anos ou mais utilizaram internet (PNAD Contínua TIC)](https://agenciadenoticias.ibge.gov.br/pt/agencia-noticias/41026-em-2023-87-2-das-pessoas-com-10-anos-ou-mais-utilizaram-internet.html?lang=pt-BR)
- Canaltech: [iFood lança agente de IA que permite fazer pedidos pelo WhatsApp](https://canaltech.com.br/apps/ifood-lanca-agente-de-ia-que-permite-fazer-pedidos-pelo-whatsapp-veja-como-usar/)
- Consumidor Moderno: [iFood, WhatsApp e o agente Ailo](https://consumidormoderno.com.br/ifood-whatsapp-canal-compras-agente-ailo/)

