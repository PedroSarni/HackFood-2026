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

## 2026-10-17 21:34 — estado.md fiel ao repo (testes, dash, voz)

**Prompt:** "TAREFA: deixar docs/estado.md fiel ao que existe agora. Edição mínima [...] troque "68 testes
passando" pela contagem real [...] Pedro: o dash saiu do rascunho [...] Breno [...] seletor real/demonstração
e diário de prompts [...] stub src/shared/voz.py [...] No B2, acrescente uma sub-linha [...]"

**Resposta:** pytest rodado: 137 passando. Atualizados "Última atualização", "No ar agora" (contagem), "Em
andamento" (dash do Pedro com Fabio e Breno, seletor real/demo aad024d, diário de prompts 6bbeb88, stub voz.py
d22fa3d como "em preparação") e a sub-linha do B2. Nada marcado [x]. O claim do Breno já está `done`.

## 2026-10-17 22:10 — bug: "Olá" virava complemento do endereço

**Prompt:** "BUG: na fase 'complemento', "Olá" é salvo como complemento do endereço (ficou "Rua X, 593, Olá,
Centro"). A fase 'bairro' tem o mesmo risco. [...] mudança mínima, mesmo padrão do d0b0c3c [...]"

**Resposta:** No complemento e no bairro, saudação e "quero fazer um novo pedido" não salvam nada: o bot repete a
pergunta da etapa (com "Não tem" no complemento). O commit do Fabio das 22h02 já mandava o resto pro Gemini,
mas o "Olá" escapava. 4 testes novos (230 passando). Pendente: "menu", "voltar" e "cancelar" digitados no
complemento ainda viram complemento.

## 2026-10-17 22:16 — bug: "cancelar"/"menu" viravam complemento ou bairro

**Prompt:** "BUG: nas fases 'complemento' e 'bairro', comandos como "cancelar", "menu", "voltar", "ajuda", "sair"
e "apagar meus dados" são salvos como complemento/bairro do endereço. [...] chame self.intencao(r) e retorne,
exatamente como o ramo 'endereco' faz."

**Resposta:** Nas fases complemento e bairro, os 5 comandos (inicio, cancelar, ajuda, sair, apagar_dados) agora
saem da etapa pelo `intencao`, como no endereço; "oi", "não tem" e texto livre seguem iguais. 4 testes novos
(234 passando); o do "apto 12" já existia desde 59d4abe e foi reaproveitado.

## 2026-10-17 22:40 — follow-up de 3 min pra quem calou (pedido do Fabio)

**Prompt:** "PEDIDO DO FABIO (dono do bot): "em 3 minutos, se a pessoa não responder mais, o bot manda um
follow-up". SE src/app.py FOR ARQUIVO PROTEGIDO ou estiver em claim ativo de outra pessoa: faça só a parte que
não precisa dele, pare e me diga exatamente o que falta [...]"

**Resposta:** `src/app.py` está no claim ativo do Fabio (`bot-ifood-agent`), então ficou de fora. Feito o lado do
bot: `FOLLOWUP_SEG = 180`, `Bot.marca_followup()` e `Bot.followup(wa_id, marca)` em fluxo.py, texto `AINDA_AI`,
6 testes (241 passando). Falta o Fabio criar a função Modal `followup` e o disparo no fim da `rodada` (trecho
pronto no chat). Sem deploy.

## 2026-10-17 22:55 — bug: "cancelar pedido" era buscado como produto

**Prompt:** "BUG: "cancelar pedido" não é reconhecido como comando e o bot procura "cancelar pedido" como produto
("Não achei cancelar pedido perto de você"). [...] acrescentar em COMANDOS, mapeando para 'cancelar', as frases
[...]"

**Resposta:** 6 frases novas no `COMANDOS` ('cancelar pedido', 'cancelar o pedido', 'cancelar compra',
'cancelar a compra', 'quero cancelar', 'desistir'), sem mexer nas outras. 10 testes novos (273 passando),
incluindo um que exige que "cancelar pedido" seja resolvido sem chamar o Gemini.

