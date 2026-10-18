# 03 — Racional da Experiência: decisões de UX

Time: Davi, Fabio, Pedro e Breno (Hackathon iFood × SEMCOMP 29, 17–18/10/2026).
Produto: "AiFood, compras pelo WhatsApp".

## Princípio central

Pedir do iFood deve parecer mandar mensagem para alguém de confiança. Cada decisão abaixo responde a uma pergunta: **onde uma pessoa com pouca prática com aplicativos desistiria?** Todas foram testadas à mão no WhatsApp, em rodadas de QA na madrugada de 18/10, e várias mudaram por causa do que o teste mostrou.

## 1. A pessoa fala do jeito dela

**Decisão:** aceitar texto, áudio e foto (lista de papel, embalagem, foto de comida), e responder por áudio quando a pessoa pede.
**Por quê:** quem não domina o app costuma dominar a conversa. Digitar é a barreira para muita gente; falar e fotografar não.
**Evidência:** áudio funcionou com música ao fundo; lista de papel por foto virou carrinho; "me responde por áudio" passou a valer na conversa.
**Cuidado:** a quantidade segue a unidade de venda ("Quantos quilos de banana?", não "quantas unidades"). **Limite conhecido:** "leite" falado vira um tipo de leite escolhido pelo bot.

## 2. Várias mensagens curtas valem como uma só

**Decisão:** o bot espera um silêncio curto e responde a tudo de uma vez ("oi", "quero", "pão", "e leite" geram uma resposta, não quatro).
**Por quê:** quem tem pouca prática manda frases picadas e continua digitando enquanto o bot pensa. Respostas cruzadas confundem.
**Como:** o tempo de espera depende do tipo de mensagem (toque de botão ~0,6 s; "oi" curto ~4 s; texto normal ~2,5 s; teto de 9 s). Uma trava impede resposta duplicada.

## 3. Nunca deixar a pessoa perdida

**Decisão:** toda resposta termina com o próximo passo, em botões grandes, e só com botões que levam a algo ("Meu pedido" só aparece com pedido feito).
**Por quê:** o pior momento da conversa é a tela em que a pessoa não sabe o que fazer.
**Complemento:** o que a pessoa diz manda e o botão é atalho. Se ela digita "mudar" ou o número da opção, funciona igual ao toque. Em qualquer etapa, uma pergunta ("quanto deu?", "cadê meu pedido?") é respondida e a conversa volta de onde estava.
**O que o QA mostrou:** "Mudar" digitado no pagamento não funcionava, e não havia como voltar no pagamento e no CPF. Corrigimos os dois.

## 4. Poucas opções por vez, com foto

**Decisão:** mostrar 3 opções em cards com foto e botão "Quero esse", mais um "Mais opções" que reaproveita a lista já buscada.
**Por quê:** uma lista longa cansa e a foto reduz o erro de escolha. A pessoa pode tocar ou dizer "o do meio", "a segunda".

## 5. O bot escolhe o que dá para escolher por ela

**Decisão:** o bot escolhe sozinho a entrega padrão, aplica o melhor cupom e, em lista com vários itens, procura a loja que tem tudo e sai mais barata.
**Por quê:** cada pergunta a menos é uma chance a menos de desistência. O iFood fecha um pedido por loja, então escolher a loja antes é mais simples do que explicar isso à pessoa.
**Transparência:** o resumo mostra itens, entrega, pagamento, endereço e total. Quando o valor "até agora" inclui entrega e taxa, o texto explica a diferença (problema que o QA encontrou).

## 6. Só fecha com confirmação explícita

**Decisão:** o pedido só é feito com a confirmação da pessoa: um toque em "Confirmar pedido" ou um "sim" dela no resumo, por voz ou texto. A confirmação nunca vem da IA.
**Por quê:** pedido errado custa dinheiro e confiança. Para esse público, uma compra indesejada acaba com o uso.
**O que o QA mostrou:** um "sim" solto digitado ao lado de uma sugestão fechava o pedido por engano. A sugestão passou a valer uma mensagem só: o "sim" é sempre para o pedido.

## 7. Compra que se repete com 1 toque

**Decisão:** oferecer o automático na 2ª compra do mesmo item ou categoria, ou quando a pessoa pede ("toda semana às 18h"). No dia, o lembrete mostra itens, loja, endereço, pagamento e valor da última vez, e o "Sim, pode pedir" fecha. Sem o sim, nada é pedido.
**Por quê:** é a maior economia de esforço para quem repete a compra. Mantém o controle com a pessoa.
**Cuidados:** "Não precisa" pausa a oferta por uma semana; "Hoje não" diz quando volta; se o preço subiu mais de 10%, mostra o resumo antes. O lembrete acusava mudança de preço sem ter mudado, e isso foi corrigido.

## 8. Pedido em grupo com a conta feita

**Decisão:** para "somos 6, lanche até R$ 100", o bot monta um kit numa loja só, respeita o orçamento e mostra o valor por pessoa.
**Por quê:** dividir pedido é fonte de atrito entre amigos e a conta é o que mais gera discussão.
**Limite conhecido:** esse foi o ponto mais frágil nos testes. Ajustes em sequência ("sem refri", "mais barato") às vezes reconstruíam o kit do zero. Os ajustes passaram a partir do kit na tela, e a leitura deles pelo código ainda está em andamento. Na demonstração, mostramos o ajuste simples.

## 9. Segurança e limites visíveis

- **CPF fora da IA.** O bot usa o CPF da conta iFood; se não houver, pede uma vez (a pessoa pode pular, salvo loja que exige). Validado no código, nunca enviado a modelo e enviado ao iFood apenas no fechamento.
- **Aviso de maioridade** para bebida alcoólica.
- **Papo fora do assunto é recusado com educação** e a conversa volta ao pedido, em parte por causa da política da Meta contra chatbot genérico.
- **Controle dos dados:** "sair" desconecta a conta; "apagar meus dados" apaga tudo.
- **Pagamento só PIX e vales**, porque a API não fornece token de cartão. Dizemos isso à pessoa.

## 10. Quando algo falha, a pessoa não vê

**Decisão:** botão antigo gera um aviso só (antes repetia a cada toque), e há um modo de contingência: se o MCP falha, o bot passa a usar um catálogo de demonstração, com um aviso discreto apenas no painel interno.
**Por quê:** na hora em que a pessoa mais precisa, o bot não pode travar. O bloqueio por rajada de requisições do gateway torna isso uma preocupação real (detalhes no entregável 06).

## Como validamos

QA manual no WhatsApp, em rodadas (fluxo básico, foto, grupo, áudio, recorrência, papo fora do assunto, MCP real), com ~30 problemas registrados, dos quais a maioria corrigida durante a noite. Suíte de 521 testes automatizados. Ainda **não** testamos com pessoas do público-alvo, e é o primeiro passo depois do hackathon.
