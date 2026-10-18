# Contexto do evento — AiFood 2026

> Fonte de verdade sobre o que o evento, os mentores e o iFood disseram.
> Agentes: leiam antes de decidir algo de produto ou de MCP.
> Fato confirmado fica nas seções 1 a 4. Fala solta de mentor vai no log (seção 5).
> Resumo completo do MCP: "regras da api/ifood-mcp-developer-portal.json".

## 1. Regras do evento
- Evento: Hackathon SEMCOMP x iFood, "Vendendo com Agentes"
- Local: ONOVOLAB, São Carlos (dentro da programação do SEMCOMP 29)
- Duração: ~30h, de sáb 17/10 12h30 até dom 18/10 17h
- 80 participantes, 20 grupos de 4
- Missão: agente de IA que opera o MCP do iFood para fazer pedidos, da escolha do restaurante ao fechamento do carrinho
- Tema livre, sem restrição temática (fala de mentor, não está no site)
- Uso de LLMs permitido, com acesso próprio ao modelo
- Mentoria: ~10 avaliadores e mentores do iFood, mais professores e doutorandos da USP
- Alojamento oferecido, com jantar e café da manhã
- Pitch: 5 a 8 min + 3 min de perguntas (anotação do time, não está no site)
- Os pitches são apresentados para todos os participantes antes do resultado
- Prêmio: R$ 4.000 (1º), R$ 2.000 (2º), R$ 1.000 (3º). Nossa anotação diz "iFood Card": confirmar com a organização

### Agenda
- Sáb 12h30: credenciamento, abertura e início
- Sáb 13h a dom 12h30: desenvolvimento contínuo
- Dom 12h30: fim do desenvolvimento e submissão
- Dom 13h a 16h: pitches finais
- Dom 16h30: consolidação dos resultados
- Dom 17h: resultados, premiação e encerramento
- Meta interna: tudo travado às 11h30 de domingo

## 2. Critérios de avaliação
A banca avalia os 20 grupos por 5 pilares. O site não informa pesos.
- Visão e Originalidade: solução original, uso criativo do agente
- Arquitetura e Engenharia: qualidade do código, uso correto do MCP, robustez do agente
- Design e Experiência: fluidez da interação, clareza pra quem pede
- Impacto: resolve problema real e é viável na prática
- Comunicação e Pitch: demo, storytelling, respostas às perguntas

## 3. Entregáveis (todos obrigatórios, até 12h30 de domingo)
- 01 Proposta de Negócio: problema e proposta de valor
- 02 Desenho de Solução: fluxo geral
- 03 Racional da Experiência: decisões de UX
- 04 Interface Visual: telas, protótipo ou interface
- 05 Documento Técnico Resumido: arquitetura, uso do MCP, decisões técnicas
- 06 Feedback sobre os MCPs: dores reais ao usar o MCP do iFood. A organização destaca este como insumo direto pro time que mantém a ferramenta
- Status: nenhum começado

## 4. MCP do iFood: fatos
Detalhes no JSON do repo. Aqui só o que importa no dia a dia.
- Gateway único: https://consumer-mcp.ifood.com.br/marketplace (4 domínios, 23 tools no servidor: falta listItemTaxonomy, que só existe na doc)
- O llms.txt cita outros hosts (api-mcp.ifood.com, dev-api-mcp.ifood.com, auth.ifood.com.br, dev-auth.ifood.com.br). Usar o gateway acima até confirmar
- Auth: OAuth 2.1 com PKCE. authorize em https://id.ifood.com.br/authorize, token em https://id.ifood.com.br/token
- Access token dura ~1h, refresh token ~30 dias e rotaciona. client_secret só no backend
- Nosso agente: "AiFood Agent", aprovado em menos de 1h (criado ~15h10, aprovado antes das 15h58)
  - Redirect cadastrado: http://localhost:8080/callback
  - Escopos: user, discovery e cart (via "Criação de pedidos")
  - Client Secret é gerado no portal após a aprovação e aparece uma única vez (ver o problema do /token na seção 8)