## 2026-10-17 23:14 — protocolo de quem cala: follow-up aos 3 min e carrinho esquecido aos 5

**Prompt:** "O Fabio (dono do claim bot-ifood-agent) pediu estas duas coisas ao Davi e liberou mexer no back. [...]
PROTOCOLO (decisão do Fabio): pessoa calada. Aos 3 min (180 s) o bot manda UM follow-up. Aos 5 min (300 s), se
continuar calada e houver itens no carrinho, o bot esquece o carrinho e avisa. PARTE A: ligar o follow-up no
src/app.py [...] PARTE B: carrinho abandonado (src/bot/fluxo.py) [...]"

**Resposta:** `src/app.py` não é protegido (só está no claim do Fabio, que liberou): função Modal `pessoa_calada`
(follow-up aos 180 s, abandono aos 300 s, mesma trava da rodada, envio pelo `contexto_producao` com o diário)
disparada no fim da `rodada`. Em fluxo.py: `ABANDONO_SEG`, `marca_abandono()`, `abandonar_carrinho()` e o
`marca_followup()` valendo na fase pedido com itens. 7 testes novos (344 passando). Sem deploy.

## 2026-10-17 23:15 — estado.md fiel ao repo depois da noite

**Prompt:** "TAREFA: deixar docs/estado.md fiel ao repo agora. Edição mínima. [...] contagem de testes pelo número
real do pytest [...] Sobre o modo (mock ou real): confirme em docs/prompts/fabio.md [...] acrescente [...] o que
entrou desde as 21h34 [...] marque B2 como [x] [...] Acrescente [...] H1 [...] H2 [...] H3 [...] H4 [...]"

