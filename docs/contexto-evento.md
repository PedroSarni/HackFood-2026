# Contexto do evento — HackFood 2026

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
- Gateway único: https://consumer-mcp.ifood.com.br/marketplace (4 domínios, 24 tools)
- O llms.txt cita outros hosts (api-mcp.ifood.com, dev-api-mcp.ifood.com, auth.ifood.com.br, dev-auth.ifood.com.br). Usar o gateway acima até confirmar
- Auth: OAuth 2.1 com PKCE. authorize em https://id.ifood.com.br/authorize, token em https://id.ifood.com.br/token
- Access token dura ~1h, refresh token ~30 dias e rotaciona. client_secret só no backend
- Nosso agente: "HackFood Agent", status "em análise" (criado em 17/10 às ~15h)
  - Redirect cadastrado: http://localhost:8080/callback
  - Escopos: user, discovery e cart (via "Criação de pedidos")
  - Credenciais de teste só saem após aprovação
- Contas de teste: até 10, e-mail @test.ifood.com.br, telefone falso, OTP aparece no portal, apagadas após 15 dias
- Sem pedido real em teste. Pedido pago em teste não é reembolsado: não usar PIX real
- submitOrder exige userConsent. O agente nunca confirma sozinho
- createCart aceita orderId para refazer pedido antigo
- trackOrder devolve agentHints (quando checar de novo e quando parar). Seguir isso, sem polling fixo
- Cart: o campo options é sempre obrigatório, mesmo vazio ([])
- paymentMethodId é UUID, não a string "PIX"
- Limitações descobertas ao testar: (preencher)

## 5. Log de falas (mais novo no topo)
Formato: - [HH:MM] Quem falou: o que disse -> impacto pra gente
- (vazio)

## 6. Decisões do time
Ver docs/decisoes.md.

## 7. Pendências e dúvidas
- [ ] Mentor: quanto tempo demora a aprovação do agente?
- [ ] Mentor: dá pra cadastrar um redirect de backend publicado, além de localhost:8080?
- [ ] Mentor: que tipo de agente externo o iFood imagina usando esse MCP?
- [ ] Confirmar se o prêmio é em dinheiro ou iFood Card
- [ ] Testar quando as credenciais saírem: trackOrder funciona com os escopos liberados? (a doc pede mcp.orders.read, que não aparece em nenhum card do portal)

## 8. Bugs e inconsistências do MCP (alimenta o entregável 06)
Marcar cada item como [só na doc] ou [testado].
- [14h40-15h03] Portal de cadastro fora do ar. Mentores avisaram que estavam resolvendo [testado]
- Hosts diferentes entre os guias (consumer-mcp.ifood.com.br) e o llms.txt (api-mcp.ifood.com / dev-api-mcp.ifood.com) [só na doc]
- Hosts de auth diferentes (id.ifood.com.br vs auth.ifood.com.br / dev-auth.ifood.com.br) [só na doc]
- Nomes de escopo diferentes (mcp.cart.* vs cart:write) [só na doc]
- 3 formatos de erro diferentes: User/Discovery, Cart e Order Tracking [só na doc]
- Erros do Cart não trazem retryable, os outros trazem [só na doc]
- ORDER_NOT_FOUND: retryable não bate com o que a doc descreve [só na doc]
- Doc do fluxo de User cita update/delete de endereço que não existem [só na doc]
- "Fluxo completo de pedido" na doc pula passos que o Cart exige [só na doc]
- Portal mostra só mcp.cart no card "Criação de pedidos"; a doc pede mcp.orders.read pra rastrear e esse escopo não aparece em nenhum card [testado no portal]
- llms.txt recomenda Pending Action pra agentes, mas contas de teste com telefone falso não conseguem testá-lo [só na doc]
- llms.txt aponta pra um canal de suporte interno (Slack) que participante externo não acessa [só na doc]
- Doc exige HTTPS no redirect, mas permite localhost sem HTTPS [só na doc]

## 9. Links
- Portal: https://mcp-developer.ifood.com.br
- Repo: https://github.com/PedroSarni/HackFood-2026
