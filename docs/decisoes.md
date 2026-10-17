# Diário de decisões

> Formato: - [HH:MM] Decisão — motivo — quem decidiu. Mais novo no topo.
> Registrar na hora, não depois.

- [17h37] Login do iFood só pela web (id.ifood.com.br/authorize), sem o OneLink do app: é o recomendado pro nosso caso, o fluxo do app exige redirect por Universal/App Link — Fabio
- [17h00] Pagamento só PIX e vales: cartão exige cardTokenId e o listPaymentMethods sempre devolve null (não há API de tokenização) — Fabio (registrado por Davi)
- [16h55] Ideia fechada: agente de compras no WhatsApp pra quem não gosta ou não sabe usar app (idosos e pouca familiaridade digital). Botões sempre, 3 opções por vez com "Mais opções", entende texto, áudio e foto, aguenta várias mensagens seguidas e repete a compra da semana com 1 toque. Diferenciais: acessibilidade e recorrência — time (registrado por Davi)
- [16h55] Confirmar compra nunca vem da IA: submitOrder só depois do toque em "Confirmar pedido" — evita pedido sem consentimento e pedido duplicado — Fabio (registrado por Davi)
- [16h55] A IA só interpreta texto, áudio e foto; o código conduz cada etapa e chama o MCP — a IA entende, o código garante — Fabio (registrado por Davi)
- [16h40] Bot roda em modo demo com MCP falso até as credenciais reais funcionarem — ninguém fica parado esperando — Fabio (registrado por Davi)
- [16h35] Gemini lite na frente e o modelo maior de reserva: respostas em ~1 s em vez de 10 s — Fabio (registrado por Davi)
- [15h50] Documentos de contexto ficam no repo em docs/, o Drive é só rascunho — agentes só leem o repo — Davi