**Resposta:** 344 testes. Mock ligado desde ~21h25 porque o iFood real cai muito (o Fabio não disse "só pra
testes", então não escrevi "voltar ao modo da demo"). Deploy das 23h00 (bbfd811) já tem foto, kit, voz e os
fixes; fora dele só 99c2c31 (app.py do follow-up), que está commitado e não "em andamento". Pronto ganhou as
features da noite, dash/mascote saíram de Em andamento, B2 [x], H1–H4 acrescentados.

## 2026-10-18 01:00 — dash: uso do MCP e rastro dos agentes de IA

**Prompt:** "[...] FASE 1A — USO DO MCP (fazer primeiro; os dados já existem) [...] uma visão 'MCP': por tool,
número de chamadas, % do total, % de erro, latência média e máxima, quantas conversas usaram. Inclua as tools da
doc que nunca foram chamadas [...] Filtro por conversa e por período. Por conversa, a sequência das chamadas na
ordem. FASE 1B — RASTRO DOS AGENTES DE IA: [...] embrulho no mesmo estilo do espiar_mcp [...] evento tipo 'ia'
[...] Nunca texto livre da pessoa [...] aba 'Agentes' [...] FASE 2 — LIGA/DESLIGA (só depois da fase 1 no ar e
testada, e me pergunte antes de começar) [...] Cuidado com volume [...] Agregue no servidor [...] Não faça deploy
sem me perguntar."

**Resposta:** claim dash-agentes-mcp. Fase 1A: `resumo_mcp`/`indice_conversas` em painel.py, rota `/api/mcp`
no servidor local (agrega no servidor, em cache por recálculo: 31 KB pra 32 mil eventos da demo, em 44 ms) e
página "Uso do MCP" no dash. O que o espiar_mcp grava não mudou. Fase 1B: `espiar_ia`/`espiar_servico`
ligados em `contexto_producao` (agente reconhecido pelo prompt de sistema, sem tocar no fluxo), evento `ia`
só com contagens, rota `/api/agentes` e aba "Agentes". Seção 13.1 em como-funciona.md. Sem deploy; fase 2
espera o Davi.

## 2026-10-18 01:40 — "mudar" digitado e o "sim" ambíguo do resumo

**Prompt:** "BUG B1: na pergunta 'Como você quer pagar?' (fase 'pagamento'), 'Mudar' digitado recebe 'Essas
eram todas as opções que achei' [...] BUG B2: o resumo pode trazer duas perguntas juntas ('Quer café pra
acompanhar? [...]' e 'Posso fazer o pedido?'). Na fase 'confirmar', 'sim' digitado aperta o 1º botão e fecha o
pedido [...] 1. B1: acrescente em COMANDOS [...] 'mudar', 'alterar', 'mudar pedido', 'mudar o pedido' [...] 2.
B2: quando o resumo mostrado tiver a sugestão de acompanhamento, 'sim' ou 'não' DIGITADOS [...] o bot pergunta
de novo com 3 botões [...] Sem sugestão no resumo, o comportamento atual continua igual (há teste para o 'sim'
que confirma). [...] nenhum teste existente pode mudar sem me explicar."

**Resposta:** B1 feito: 4 frases em COMANDOS -> ação `mudar` (com itens abre o mudar(); sem carrinho repete a
pergunta da etapa; no endereço/complemento/bairro escapa da etapa em vez de virar complemento). B2 parado: o
resumo dos testes existentes já tem sugestão (manteiga), então test_sim_digitado_no_resumo_confirma e dois de
voz (sim falado no resumo) mudariam; esperando a decisão do Davi. Sem deploy.

## 2026-10-18 02:00 — B2: "sim" no resumo com sugestão pergunta de novo

**Prompt:** "Decisão B2: pode mudar esses 3 testes. Eles garantem justamente o comportamento arriscado: 'sim'
digitado ou falado fecha o pedido mesmo quando o resumo também pergunta do acompanhamento. Atualize cada um pro
novo comportamento (re-pergunta com 3 botões; o pedido só fecha no toque em 'Fazer pedido assim') e me explique
em uma linha por que cada um mudou. Sem sugestão no resumo, 'sim' continua confirmando [...]"

**Resposta:** resumo com sugestão: "sim"/"não" (digitado ou falado) na fase confirmar re-pergunta com
"✅ Fazer pedido assim", "➕ Colocar <sugestão>" e "✏️ Mudar"; o "Colocar" põe 1 unidade da mesma loja e
volta pro resumo. Sem sugestão, nada muda. 3 testes atualizados (o "sim" deles confirmava com sugestão na tela),
6 novos, 418 passando. Sem deploy.

## 2026-10-18 02:15 — fase 2 do dash cancelada, claim dash-agentes-mcp concluído

**Prompt:** "Fase 2: não precisa. O Fabio entregou o dash-agents-control (liga/desliga, escolha de modelo,
crachá), que cobre isso. Marque o claim dash-agentes-mcp como done, sem criar nada novo. Não toque em
src/agentes/ nem em telemetria.js. Sem deploy. Registre isto em docs/prompts/davi.md."

**Resposta:** claim dash-agentes-mcp como done, com a fase 2 anotada como cancelada (coberta pelo
dash-agents-control do Fabio). Nenhum código tocado, sem deploy.

## 2026-10-18 02:30 — B4: aviso de botão antigo empilhava

**Prompt:** "BUG B4 em src/bot/fluxo.py, repetir_pergunta (~linha 467): o aviso 'Esse botão é de uma conversa
antiga' empilha a cada toque. [...] Correção mínima: depois de perguntar(), restaurar em u['pergunta'] o
'texto' original [...] Teste: chamar repetir_pergunta(T.BOTAO_VELHO) 3 vezes seguidas e conferir que a última
mensagem tem o aviso UMA vez. Não mexa em mais nada. [...] sem deploy [...]"

**Resposta:** repetir_pergunta restaura o texto original da pergunta depois de reenviar. Teste novo (3 toques
em botão velho no resumo, aviso 1 vez, pergunta intacta) falha sem a correção. 428 passando. Sem deploy.

## 2026-10-18 02:20 — estado.md fiel ao repo depois da madrugada