- Contas de teste: até 10, e-mail @test.ifood.com.br, telefone falso, OTP aparece no portal, apagadas após 15 dias
- Sem pedido real em teste. Pedido pago em teste não é reembolsado: não usar PIX real
- submitOrder exige userConsent. O agente nunca confirma sozinho
- createCart aceita orderId para refazer pedido antigo
- trackOrder devolve agentHints (quando checar de novo e quando parar). Seguir isso, sem polling fixo
- Cart: o campo options é sempre obrigatório, mesmo vazio ([])
- paymentMethodId é UUID, não a string "PIX"
- 2º agente: "Compras pelo WhatsApp" (conta do Fabio, 17/10 ~16h05), em análise. Redirects: o backend
  publicado (`.../ifood/callback` no Modal) e `http://localhost:8080/callback`. Mesmos 3 escopos
- Limitações descobertas ao testar (17/10, sem credencial: endpoints públicos e mock fiel à doc):
  - Discovery não aceita addressId: `userLocation` é sempre `{latitude, longitude}` (vem do `coordinates` do endereço)
  - Cartão: `setCartPayment` exige `cardTokenId`. O `listPaymentMethods` devolve PIX e um cartão de teste com
    `cardTokenId` (não null) [testado, 17/10]. Não há API de tokenização. A decisão de só PIX e vales segue (docs/decisoes.md).
    Não existe "pagar na entrega"
  - `submitOrder` devolve só `orderId`: nenhum código PIX copia-e-cola/QR em nenhuma tool
  - Entrega agendada exige `selectedTimeSlotId`; os timeslots têm `timeslotId` em mercado, e a chave vem omitida em
    restaurante [testado, 17/10]
  - Opções do item → carrinho: o mapeamento `optionGroupId/optionId` → `options/customizations` não está claro.
    O bot tenta o modo A e cai pro B sozinho se o iFood recusar

## 5. Log de falas (mais novo no topo)
Formato: - [HH:MM] Quem falou: o que disse -> impacto pra gente
- (vazio)

## 6. Decisões do time
Ver docs/decisoes.md.

## 7. Pendências e dúvidas
- [x] Mentor: quanto tempo demora a aprovação do agente? Resposta: menos de 1h (agente do Davi)
- [ ] Mentor: dá pra cadastrar um redirect de backend publicado, além de localhost:8080?
- [ ] Mentor: que tipo de agente externo o iFood imagina usando esse MCP?
- [ ] Confirmar se o prêmio é em dinheiro ou iFood Card
- [x] Testar quando as credenciais saírem: trackOrder funciona com os escopos liberados? (a doc pede mcp.orders.read, que não aparece em nenhum card do portal). Resposta: funciona. trackOrder devolve ORDER_NOT_FOUND, não erro de acesso [testado]
- [ ] Submissão: provável repo do GitHub, instruções domingo de manhã [assumido, confirmar]

