# Prompts do Davi

Cada prompt e um resumo do que o agente respondeu ou fez, pro time acompanhar (regra no `AGENTS.md` §8).
Segredos e dados pessoais aparecem como `[...]`. Começa em 17/10 ~18h40; os prompts de antes não foram registrados.
Os prompts desta sessão foram longos e colados: aqui vai o pedido condensado, com as palavras da pessoa.

## 2026-10-17 18:45 — corrigir docs desatualizados (whatsapp, src/README, claim do bot)

**Prompt:** "O Fabio autorizou corrigir docs desatualizados. Escopo: SÓ docs/whatsapp.md, src/README.md e
.coord/claims/bot-ifood-agent.md [...] corrija apenas o que o repo COMPROVA [...] O que não der pra comprovar,
NÃO mude: liste no fim."

**Resposta:** Webhook marcado como já virado pro deploy novo (`scripts/virar_webhook.py`), `mcp_fake` como pronto
no README e no claim, e os 3 arquivos entraram no claim `docs-vivos` (80f31d3, babe416, 94e6183, f91201e).
Ficou pro Fabio: status do cliente MCP com credencial real, fluxo/rastreio "em teste" e `META_APP_SECRET`.

## 2026-10-17 18:48 — QA real do MCP no contexto-evento

**Prompt:** "Escopo: SÓ docs/contexto-evento.md (§4, §7 e §8). [...] Fonte: o resumo abaixo (QA real do MCP,
conta de teste, 17/10). Use o formato [testado] e não invente nada além dele." [resumo do QA com ~20 achados]

**Resposta:** §4 com 23 tools no servidor, §7 com `mcp.orders.read` respondida e submissão [assumido], §8 com o
invalid_client resolvido e os achados do QA em [testado] (60583e2). Pendente: frases da §4 sobre cartão e timeslot.

## 2026-10-17 20:20 — estado e decisões depois do QA

**Prompts:**
- "Atualize em docs/estado.md, apenas o que o repo ou os commits provam: [C1, B3, C5, invalid_client fora do
  bloqueio, 2º agente aprovado, dashboard do Pedro, QA concluído]" + decisões de cupom e submissão.
- "decisoes.md: ACRESCENTE no topo [...] Correção de fato [listPaymentMethods]; contexto-evento.md §4: corrija a
  frase do listPaymentMethods e a de timeslots; estado.md: Rascunho do 06 (Davi): em andamento, fora do repo."

**Resposta:** estado.md, decisoes.md e contexto §4 atualizados (5897887, e23b17f, b629f47, f790a7a, c4d9bd2).
A decisão do cupom automático não entrou (o Davi não confirmou). Sem prova no repo: o horário 17h46 e o
`cardTokenId` do cartão de teste (só no resumo do QA).

## 2026-10-17 21:12 — bug: fase endereço prendia quem dizia "Olá"

**Prompt:** "BUG: na fase 'endereco', livre() manda QUALQUER texto para receber_endereco() [...] Se a pessoa
digita "Olá" ou "Quero fazer um novo pedido", cai em "Não achei esse endereço" e fica em loop, sem botões."

**Resposta:** Saudação, pedido de menu e texto sem cara de endereço não vão mais ao geocoder e recebem botões
Tentar de novo / Início; 2 falhas seguidas também mostram botões (d0b0c3c). 5 testes novos, 124 passando.
Pendente: "Tentar de novo" reenvia o mesmo endereço (sugerido "Cadastrar outro", decisão do Fabio).

## 2026-10-17 21:15 — bug: sessão nunca expirava

**Prompt:** "BUG: processar() faz u['ultima_msg'] = self.ctx.agora() mas ninguém compara com o valor anterior.
A pessoa some, volta horas depois e o bot continua na fase antiga [...]"

**Resposta:** Depois de 30 min parado em 9 fases de pergunta aberta, volta ao menu; login, endereços, histórico e
carrinho ficam; no resumo com carrinho só reapresenta o resumo (4797590). 5 testes novos, 129 passando.
Escolhas pra validar com o Fabio: botões não expiram, CPF depois de expirar é descartado, "sim" não confirma.

## 2026-10-17 21:18 — registrar os 2 bugs no estado e no diário de decisões

**Prompt:** "atualizar só docs/estado.md e docs/decisoes.md, com edição mínima e append-only no diário [...]"

**Resposta:** A3 ganhou a linha dos 2 bugs corrigidos e 6 entradas novas no diário (97c79bb, d7845ea). As entradas
foram no topo, porque o diário é "mais novo no topo", e não no fim como o prompt pedia.

## 2026-10-17 21:29 — registrar a sessão no diário de prompts

**Prompt:** "vc consegue registrar essas mudanças q fiz agora no diario de prompts?"

**Resposta:** Criado este arquivo com as entradas da sessão (de ~18h45 até agora).