**Prompt:** "TAREFA: deixar docs/estado.md fiel ao repo agora. Edição mínima [...] 1. Cabeçalho [...] 2. 'Pronto':
acrescente, com o hash [...] o que entrou desde 23h15 [...] 3. 'No ar agora': corrija a linha do último deploy e
do modo [...] 4. 'Em andamento' [...] 5. Lista do projeto: não apague nada. Marque [x] [...] H2 [...] B1 e B2.
'Pendências da noite': H5 B3, H6 B4, H7 M2, H8 C1, H9 O2, H10 O1/M1/V1, H11 U1/U3/U4/U5, H12 QA [...] Sem deploy."

**Resposta:** estado.md atualizado (428 testes, mock ligado às ~02h00, deploys de ~01h31 e ~02h30, H2 e H6 [x], H5 a
H12 acrescentados). Divergências com o repo: B1/B2 da lista são outros itens (ranking e decisão de grupo/áudio), então
não marquei; os bugs B1/B2/B4 estão em "Pronto". B2 e B4 sem deploy comprovado.

## 2026-10-18 05:10 — varredura de lixo e docs alinhados ao que foi provado

**Prompts:**
- "Faça uma varredura de LIXO: só o que realmente sobrou para trás. Se não achar, diga 'nada encontrado' e pare.
  [...] FASE 1: SÓ LISTAR [...] 1. Arquivos rastreados que não deveriam estar no git [...] 7. Segredos ou dados
  pessoais [...] Mostre a lista numerada no chat e PARE. [...] FASE 2: só depois da minha resposta [...]"
- "Fase 2, aprovado só isto (nada foi aprovado para apagar): itens 6, 7 e 11 [...] Item 6: em src/README.md,
  corrija só o cabeçalho e a tabela de status [...] Cite scripts/modo.py ao lado de IFOOD_MOCK=1, também em
  docs/como-funciona.md:397 [...] Item 7: em docs/estado.md, ajuste 'Em andamento' [...] e acrescente as entregas
  das 02h20 em diante (dash-ai-insights, analista) [...] Item 11: remova a linha de docs/prompts/fabio.md:208 com o
  endereço residencial. Não reescreva o histórico do git. [...] Um commit: 'docs: alinha README e estado ao que foi
  provado' [...]"

**Resposta:** Varredura listou 11 itens no chat (sem arquivo rastreado indevido, sem chave nem token no repo nem no
histórico; CPFs e telefones só de exemplo). Nada apagado. Aplicados só os itens 6, 7 e 11: status do src/README.md e
modo demo com `scripts/modo.py`, 2º agente movido pra "Pronto" e Sofia/insights (9626e97, 054d7d2) no estado.md, linha
do print com endereço removida do fabio.md (continua no histórico do git). 440 passando. Sem deploy.

## 2026-10-18 05:40 — lembrete dizia "o preço mudou" só por causa da entrega

**Prompt:** "Bug de dinheiro no lembrete da recorrência (src/bot/fluxo.py e src/bot/recorrencia.py). Corrija SÓ isto:
Sintoma: o lembrete mostra 'Da última vez: R$ 24,95' (SUBTOTAL, sem entrega). Quando a pessoa toca 'Sim, pode
pedir', o total vem R$ 29,94 (24,95 + entrega 4,99) e o bot avisa 'O preço mudou desde a última vez', mas o preço
dos itens NÃO mudou. [...] Compare grandezas iguais [...] 'O preço mudou' só aparece se o valor realmente mudou.
Teste 1: itens iguais + entrega de R$ 4,99 → NÃO aparece 'preço mudou'. Teste 2: preço dos itens sobe → aparece.
[...] NÃO mexa na Lia nem em src/agentes/ [...]"

**Resposta:** O automático montado sem pedido (`_salvar_modelo`) guardava o subtotal no campo `total`, e o "sim" do
lembrete comparava isso com o total com entrega. Agora o modelo guarda `subtotal`; `preco_da_ultima_vez` (recorrencia.py)
diz o que comparar (total com total se já se sabe, senão subtotal com subtotal, inclusive em lembrete antigo); o
lembrete mostra "Itens: R$ X + entrega" até o 1º pedido e, depois dele, "Da última vez" com o total pago. 2 testes
novos (o 1º falha sem a correção), nenhum existente mudou, 462 passando. Sem deploy.