## 8. Bugs e inconsistências do MCP (alimenta o entregável 06)
Marcar cada item como [só na doc] ou [testado].
- [14h40-15h03] Portal de cadastro fora do ar. Mentores avisaram que estavam resolvendo [testado]
- [16h30] Agente "AiFood Agent" (Davi): POST /token devolve invalid_client com o secret recém gerado (post, Basic e sem secret). RESOLVIDO: o secret estava errado, não era problema do iFood [testado]
- [17h05] RESOLVIDO para o agente "Compras pelo WhatsApp": com o client_id GbC9J7... + o secret dele, POST /token devolve invalid_grant (não invalid_client) usando um code falso — ou seja, a autenticação do cliente PASSA, tanto por client_secret_post quanto por Basic. Logo, o invalid_client do item acima era específico do agente/secret do Davi, NÃO um bug geral do iFood. O OAuth do nosso agente está completo (authorize + escopos mcp.* + redirect + /token). Falta só um login humano real. [testado]
- Dica pro invalid_client: conferir se o secret é do MESMO agente do client_id (cada agente tem o seu), e gerar de novo no portal se tiver dúvida (some ao recarregar a página) [testado]
- Hosts diferentes entre os guias (consumer-mcp.ifood.com.br) e o llms.txt (api-mcp.ifood.com / dev-api-mcp.ifood.com). Os do llms.txt nem resolvem no DNS; o consumer-mcp responde 401 com `resource_metadata` [testado]
- Hosts de auth diferentes (id.ifood.com.br vs auth.ifood.com.br / dev-auth.ifood.com.br). Só o id.ifood.com.br tem OIDC de verdade (authorize, token, revoke, PKCE S256); os outros devolvem 302/vazio [testado]
- O 401 do gateway manda o cliente "re-register automatically", mas não existe registration_endpoint (credencial só pelo portal) [testado]
- llms.txt usa escopos `user:read`/`cart:write` e `code_challenge_method=pkce`; as páginas usam `mcp.*` e `S256` [só na doc]
- Doc do MCP não mostra initialize, Mcp-Session-Id nem protocolVersion: tudo deduzido da spec do MCP [só na doc]
- Nomes de escopo diferentes (mcp.cart.* vs cart:write) [só na doc]
- Formatos de erro: a doc fala em 3 (User/Discovery, Cart e Order Tracking); na prática são 4 em JSON + 3 em texto cru (exceção Java, NPE Kotlin, chave i18n) [testado]
- Erros do Cart não trazem retryable, os outros trazem [testado]
- ORDER_NOT_FOUND vem com retryable=false (a hipótese anterior, de que não batia com a doc, era falsa) [testado]
- listPaymentMethods devolve PIX e cartão de teste; paymentMethodId é UUID (não null, não "PIX") [testado]
- createCart já exige o 1º item: não existe carrinho vazio [testado]
- addItemToCart sem options estoura exceção (a doc está certa, o schema está errado); createCart aceita sem options; options=[] funciona nos dois [testado]
- cartItemId muda a cada escrita no carrinho (add/update/remove/setDelivery/setPayment/setVoucher) [testado]
- getCart de carrinho inexistente devolve GEN-123 "try again", sem retryable [testado]
- createAddress com endereço falso devolve um endereço nos EUA com confiança SINGLE [testado]
- Facets do browseOffers contam só a página atual; listItemTaxonomy não existe no servidor [testado]
- getItem pode devolver 61 KB para um único item [testado]
- setVoucher com cupom não aplicável responde sucesso [testado]
- setCartDelivery aceita timeslot inválido e troca em silêncio [testado]
- totalAmount não fecha num carrinho de mercado (R$ 5,54 vs 9,38), origem não identificada [testado]
- benefitsTotalAmount é fixo e não bate com o total [testado]
- Não existe tool para listar pedidos [testado]
- Discovery só aceita lat/lng, nunca addressId. Timeslots existem em mercado (campo timeslotId na resposta, selectedTimeSlotId na entrada) e vêm omitidos em restaurante [testado]
- Doc do fluxo de User cita update/delete de endereço que não existem [só na doc]
- "Fluxo completo de pedido" na doc pula passos que o Cart exige [só na doc]
- Portal mostra só mcp.cart no card "Criação de pedidos"; a doc pede mcp.orders.read pra rastrear e esse escopo não aparece em nenhum card [testado no portal]
- llms.txt recomenda Pending Action pra agentes, mas contas de teste com telefone falso não conseguem testá-lo [só na doc]
- llms.txt aponta pra um canal de suporte interno (Slack) que participante externo não acessa [só na doc]
- Doc exige HTTPS no redirect, mas permite localhost sem HTTPS [só na doc]

## 9. Links
- Portal: https://mcp-developer.ifood.com.br
- Repo: https://github.com/PedroSarni/AiFood-2026