## 2026-10-18 06:10 — cinco acertos de texto (U6, U5, U25, U28, U22)

**Prompt:** "Cinco acertos de texto/formatação no bot (src/bot/fluxo.py, src/bot/textos.py). Faça SÓ estes, nesta
ordem, um commit por item: A. U6: itens iguais em linhas separadas [...] Some pelo mesmo produto: '5x Leite
integral' [...] B. U5: quando a lista lida de foto/áudio ('Anotei sua lista:') tiver quantidade guardada, mostre [...]
C. U25: o lembrete da recorrência diz 'nessa forma de pagamento' sem dizer qual [...] D. U28: ao tocar 'Hoje não' [...]
Diga quando [...] E. U22: a recusa de papo fora do assunto vem colada em 'Tudo bem, cancelei. Nada foi comprado.'
mesmo sem pedido em andamento [...] Teste automático para A, B, D e E [...]"

**Resposta:** 5 commits. A: `somar_iguais`/`lista_itens` (textos.py) no resumo, no "Combinado!" e no lembrete; o
carrinho continua com as linhas. B: "Anotei sua lista" mostra "2x leite" quando há `quantidade` (não há campo de
unidade, então "1 kg" só aparece se já vier no termo). C: "pagando com *PIX*", com a forma do lembrete ou a preferida.
D: "Te chamo de novo na semana que vem/amanhã/no mês que vem". E: o aviso do menu ("cancelei") ficava guardado como
pergunta e voltava em toda repetição; agora vale uma vez só. 8 testes novos, nenhum existente mudou. Sem deploy.

## 2026-10-18 06:40 — sugestões validadas no código e foto sem relação (U13, U23, U8)

**Prompts:**
- "Três acertos nas sugestões. ANTES: git pull e git log -5 -- src/agentes/ (Pedro/Breno podem estar editando
  agentes; se houver commit de hoje na Duda, me avise e pare). A. U13: o resumo sugere 'Quer refrigerante pra
  acompanhar?' mesmo com Guaraná 2L no pedido [...] B. U23: o bot sugeriu 'pãozinho pra acompanhar o café' com leite
  no carrinho. A frase só pode citar itens que realmente estão no carrinho. C. U8: foto sem relação [...] o estado
  volta ao menu e sem esses restos. Princípio mantido: o agente só PROPÕE (JSON), o código decide e valida [...]"
- "Sim, siga com A, B e C. [...] Pode editar src/bot/combina.py, src/bot/fluxo.py, src/bot/foto.py e
  src/bot/textos.py [...] NÃO edite src/agentes/ nem src/bot/relevancia.py [...]"

**Resposta:** Parei primeiro: a Duda (relevancia.py) tinha commits de hoje do Fabio (e31eedd 01:40, db33ba9 00:05).
Liberado, sem tocar na Duda: `ja_tem` (combina.py) barra categoria que o carrinho já tem (Guaraná = refrigerante),
tanto no `complementos` quanto no que a IA propõe no sugerir; `so_o_produto` tira a justificativa do termo da IA
("pra acompanhar o café"), e a frase fica a do código, que não cita nada. Foto sem relação no meio dos cards volta
pro menu sem os cards na memória. 1 teste existente mudou (afirmava `fase == 'escolhendo'` depois da foto sem
relação, o oposto do pedido). 3 testes novos, 473 passando. Sem deploy.

## 2026-10-18 09:00 — CPF exigido no item (MERCH-007) perdia o item e pedia o CPF de novo

**Prompt:** "Bug no fluxo do CPF com MCP real (src/bot/fluxo.py, em volta de receber_cpf, sem_cpf e do tratamento de
erro MERCH-007 [...]). Sintoma (QA em loja real, Nissei Mercado, que exige CPF): a pessoa toca 'Quero esse' em um leite
→ o bot responde 'Essa loja exige CPF na nota... escreva seu CPF' → a pessoa manda o CPF → o bot diz 'Seu pedido ainda
está vazio' e perdeu o item. Na 2ª tentativa (mesmo leite) pediu o CPF DE NOVO. [...] 1. Reproduza com o mock [...]
2. Depois que o CPF válido chegar, RETOMAR o que a pessoa estava fazendo [...] 3. Guardar o CPF informado na sessão
[...] 4. Se não conseguir retomar, dizer isso e voltar ao menu, nunca 'pedido vazio'. [...] (o Fabio mexe em fluxo.py no
claim bot-kit-consistency: se houver conflito, pare e me avise) [...]"

**Resposta:** Sem conflito com o claim do Fabio. Reproduzido no mock (createCart/addItemToCart com MERCH-007). Agora o
erro guarda a ação da vez (`retomar_cpf`) e, com o CPF, refaz o item escolhido; no fechamento segue pro resumo como
antes (nunca envia direto). O CPF dado fica em `u['cpf']`; se a loja recusa de novo com o CPF já em mãos, diz que não
deu e volta pro menu, sem pedir de novo. Sem nada pra retomar nem carrinho: "Anotei seu CPF" + menu. 3 testes novos
(falham sem a correção), nenhum existente mudou. Sem deploy.

## 2026-10-18 09:20 — interruptor cfg:cutucar pra apresentação ao vivo

**Prompt:** "Adicione um interruptor para desligar o follow-up e o abandono sem mudar os tempos. [...] 1. Crie a
configuração cfg:cutucar no mesmo armazém e no mesmo estilo do modo palco (cfg:reserva_auto): ligada por padrão;
desligada, o bot não agenda pessoa_calada nem cutuca nem abandona carrinho. 2. Adicione scripts/modo.py --cutucar
on|off, no mesmo formato do --palco. 3. Teste: com cutucar off, marca_followup/marca_abandono não disparam nada.
4. NÃO mude FOLLOW_UP_SEG nem ABANDONO_SEG nem nenhum texto. [...]"

**Resposta:** `Bot._cutucar()` (fluxo.py) lê `cfg:cutucar` do armazém, ligado se não existir. Desligado:
`marca_followup`/`marca_abandono` devolvem None (o app.py não agenda `pessoa_calada`), e `followup`/`abandonar_carrinho`
já agendados não fazem nada. `scripts/modo.py --cutucar on|off` grava e mostra o estado. Tempos e textos iguais;
2 testes novos, 512 passando. Sem deploy (vale na próxima mensagem depois do deploy deste código).

## 2026-10-18 09:50 — revisão factual dos entregáveis D2 a D5

**Prompt:** "Coloquei 4 entregáveis do hackathon em docs/entregaveis/ (02-desenho-de-solucao.md,
03-racional-da-experiencia.md, 04-interface-visual.md, 05-documento-tecnico.md). Eles são o conteúdo final: NÃO crie
outros arquivos .md [...] Tarefa: revisar só a precisão factual contra o código atual da main [...] Confira cada
afirmação técnica: nomes de agentes e papéis, fila de modelos, tools do MCP usadas (o texto diz 19 de 23),
freio/disjuntor/ponte, modo palco, tempos da rajada, textos citados entre aspas, botões, contagem de testes [...],
menu do dash [...] Corrija no próprio arquivo só o que estiver errado ou desatualizado, com a menor mudança possível
[...] Commit único 'docs(entregaveis): D2, D3, D4 e D5' [...]"

**Resposta:** Conferi contra o código. Batem: agentes e crachás, fila (Claude > Gemini > OpenRouter), 19 de 23 tools,
freio 0,35 s, disjuntor 300 s, ponte, palco 10 s/1 tentativa, rajada (0,6/4/2,5/9 s), textos e botões, menu do dash,
keys com 4 últimos. Corrigido: testes (510/512 → 521), confirmação ("sim" repetido → um "sim" no resumo, desde o
9e861a3 do Fabio; "já pode passar no pix" fecha direto), CPF da nota pedido se não estiver na conta, papel e plano B
da Duda, foto sem relação nos cards, "Anotei sua lista" numerado, botões do resumo, kit ainda em andamento, "dinheiro
em centavos" e "diário sem texto". Não confirmado: "MCP real devolve até 10 ofertas", "leite falado". Sem deploy.
