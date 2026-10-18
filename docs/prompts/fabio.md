# Prompts do Fabio

Cada prompt e um resumo do que o agente respondeu ou fez, pro time acompanhar (regra no `AGENTS.md` §8).
Segredos e dados pessoais aparecem como `[...]`. Começa em 17/10 ~20h; os prompts de antes não foram registrados.

## 2026-10-17 ~20h — key nova do Gemini e áudio pelo Scribe

**Prompt:** "a nova key do gemini: [key do Gemini] cadastre ela. use o scribe mesmo! pode criar a key no
eleven labs.io entao entrando no meu browser se nao me de o link pra eu ir la criar"

**Resposta:** Key validada com 1 chamada e cadastrada num secret novo, `hackathon-gemini`, só do HackFood
(o `llm-conversor` é compartilhado com o handwrite_bot e ficou intocado). Scribe confirmado (`scribe_v2`).
A key da ElevenLabs o agente não cria nem copia pelo navegador: mandou o link
https://elevenlabs.io/app/settings/api-keys pra criar e colar no chat. Código do Scribe pronto e testado (o áudio
vira texto e segue o caminho de uma mensagem escrita); fica desligado, com o Gemini ouvindo, até a key entrar.

## 2026-10-17 ~20h30 — "o Gemini não está traduzindo pro iFood"

**Prompt:** "corrija essa porra desse bug: [print do chat: o bot respondeu "Não achei *sla porra algo que
complete esse valor* no Nissei Mercado - 431"] O GEMINI NAO ESTA TRADUZINDO PRO IFOOD???"

**Resposta:** O log mostrou que às 20:27 o `gemini-3.1-flash-lite` deu 503 (sobrecarga do Google) e o
reserva `gemini-3.8-flash` deu 429 (cota da key velha). Sem Gemini, o plano B buscou a frase inteira no
iFood. No ar: key nova, `gemini-3.5-flash-lite` como 2º da fila (respondeu em 1,3 s enquanto os outros
davam 503) e o plano B só busca texto de até 4 palavras. Teste novo cobrindo isso.

## 2026-10-17 ~20h35 — sugerir algo pra completar o pedido mínimo

**Prompt:** "nesse caso aí por ultimo ele deveria sugerir algo parecido de interesse do cliente pra
completar o valor"

**Resposta:** No ar: botão "💡 Me sugere algo" no aviso de pedido mínimo e no "O que mais você quer?".
Frases como "me sugere" e "algo que complete esse valor" viram sugestão sem depender do Gemini. Na loja
do carrinho, sugere 1º o que a pessoa costuma comprar (histórico), depois o que combina (Gemini), depois
algo parecido com o carrinho; quem fecha o mínimo aparece primeiro, e pedir de novo traz outra coisa.
4 testes novos (115 passando).

## 2026-10-17 20:53 — registrar os prompts

**Prompt:** "preciso que pra cada novo prompt que eu faça salve em um .md e um breve resumo do que deu
como resposta, sabe? pros outros acompanharem os prompts. coloque isso como regra" / "a partir de agr claro"

**Resposta:** Regra nova no `AGENTS.md` (§8, um arquivo por pessoa em `docs/prompts/`, nunca com segredo)
e este arquivo, começando pelos prompts de agora há pouco.

## 2026-10-17 ~21h — main quebrado pelo commit do painel

**Prompt:** (resposta à pergunta do agente) "Commita já assim"

**Resposta:** Outra sessão, na mesma pasta, commitou o painel (`73a8650`) levando o import do Scribe no
`contexto.py` sem o `scribe.py`, e o main no GitHub dava ImportError. O commit `284ec28` sobe só o
`scribe.py` (conferido num worktree: HEAD quebrado, HEAD + arquivo = 119 testes ok). O resto espera o
`git config user.name` deixar de ser um e-mail.

## 2026-10-17 ~21h05 — callback do OAuth (mensagens da organização)

**Prompt:** "[print do grupo: com callback em localhost o iFood não confere a porta, só o path; editar a
callback URI está bloqueado no portal, a organização ajusta se precisar] tem essas duas msgs novas aqui,
impactam em algo? só pra dar uma olhada"

**Resposta:** Não impacta: o callback do bot é a URL pública do Modal (`.../ifood/callback`), já cadastrada
e com login real funcionando; a regra da porta é pra quem loga por ferramenta local. Cuidado indireto: com
a edição bloqueada, nada de mudar o nome do app, o label ou a região no Modal, senão a URL muda e o login
do iFood quebra.

## 2026-10-17 20:40 — dash do Pedro funcional e em tempo real

**Prompt:** olha: "D:\Users\fabio\Desktop\hackathon" entre ai e vamos começar a fazer uma nova feature, a feature do dash, veja o front do dash exemplo e de vida pra ele, faça ser funcional localmente atualizado em tempo real

**Resposta:** Claim `dash-live-data`. O bot ganhou um diário de eventos (`src/shared/painel.py`: entrada, saída e chamadas ao MCP no modal.Dict `hackfood-painel`, CPF mascarado), um servidor local com SSE (`src/painel/servidor.py`) e um simulador que roda o Bot de verdade com os fakes. O `Frontend/Rascunho_Dash` passou a ler isso ao vivo. Commits 73a8650, bf1d0c2. Pendente: `modal deploy` pra o bot em produção começar a gravar. Achado: carrinho aberto não expira e trava a busca em outra loja.

## 2026-10-17 21:15 — alternar dados reais e demonstração na apresentação

**Prompt:** faça com que eu possa exibir dados mockados (muitos dados) ou simplesmente os dados reais, entende? pra mostrar na apresentação

**Resposta:** O servidor local serve as duas fontes juntas e o seletor no topo do dash troca na hora entre Dados reais, Demonstração (~800 conversas simuladas em 30 dias, ao vivo, em cache) e Base estática; também dá pra abrir com `?fonte=demo|real`. Commit aad024d. Pendente o mesmo deploy.

## 2026-10-17 21:35 — tirar a base estática do dash

**Prompt:** apague o estatico do pedro

**Resposta:** Saiu a "Base estática" do dash: fixtures de `data.js`, o roteiro "Simular compra", o CSV e o PDF de exemplo. Ficaram só Dados reais e Demonstração; o cartão "Explorar demonstração" agora abre a Demonstração. A base fixa sobrevive só em `Frontend/Rascunho_Dash/tests/fixtures.js`, pros testes (19 passando). `app.js` (versão antiga em JS puro, não usada pelo `index.html`) não foi mexido.

## 2026-10-17 ~21h20 — URL fixa em lugar crucial, refri pro lanche, nome do git

**Prompt:** "[citou o aviso: não dá pra mudar nome do app, label ou região no Modal, senão o login do iFood
quebra] salve essa informacoes em algum lugar muito crucial. sobre: [citou o 'completar o valor'] pode ser um
refri pra um sanduiche ou sempre algo assim, sabe. [citou 'Falta o seu nome no git'] ignore isso"

**Resposta:** URL fixa registrada no `AGENTS.md` §0.0 (todo agente lê ao chegar), num comentário em cima do
`APP` no `src/app.py` e no `como-funciona.md` §4. A sugestão do mínimo passou a oferecer 1º o que acompanha
(`src/bot/combina.py`: refri pro lanche, manteiga pro pão; nunca remédio nem álcool), depois o que a pessoa
costuma comprar, depois algo parecido. Commits com a identidade atual: `90ca03e`, `123d7c7`, `6bbeb88`.

## 2026-10-17 ~21h25 — key da ElevenLabs e deploy liberado

**Prompt:** "chave do elevenlabs [key da ElevenLabs]" / "ao finalizar pode fazer deploy"

**Resposta:** Key no secret `hackathon-elevenlabs`. Scribe validado com 1 chamada: um áudio em pt-BR gerado
pela voz do próprio Windows ("Oi, eu quero dois pacotes de pão francês e um litro de leite, por favor") voltou
transcrito certinho. Deploy no fim da rodada.

## 2026-10-17 ~21h30 — mock no lugar do iFood, MUITO CONSISTENTE

**Prompt:** "vamos deixar um mock ligado no lugar do mcp do ifood de fato, ok? deixe um mock bem consistente
baseado no que ja conversamos aqui, ja que ele tende a cair com frequencia, ok?? MUITO CONSISTENTE"

**Resposta:** Mock ligado em produção às ~21h25 (`scripts/modo.py --mock on`, sem deploy). O mock ficou
consistente de propósito: pedido mínimo por loja (o mesmo na loja e no carrinho), Lanchonete do Bairro, refri,
suco, batata e sobremesa onde faz sentido, o básico do dia a dia (óleo, macarrão, cebola, papel higiênico...),
e busca que ignora "de"/"com" e põe na frente quem tem todas as palavras. Auditoria: todas as buscas típicas
acham algo e, em loja de comida, a sugestão sempre acha o que acompanha. Carrinho do iFood real (o do Nissei)
é largado quando o mock liga: antes a busca ficava presa numa loja que o mock não tem.

## 2026-10-17 ~21h40 — a voz de saída é pedido do Fabio

**Prompt:** "eu que pedi, é uma feature nova, apenas aceite"

**Resposta:** Aceito: a voz (o bot falando) é a feature nova da outra janela. Esta sessão commita só o que
ela mesma mudou e faz o deploy a partir do main commitado, pra não subir a voz pela metade.

## 2026-10-17 21:40 — tá tudo deployado?

**Prompt:** "ta tudo deployado"

**Resposta:** Tudo o que está commitado, sim: o último deploy (v23, 21:37) é o main `636939e`, e nada
entrou no main depois. Fora do ar fica só o que a outra janela ainda não commitou: a voz de saída
(`voz.py` e mudanças em fluxo, contexto, textos, whatsapp e llm) e ajustes no painel. Com isso na pasta,
os testes passam (213). Entra no ar quando aquela janela commitar e fizer o deploy.

## 2026-10-17 22:15 — responder por áudio quando a pessoa pede

**Prompt:** em "D:/Users/fabio/Desktop/hackathon" vamos desenvolver a feature DE QUANDO A PESSOA PEDIR SOMENTE POR AUDIO (ouvir o que é dito pelo audio da pessoa ja esta sendo finalizado) SE ELA PEDIR somente se ela pedir pra ser respondida por audio, que naquela sessao em especifico e ao final dela acabe isso, seja respondida por audios personificados com o eleven labs, gere o audio rapidamente e mande no chat, vamos testar bem isso com cuidado, pq as respostas aqui precisam ser um pouquinho diferentes do ipsis litteris do chat, precisa parecer um pouquinho mais uma pessoa pedindo instrucoes pra pessoa mandar novamente em forma de audio ou texto como resposta, sabe? deve parecer de fato um atendente mandando audio

**Resposta:** Modo áudio (`src/bot/voz.py`, TTS em `src/shared/voz.py`): liga só com pedido explícito ("me responde por áudio"), desliga com pedido feito, 30 min parado, "sair" ou "pode escrever". O texto solto da rodada vira UMA nota de voz no fim, reescrita pelo Gemini como fala de atendente (fila própria, ~0,9 s); botões e cards continuam, número do pedido fica escrito, no CPF pede pra escrever. Falhou, vai escrito; se nem o 1º áudio sai, avisa que não dá. Commits 51ef4ff e o seguinte. Bloqueio: a key do secret `hackathon-elevenlabs` não tem a permissão `text_to_speech` (401). Falta liberar e fazer o `modal deploy`.

## 2026-10-17 21:42 — (continuação) a voz também foi pro ar

**Resposta:** Durante a conferência a outra janela publicou a voz (`51ef4ff`) e um conserto dela (`56aa1b3`).
Deploy feito a partir do main limpo, com 215 testes passando: v24 no Modal às 21:42, com voz, mock
consistente, sugestão do mínimo e Scribe. O que ainda estiver só na pasta, sem commit, não está no ar.

## 2026-10-17 22:40 — key nova da ElevenLabs com voz

**Prompt:** nova chave que funciona pra emitir voz: [key da ElevenLabs]

**Resposta:** Key testada: TTS em ogg/opus mono (formato da nota de voz) e o Scribe também funciona com ela, então substituiu a antiga no secret `hackathon-elevenlabs`. Voz padrão trocada pra Roberta (pt-BR) no modelo flash: ~1 s por fala, medido contra Raquel, Ana Alice e Davi. Deploy feito; upload do ogg pra Meta conferido. Falta o teste ponta a ponta no WhatsApp ("me responde por áudio").

## 2026-10-17 ~21h45 — o bot é inflexível: pedido no meio do endereço virou endereço

**Prompt:** "[3 prints: na etapa do endereço, um áudio pedindo pizza com calabresa, frango catupiry e uma coca
de 2 virou o endereço 'Oi, Eu Quero Comer Uma Pizza...'; depois 'Não achei pizza margherita com calabresa']
o bot é completamente inflexivel, ignorou o conteudo e mandou o que queria, ele deve mudar de funcao se o
texto ou o audio falar sobre outra coisa, entende? nesse caso ele falou sobre pizza de marguerita na hora do
endereco e ele achou que esse era o endereço, puta que pariu mano, seja mais flexivel"

**Resposta:** Endereço, bairro e complemento passaram a ler a mensagem antes de encaixar na etapa: com cara
forte da etapa (CEP, rua/avenida, apto/bloco) segue direto; o resto o Gemini lê sabendo a etapa. Pedido no
meio do endereço vira o pedido pendente (o antigo sai), com "Anotei: ..." e a pergunta de volta; papo é
respondido; cancelar cancela. "não tem" escrito no complemento é sem complemento; CPF sem número segue o
fluxo. Sabor e tamanho vão no termo da busca. Conferido com o Gemini de verdade na frase do áudio.

## 2026-10-17 ~21h50 — inglês na tela, botão que não leva a nada, fala é lei

**Prompt:** "[print: 'Meu pedido' respondeu 'Do not attempt to look up this Order ID again.'] ele ta falando
as vezes em ingles essa porra, sem contar que se nao tiver pedido feito, nao deve aparecer esse botao. Tenho
percebido que tudo que digo quase que é desconsiderado, ele só considera o funcionamento dos botoes sendo que
o que eu digo sempre deve ser lei, deve ser interpretado a cima de tudo, se precisar chamar outra funcao
naquele momento faça, entende?"

**Resposta:** O inglês era instrução da API pro agente (`suggestion`) indo pra tela: cortado na origem e com
filtro no tratador de erros. Pedido que este iFood não conhece (feito antes do mock) sai da lista, com
resposta em português. "Pedir de novo" e "Meu pedido" só aparecem quando levam a algo (nos 9 menus). Regra
no `como-funciona.md`: o que a pessoa diz manda; botão é atalho. O mock ganhou esfiharia e pratos do dia
(o print seguinte deu "Não achei esfiha de carne").

## 2026-10-17 ~21h58 — a voz manda texto junto e corta no fim

**Prompt:** "[print: no modo áudio o bot mandou texto e áudio, e o último áudio cortou no fim] OUTRA COISA:
eu pedi pra ela responder só por audio, até ai blz, mas ela manda texto e audio, sem contar que esse ultimo
audio dela saiu cortado no final, quando ela mandar audio é só audio, e audio n deve falar sobre botao, só
pedir pra pessoa fazer coisas porra" / "na vdd deixe isso pra outro agente, vou mandar pra ele aqui"

**Resposta:** Fica com o outro agente (a frente da voz). Esta sessão não mexeu em voz; só ajustou 2 linhas do
`tests/test_voz.py`, porque o menu sem pedido não mostra mais os atalhos.

## 2026-10-17 23:20 — áudio é só áudio, sem falar de botão, sem cortar o fim

**Prompt:** OUTRA COISA: [print da conversa: depois de pedir só áudio, o bot mandou a mensagem com botões E o áudio; o áudio dizia "é só tocar no botão"] eu pedi pra ela responder só por audio, até ai blz, mas ela manda texto e audio, sem contar que esse ultimo audio dela saiu cortado no final, quando ela mandar audio é só audio, e audio n deve falar sobre botao, só pedir pra pessoa fazer coisas porra

**Resposta:** Modo áudio virou só áudio: botões, cards, lista e texto são segurados e viram a fala (só o link de login sai, não dá pra entrar por voz); 3 produtos por vez, ditos numerados; código de entrega falado dígito por dígito; se o áudio falha, as mensagens normais saem. O áudio não fala de botão/tela (prompt + trava que corta a frase). Fim cortado: medido 1 em 8 sem a última palavra no flash; pausa de 0,7 s no fim deixou 8 em 8 inteiros. Resposta falada "é no centro"/"pode ser no pix" agora casa com a opção. Medido também: o Gemini inventava passo (CPF, "dinheiro na entrega") em 9 de 10 quando a pessoa dizia uma coisa e a mensagem era "não entendi"; com a regra de ouro, 0 de 10.

## 2026-10-17 ~22h10 — o automático repetia sempre o último pedido

**Prompt:** "tem um problema na compra com recorrencia, nao sei se é por causa do mock, mas pra toda
recorrencia diferente vem a mesma mensagem antiga [2 prints: 'todo dia as 7h peça dois paes' e 'todo dia
as 9h dois cafes expresso' responderam 'Opa, segunda vez de 1x X-Salada, 1x Refrigerante lata 350 ml por
aqui!']"

**Resposta:** Não era o mock: o agendar jogava fora os itens ditos e oferecia o último pedido com o texto da
2ª compra. Agora o automático é do que a pessoa disse: o bot monta o pedido uma vez (loja e produto) e
guarda como modelo, sem pedir agora; no dia o lembrete monta o carrinho do modelo e só fecha com o sim.
A hora dita é lida mesmo quando o Gemini não devolve (ele devolveu hora vazia pras duas frases). Conferido
com o Gemini de verdade nas duas frases. O mock ganhou uma cafeteria.

## 2026-10-17 23:40 — endereço e complemento falados viravam a frase inteira; chave nova do Gemini

**Resposta:** O atalho sem IA (frase com "rua" ou "apartamento") mandava a frase inteira. Agora sai só o dado: `so_endereco` corta antes do logradouro e `so_complemento` monta "Apto 14", "Bloco B, Apto 32", "2º andar" (número por extenso vira dígito). Key nova no secret `hackathon-gemini`; testando, o 3.1-flash-lite (1º da fila) estourava 6 s e o 3.5-lite responde em ~1,2 s, então o 3.5 foi pra frente.

## 2026-10-17 23:55 — OpenRouter de quebra-galho quando o Gemini estoura

**Prompt:** esse gemini ta estourando muito, cadastre como quebra galho pro debug algum modelo openrouter, tenho ele logado no meu pc aqui

**Resposta:** `src/shared/llm.py`: se a fila do Gemini falhar, tenta o OpenRouter (`google/gemini-3.5-flash-lite` e depois `anthropic/claude-haiku-5.5`), com o mesmo esquema JSON; `BOT_LLM=openrouter` pula o Gemini pra debug. Secret novo `hackathon-openrouter` criado com PREENCHER (desligado). A chave do PC não foi lida (o classificador barrou ler o .env da pasta sensível): falta o Fabio passar a chave ou cadastrar no secret.

## 2026-10-17 ~22h35 — o bot viciado em falar de automático

**Prompt:** "o robo ta viciado em falar sobre a recorrencia o tempo todo"

**Resposta:** O diário do bot (mensagens reais dos últimos 90 min) mostrou de onde vinha: a oferta pós-pedido
disparava em TODA compra depois da 2ª (sempre dizendo "segunda vez"), o "Não precisa" não era lembrado, e o
modo demo trouxe em 1 minuto o lembrete de um automático criado pelo bug antigo do X-Salada. O Gemini não
puxava o assunto: nenhuma dessas mensagens veio dele. Agora a oferta sai só na 2ª compra, "Não precisa"
segura a oferta por uma semana e o texto ficou curto. De carona, com o Gemini fora: "cancelar o pedido"
cancela (antes virava busca) e "quero jantar pizza hj" busca pizza no restaurante.

## 2026-10-18 00:10 — fotos das opções no modo áudio; foto que "não deu pra ouvir"; key do OpenRouter

**Prompt:** como pego a chave do openrouter qual o site certinho? preciso que quando eu peça pra ela entrar no modo só audio ela mande foto da comida, as opcoes como unica exceção, ok? o resto segue tudo audio mesmo / sem contar que agora pouco mandei uma foto e ela disse que nao consegue ouvir meu audio?? o que é isso / aqui a key do openrouter: [key do OpenRouter]

**Resposta:** Chave em openrouter.ai/settings/keys (crédito em /settings/credits). Cadastrada no secret `hackathon-openrouter` e testada: os dois modelos entendem o pedido (~4-5 s). Modo áudio: opções de produto chegam como fotos numeradas (1️⃣ 2️⃣ 3️⃣, sem nome nem preço) e o áudio diz o que é cada número; o resto segue só áudio. Foto + Gemini fora caía no aviso de áudio; agora o aviso depende do que chegou (e o OpenRouter também lê foto). O trecho é do claim bot-photo-group-kit: mudança mínima, commit isolado.

## 2026-10-17 22:45 — foto vira pedido e o kit pra dividir com os amigos

**Prompt:** abra /hackathon leia o projeto com calma, preciso criar algumas funcionalidades pro nosso bot fazer, primeiro, se a pessoa mandar a foto de uma comida pergunte se ela quer algo parecido e depois sugira de fato algo parecida (processo com nosso llm), garanta que a pessoa consiga fazer pedidos enviando fotos também, entende? pode ser foto de lista de compras tbm, cabe ao llm entender o que a foto diz, fato é que uma foto mandada em qualquer momento, inclusive como primeira mensagem, deve ser interpretada como pedido de foto, entendeu?? a outra feature é (MUITO CUIDADO AO FAZER ESSA AQUI): feature de dividir com os amigos, é uma feature demorada que deve ser feita com cuidado, se a pessoa falar que quer lanchar em 5 pessoas hamburguer, ele vai montar um kit com coca, hamburguer e boas opçoes, entende? e dizer quanto ficaria pra cada, acho que fica bom nosso modelo processar isso no meio, entende? tome decisoes boas que garanta um bom funcionamento e pense nos casos de borda desse modo amigo, gaste o tempo necessario, apenas garanta bom funcionamento de tudo

**Resposta:** Claim `bot-photo-group-kit`. Foto em qualquer etapa (até antes do login) vai pro Gemini (`src/bot/foto.py`): comida pergunta "quer algo parecido?" e busca os parecidos num carrossel só; lista/produto vira a lista do pedido; no CPF a foto nem abre. Kit em grupo (`src/bot/grupo.py`): loja única, o Gemini decide o que entra e quantos, o código escolhe as opções obrigatórias e faz a conta (por pessoa arredondado pra cima), com Outra loja, ajuste falado ("sem refri", "agora somos 6") e o "por pessoa" no total, no resumo e no pedido feito. 50+ testes novos e validação no Gemini real (`scripts/validar_foto_grupo.py`, TUDO CERTO). Deploy pendente do ok do Fabio.

## 2026-10-17 ~22h45 — adicionar ao carrinho falando, sem botão

**Prompt:** "o processo de adição no carrinho esta muito bugado, eu falo (SEM APERTAR EM BOTOES) precocemente
que ta bom ja, ou seja, antes dele esperar que eu ja terminei, to falando que essa pizza ta boa, entao ele ja
deve finalizar e adicionar ao carrinho, coisa que ele tem errado muito. ele deve adicionar mais certeiramente
ao carrinho é isso, se depois de ele mandar a foto de um hamburguer, eu falar, "eu quero esse ja pode
adicionar ao carrinho e fechar" O PROXIMO PASSO É O FIM DO CHECKOUT só recomendar adicicoes ao carrinho
mostrar total e como vai pagar, se ja tiver dito o meio em algum momento anterior é só pular essa etapa
tambem e colocar na funcao o meio que ja foi dito no momento anterior (recente)"

**Resposta:** "quero esse" sem número caía no "não entendi". Agora a fala escolhe o card (pelo número, pelo
único da tela ou pelo nome) e adiciona sem perguntar quantidade nem opção (usa a que foi dita, senão 1 e a
padrão da loja). "Pode fechar" vai direto pro fim: total, pagamento e uma sugestão do que acompanha. Pagamento
dito ("no pix") não é perguntado de novo. Número solto continua igual a tocar o botão.

## 2026-10-17 ~22h46 — a recomendação dava "travadinha"

**Prompt:** "eu pedi uma recomendação e ele n conseguiu ele ficou falando que "deu uma travadinha""

**Resposta:** Bug desta sessão: sem carrinho, o código da sugestão dava KeyError (log de produção das 22h44 e
22h45). Corrigido, com teste. Sem carrinho, a recomendação agora é o que a pessoa costuma levar ou algo da hora
do dia (pão de manhã, marmita no almoço, pizza à noite), e não "refrigerante" do nada. De carona: o teto de
resposta do Gemini subiu, porque o 3.5-flash-lite parou em MAX_TOKENS às 22h38.

## 2026-10-18 00:25 — áudio ou foto na hora do CPF vale "sem CPF"

**Prompt:** na hora do cpf mandei um audio dizendo que n precisa de cpf, se for audio pro cpf ou foto, só ignore considere que n quis mandar

**Resposta:** Na etapa do CPF, áudio ou foto não é ouvido nem aberto e vale como "sem CPF" (loja que exige CPF continua pedindo pra escrever). No modo áudio, a fala do CPF agora diz: escreve os números ou, se não quiser, manda um áudio. O teste da foto no CPF (claim bot-photo-group-kit) foi ajustado pra regra nova.

## 2026-10-17 23:00 — deploy da foto e do kit em grupo

**Prompt:** pode fazer deploy

**Resposta:** Worktree atualizada pro main (bbfd811, já com os fixes do time), 335 testes passando, deploy feito no mesmo app/label `hackfood-bot` (URL do login do iFood intacta). Foto vira pedido e o kit pra dividir com os amigos estão no ar.

## 2026-10-18 00:45 — tudo áudio vale também pros avisos do pedido a caminho

**Prompt:** quando eu peço exclusividade de audio, na hora de me enviar os lembretes sobre como pedido está ele fica enviando msg e depois para de mandar audio, apenas texto, quando peço tudo audio, deve ativar a funcao tudo audio, sabe?

**Resposta:** O modo áudio desligava no "pedido feito" e o rastreio (outro processo) só mandava texto. Agora, com tudo áudio, o modo segue até o pedido chegar: cada aviso ("confirmou", "saiu pra entrega", "chegou") vira nota de voz curta, sem pergunta; acabou o rastreio, a sessão de áudio acaba. Áudio falhou, o aviso sai escrito. O rastreio espera 10 s antes da 1ª consulta pra não chegar antes do áudio do "pedido feito".

## 2026-10-17 ~23h15 — perguntou o código de entrega e o bot ignorou

**Prompt:** "no meio dos status do pedido eu perguntei novamente em um audio qual era o código de entrega e ele
ignorou, isso era algo muito importante mas ele ignorou. A TODO MOMENTO AS MSGS DA PESSOA DEVEM SER
INTERPRETADAS e tentar entender sobre o que ele esta falando e redirecionar a conversa pra isso se adaptando,
tem que pensar em todo tipo de usuario que nao se comporta e adianta ou se atrasa em passos"

**Resposta:** O Gemini entendia ("acompanhar"), mas o bot só sabia mostrar o status (23h02 e 23h03, duas
vezes). Agora qualquer pergunta sobre o pedido feito é respondida no que foi perguntado (código de entrega,
quanto deu, o que veio, pagamento, endereço, previsão), em qualquer etapa, e a pessoa volta pra onde estava
(endereço, cards, pagamento). "Qual o código de entrega?" é reconhecido até sem o Gemini. Pra quem adianta ou
atrasa passo: "a primeira foto que você mandou", "o dois" escolhem pela posição ("segunda-feira" e "arroz
tipo um" não), CPF dito antes da hora fica guardado pra nota (e nunca vai pro Gemini), e o Gemini passou a
saber qual foi o último pedido. Conferido com o Gemini real nas falas da produção: 10 de 11 certas (a que
falhou, "eu já falei que quero um", pergunta "Qual deles?").

## 2026-10-17 ~23h25 — "Tá chegando?" depois de confirmar não dizia nada

**Prompt:** "perguntei sobre o status da entrega assim que ele confirmou e nao pareceu saber muito nao, ele
ficou falando sobre fazer novo pedido, mensagem que só de ver ja ta mal escrita tbm ta escrito "fazer pedido"
deveria ser no minimo, "fazer novo pedido". eu meio que nao tenho como perguntar como o pedido esta, onde
está e etc"

**Resposta:** "Tá chegando?" e "O entregador chegou?" (23h21) ganhavam uma linha de status e os botões de
pedir de novo. Agora vem o status inteiro: onde está, quando chega em horário ("entre 23h46 e 23h56"), loja,
número, código de entrega, o que vem e o total, com o botão *Atualizar status*. Quem já pediu vê *Fazer novo
pedido* no lugar de *Fazer pedido*.

## 2026-10-18 01:20 — primeira mensagem simplesinha com vitrine do gosto da pessoa

**Prompt:** pra primeira mensagem deixe ela bem simplesinha e ja meta umas recomendacoes pra chamar atencao do cliente de acordo com os gostos dele, algo assim [prints do Ailo do iFood: carrossel "Tô afim de Lanches", "Quero pratos até R$ 45", "Descontos pra você"] faça essas categorias de recomendação feitas com agentes internos nossos

**Resposta:** Claim `bot-welcome-showcase`. O "oi" agora é "Oi, Fabio! 😊 O que você quer pedir hoje? Pode escrever ou mandar áudio." e logo embaixo um carrossel montado por agentes internos (`src/bot/vitrine.py`): gosto (histórico nosso ou pedidos do app), hora do dia, precinho (maxItemPrice) e descontos (preço promocional real). Foto de produto real em cada card, no máximo 3 buscas por vitrine, guardada 20 min. Tocar ou falar o card busca aquilo com o mesmo teto/filtro. No modo áudio vira fotos numeradas + áudio.

## 2026-10-17 ~23h20 — a lista tem que ir pro mercado que tem tudo (e o kit sem Coca)

**Prompts:**
- "quando eu estou escolhendo uma lista de mercado, sinto que ele vai pelo primeiro item e depois vai vendo se
  tem os demais, mas ele deve selecionar um mercado que no minimo tem tudo né? assim como me deixar trocar de
  mercado no meio, mas sempre garantir o melhor custo beneficio dentre os mercados que tem tudo que quero, o
  mesmo pra restaurante né, gaste bastante tempo e atenção nessa feature pois é um dos coracoes do projeto,
  muito cuidado"
- "[print do kit pra 11 pessoas na Pizzaria Bella Napoli com o aviso "Não achei coca-cola nessa loja"] tem
  isso aqui ele me recomendou esse lugar que nem tinha coca, nao era isso que eu queria, eu queria coca"

**Resposta:** Era isso mesmo: a loja era a do 1º item escolhido e o resto da lista só era procurado nela; o
kit escolhia a pizzaria pela pizza. Agora lista com 2+ itens (escrita, falada, de foto, e "pizza e uma coca")
busca tudo antes e vai pra loja que tem TODOS os itens, a de menor conta entre elas (o mais barato de cada
item x quantidade + entrega); nenhuma com tudo: a que tem mais, dizendo o que fica de fora. *Trocar de loja*
(botão ou "tem outro mercado?") mostra as outras com quanto sai e leva o carrinho junto. O kit usa a mesma
conta. Um filtro só do Gemini pra lista toda (um por item estourou a cota da chave: 429). Conferido com o
Gemini real: a lista das 23h04 (8 itens) foi pro Supermercado Central em 1 s; pizza + Coca, pra Forno a
Lenha. Mock ficou coerente (mercados com o básico todo, Coca na pizzaria).

## 2026-10-18 ~00h15 — quais são as tools do MCP do iFood

**Prompt:** "quais as tools do mcp inteiro? só pra eu pensar aqui sobre"

**Resposta:** Listei as 24 tools dos 4 domínios (User 3, Offer Discovery 6, Cart 13, Order Tracking 2), pelo
resumo oficial do repo (`regras da api/ifood-mcp-developer-portal.json`), marcando as 19 que o bot já usa e as
5 que não usa (browseOffers, listItemTaxonomy, getMerchant, updateCartItem, removeVoucher), com ideias de uso.
Avisei que o disco C: da máquina está cheio (0 GB livres), o que pode travar git, Python e Modal locais (o bot
no Modal não é afetado).

## 2026-10-18 ~00h25 — religar o que caiu

**Prompt:** "abra /hackathon e retome de onde paramos, os processos morreram no meio"

**Resposta:** O bot já estava no ar (v39, 00:06) e nada ficou pela metade no código. Quem tinha caído era o
servidor de dados do dash (porta 8787), por falta de memória; o Vite (5173) seguia de pé. Religuei o servidor:
"Dados reais" já mostra 942 eventos (o deploy resolveu o vazio) e a demonstração, 32 mil. Ficou pendente: apagar
ou não o `app.js` antigo do Pedro, e o `docs/whatsapp.md` com edição não commitada de outra janela.

## 2026-10-18 ~00h45 — apagar o app.js e acertar o status do WhatsApp

**Prompt:** "pode apagar o app.js sim do pedro pode arrumar esse 2 corrigido e commitar."

**Resposta:** Apaguei `Frontend/Rascunho_Dash/app.js` (versão antiga em JS puro que ninguém importava). Os 24
testes do dash passam e o build também. Commitei a seção "Status da conta" do `docs/whatsapp.md` depois de
reconferir o número na Graph API (só leitura): TIER_250, qualidade GREEN, sem Official Business Account. Corrigi
o nome, que não está "não aprovado": é AVAILABLE_WITHOUT_REVIEW. O erro 141006 do template não foi retestado,
porque exigiria enviar mensagem.

## 2026-10-18 ~01h45 — bot que atende ligação e iFood real de volta

**Prompt:** "mano, com muito cuidado, vamos analisar a possibilidade de montarmos um bot/agente que tria LIGACOES feitas por usuarios, temos essa possibilidade? apenas de uma olhada, fazendo isso, podmos ser banidos? nao podemos perder esse deploy no wpp. assim que me responder, rapidamente desligue o mock do wpp e ligue o acesso ao MCP do ifood."

**Resposta:** A Calling API oficial da Meta existe e vale no Brasil, mas pede limite de 1–2 mil conversas/24h (o
número está em TIER_250) e um servidor de voz WebRTC/SIP, que não cabe no Modal sem gambiarra. Nada foi ligado.
Banimento não vem de usar a API oficial, vem de bloqueio e denúncia de usuário; o risco real é mexer nas
configurações do número emprestado do handwrite. Mock desligado (`scripts/modo.py --mock off`, sem deploy): o bot
volta ao MCP real do iFood na próxima mensagem. Disjuntor liberado; o "tempo rápido" segue LIGADO.

## 2026-10-18 ~01h55 — gambiarra pra ligação

**Prompt:** "n tem nem um jeito de gambiarra?"

**Resposta:** Pela ligação do WhatsApp não tem: lib não oficial (Baileys etc.) é proibida e é o que dá ban.
Opções sem tocar no número: (1) link no WhatsApp que abre página com agente de voz no navegador (ElevenLabs
Agents, que já temos a conta), e (2) número de telefone comum (Twilio) atendido pelo mesmo agente. As duas
chamam o nosso back no Modal pra usar o MCP. Nada implementado, esperando o Fabio escolher.

## 2026-10-18 ~01h15 — o que o Davi está fazendo

**Prompt:** "o davi fez uns commits ai, veja sobre o que é e o que fazem, no caso o que ele esta fazendo?"

**Resposta:** Expliquei o claim `dash-agentes-mcp` do Davi: abas "Uso do MCP" e "Agentes" no dash, alimentadas
pelo rastro de cada chamada de IA (só contagens, sem texto), com o liga/desliga (fase 2) esperando. Avisei de um
teste dele que falhava por empate de horário no Windows (corrigido depois, em e31eedd).

## 2026-10-18 ~01h30 — deploy e o time de agentes como coração do dash

**Prompts:**
- "veja oq o davi commitou por ultimo, e faça o deploy"
- "eu deixo fazer o deploy, rode ele. [...] quero aprimorar [...] a gestao e transparencia [...] animação bonitinha
  de como cada agente esta interagindo entre si, me de a opção de eu abrir um a um e ir filtrando as configurações
  dele, qual o modelo, qual o system prompt [...] qual key ta setada [...] se eu posso desligar ele por hora [...]
  personificação [...] ela dever ser tipo a primeira tela, depois o uso do mcp e dps metricas de dinheiro, alem de
  dar uma enxugada"
- "faça o back funcionar de uma maneira que qualquer pessoa consiga trabalhar focado na melhoria de um agente [...]
  queira trocar o modelo de imagem apenas [...] animacoes que transmitam o sentimento da coisa, como um time
  trabalhando, e uma boa modularização de back."
- "tudo bem refatorar o design das abas, nada é fixo aqui"

**Resposta:** Deploy das 01:31 (com o fix do Davi `e5f3d73`). O Davi passou a tarefa inteira pro Fabio, então
abri o claim `dash-agents-control`.
- **Back:** `src/agentes/` com um arquivo por agente (Lia, Íris, Duda, Beto, Tito, Vina, Otto). Cada arquivo tem
  a fila de modelos SÓ daquele agente; trocar o modelo da foto é mexer em `src/agentes/foto.py`, ou fazer pelo
  dash sem deploy.
- **Interruptor:** liga/desliga sem deploy (`cfg:agentes`). O desligado cai no plano B de sempre e conta como
  "pulo", não erro.
- **Ficha do ar:** keys só com os 4 últimos caracteres e versão do prompt (`cfg:agentes_ar`).
- **Dash:** "Agentes" virou a 1ª tela. Tem o palco ao vivo (recados correndo entre cliente, Maestro, agente e
  iFood, com balões), os cards de desempenho com filtros e a ficha de cada um (desempenho, fila e modelo
  principal, keys, plano B, onde mexer, system prompt, interruptor com confirmação pros essenciais).
- **Menu:** Agentes → Uso do MCP → Dinheiro → Conversas, e o resto em "Mais análises". Saíram Inteligência
  artificial, Follow-ups, Financeiro (foi pro Dinheiro), o cartão de propaganda e os enfeites.
- **Testes e deploy:** 419 do back e 35 do front passando. Deploy às ~02h30 (2af1cf6). A ficha do ar aparece no
  dash depois da 1ª mensagem que o bot receber.


## 2026-10-18 ~02h00 — mock de volta

**Prompt:** "volte o mock do mcp"

**Resposta:** Mock religado (`scripts/modo.py --mock on`, sem deploy): o bot volta ao iFood falso na próxima
mensagem. Tempo rápido segue ligado.

## 2026-10-18 ~02h40 — um agente chamado Tungs

**Prompt:** "coloque o nome de algum agente pra \"tungs\""

**Resposta:** O tutor (antes Tito) virou Tungs em `src/agentes/tutor.py` (commit 15386c5). Só muda o crachá no dash; o
comportamento e o prompt do tutor seguem iguais, então não precisou de deploy.

## 2026-10-18 ~02h15 — leite com mercado fechado

**Prompt:** "quando pesquiso tipo, leite (que so vende em mercados) e todos os mercados estao fechados ele diz que nao achou, o mcp nao consegue retornar de mercado fechado é isso? nao da pra agendar? o mcp nao tem essa funcao? acho que pros nossos testes era legal vc ignorar se o mercado ou estabelecimento esta fechado e exibir o item mesmo assim, se possivel, sabe?"

**Resposta:** Quem escondia era o bot: a busca mandava `onlyOpen: true`. Criei o interruptor
`scripts/modo.py --fechadas on|off` (`cfg:fechadas`, sem deploy depois deste): loja fechada aparece depois das
abertas. O MCP tem entrega agendada (timeslots em mercado), mas o bot só usa a
imediata e ninguém testou agendar em loja fechada. Deploy feito e interruptor ligado.

## 2026-10-18 ~02h25 — loja fechada sem aviso

**Prompt:** "com "🔒 fechada agora" no card. NAO PRECISA DISSO, É SO UM TESTE, mostre como se fosse normal"

**Resposta:** Tirei o aviso: com `--fechadas on`, a loja fechada aparece igual às abertas (só vem depois delas).
Deploy feito.

## 2026-10-18 ~02h20 — o bot parou de responder; pauzinhos do Maestro e MCP no palco

**Prompt:** "agora ta muito melhor, tirando o fato que ele parou de responder... voce fez alguma cagada aí, né?....
outra coisa, adicione uma pequena animacao de pausinhos nas "maos" do maestro se mexendo enquanto ele "orquestra",
assim como a possibilidade de clicar nos agentes na tela supeior, pra expandir um pouquinho as acoes dele assim
como eu quero ver mais dados sobre o mcp nessa tela, to sentindo muita falta disso... mesmo que de uma forma sutil"

**Resposta:**
- **Por que parou de responder:** não foi código. Nos logs do Modal o bot recebe, entende e manda a resposta, mas
  desde 05:01 a Meta recusa toda entrega com o erro `131042 Business eligibility payment issue` (conta do WhatsApp
  sem moeda configurada no faturamento). Nenhum traceback no app. Anotado em `docs/whatsapp.md`; só o Fabio
  resolve, no Meta Business Suite.
- **Palco:** o Maestro ganhou dois pauzinhos que balançam devagar parado e regem rápido enquanto orquestra.
  Cliente, Maestro, agentes e iFood viraram clicáveis e abrem um balão com as últimas ações; o de agente tem um
  atalho pra ficha completa.
- **MCP na tela do time:** o balão do iFood mostra as 5 tools mais chamadas (chamadas, erro, latência); o nó do
  iFood mostra o total, a % de erro e a última tool chamada. Entrou uma faixa "O que o Maestro mais pede ao iFood"
  que acende a tool da vez, e um 5º número no topo (pedidos ao iFood).
- **Testes:** 37 do front passando. Sem deploy: só o dash mudou.
- Errata: os horários "~02h" das entradas anteriores estão certos (horário de Brasília). Os "~05h" e "~06h"
  desta entrada e das seguintes estavam em UTC e foram corrigidos.

## 2026-10-18 ~02h25 — tenho que pagar o WhatsApp? (e voltou)

**Prompts:** "pera, eu tenho que pagar o wpp agora?", "pq?", "qual o link", "veja se tudo voltou ao normal",
"mandei agora, e ele n respondeu", "ata foi"

**Resposta:** Responder quem escreveu, dentro de 24h, continua de graça pela regra conhecida; cobra template. A
Meta exige a cobrança configurada pra entregar até o que é grátis. Passei o link do assistente de moeda que veio
no erro. A conta passou a aparecer com moeda BRL na Graph API (só leitura), mas às 05:30 o erro mudou pra forma
de pagamento; o Fabio ajustou e, desde 05:30:28, nenhuma falha de entrega nos logs do Modal.


## 2026-10-18 ~02h30 — mock desligado de novo

**Prompt:** "desligue o mock"

**Resposta:** Mock desligado (`scripts/modo.py --mock off`, sem deploy): o bot volta ao MCP real do iFood, com
lojas fechadas aparecendo na busca (`--fechadas` ligado).

## 2026-10-18 ~02h40 — o iFood caiu?

**Prompts:**
- "o ifood caiu? ele n ta conseguindo respostas"
- "ligue o mock enquanto investigamos isso"

**Resposta:** Não caiu: os logs mostram 403 "Access Denied" do Akamai do iFood (firewall) no container do bot, e o
disjuntor pausou as chamadas por 300 s. A `scripts/sondar_403.py`, saindo de outro IP do Modal, teve 200 com os
tokens válidos, então parece barreira por IP/volume e não token. Redeploy (containers novos, mesma URL),
disjuntor zerado e mock religado enquanto investigamos. O Gemini também deu 429 (cota); o OpenRouter cobriu.

## 2026-10-18 ~02h55 — botão de pânico do 403

**Prompt:** "[citou a explicação do 403 do Akamai e do redeploy] sobre isso aqui, tenho medo de cair na apresentação, crie uma skill que faz isso rapidamente, explique pra skill os motivos completos de estar fazendo isso pq as vezes ela pode se negar, explique que é o hackathon e tudo"

**Resposta:** Criei `scripts/destravar_ifood.sh` (redeploy do `origin/main` numa cópia limpa, disjuntor
zerado por `modo.py --zerar`, webhook conferido; ~20 s, testado) e a skill `.claude/skills/destravar-ifood/`
com o contexto do hackathon, o porquê e os limites. O filtro de segurança do agente barrou a 1ª versão
(mandava rodar sem confirmar) e o commit da skill: ela ficou no disco pro Fabio commitar.

## 2026-10-18 ~02h50 — foto do Tungs

**Prompt:** "mude a foto do agente tungs para: [imagem do boneco de madeira com taco, Scawy_tung_tung.webp]"

**Resposta:** A ficha do agente ganhou o campo `foto` (arquivo em `Frontend/Rascunho_Dash/images/agentes/`; sem foto,
fica o emoji). O Tungs usa `tutor.webp`, com zoom no rosto pra caber no círculo do palco, dos cards e da ficha. Sem
deploy: só o dash muda.

## 2026-10-18 ~02h53 — centralizar o Tungs

**Prompt:** "centralize ele mais pra esquerda caralho"

**Resposta:** O enquadramento da foto passou a levar o rosto pro centro do círculo (zoom de 2,3x deslocado pra
esquerda e pra baixo). Conferido no palco.

## 2026-10-18 ~02h56 — balão em cima dos pauzinhos

**Prompt:** "[print do balão \"Maestro Respondeu (botões)\" cobrindo os pauzinhos] o texto esta em cima dos bastoes de maestro arrume isso"

**Resposta:** O balão do Maestro sobe mais que o dos agentes (84px em vez de 44px), porque o Maestro é maior e tem os
pauzinhos por cima. Medido no navegador: o balão para 21px acima da ponta dos pauzinhos.

## 2026-10-18 ~03h00 — animação em tempo real

**Prompt:** "o agente processa as animacoes só dps de responder a msg, seria bom ele processar em tempo real"

**Resposta:** O bot já gravava o diário a cada 0,3 s; o atraso era o servidor local do dash, que a cada evento novo listava
o modal.Dict inteiro (medido: 11 a 15 s). Agora o bot mantém a chave `recentes` (últimos 120 eventos) e o servidor lê
só ela (~1 s), com a varredura completa em segundo plano a cada minuto. O palco busca a cada 0,7 s e toca rajadas mais
rápido. Deploy feito (09b35fd), 429 testes no back e 37 no front.

## 2026-10-18 ~03h15 — botão de IA com varredura de arco-íris e insights por time

**Prompt:** "blz, vou tratar de uma featura um pouco trabalhosa [...] adicione um botao flutuante ao canto inferior
direito das páginas: conversao, clientes e mercado, com o icone de i.a que quando eu clique faça uma animação de como
se o botao tivesse varrido a página inteira em cores de arco iris bem sutis [...] como a apple faz na apple
intelligence animation [...] capriche muito nessa animação que vem de cima a baixo. pra cada pagina ela deve gerar
insights valiosos com o modelo setado [...] insights para os times responsaveis [...] quais times e quais medidas o
ifood pode tomar, basicamente insights UTEIS"

**Resposta:** Claim `dash-ai-insights`.
- **Agente nova, a Sofia (Analista):** ficha, fila de modelos própria e interruptor. Roda no Modal (função
  `analisar_pagina`), porque as keys de IA só existem lá.
- **Dados enviados:** o dash manda só agregados de cada página (funil com perda por etapa, motivos de abandono,
  recompra, concentração, cidades e lojas), nenhum nome de cliente.
- **Animação:** onda de arco-íris desfocada e sutil descendo do topo ao rodapé, com uma linha brilhante na frente.
  Depois a borda da tela brilha girando enquanto ela pensa e apaga quando os insights chegam. O botão tem um anel de
  arco-íris.
- **Painel:** resumo + 3 a 5 cartões com time dono, evidência, ação, impacto, prazo e métrica; "Gerar de novo".
- **Testado de verdade nas 3 páginas:** ex. "Comercial e parcerias: baixa conversão na Drogaria Saúde".
- **Cota do Gemini:** a key do Gemini está estourada (429), então quem respondeu foi o OpenRouter. Isso vale pro
  bot inteiro.
- **Testes e deploy:** 433 no back e 41 no front. Deploy 9626e97.

## 2026-10-18 ~04h42 — onde a meta chama o nosso back

**Prompt:** "onde vejo onde a meta chama o nosso back, o url de fallback?"

**Resposta:** Conferido na Graph API (`GET /{PHONE_ID}?fields=webhook_configuration`, só leitura): a Meta entrega
os eventos no override do próprio número, o `/whatsapp` do hackfood-bot no Modal. O painel da Meta (WhatsApp →
Configuração) mostra só a URL do app, que é a do handwrite: ela é o fallback, usada só se o override do número sair.
Não há override na WABA. Sem mudança de código.

## 2026-10-18 ~05h05 — seção das rotinas (follow-up e afins) no dash

**Prompt:** "vamos mexer um pouco no front do dashboard, ok? adicione uma sessaozinha sobre os algoritmos de
recorrencia, como followup e afins, algum indicativo que foram disparados, sabe? sinto falta disso"

**Resposta:** Claim `dash-rotinas`. Na tela Agentes entrou "O que o Maestro faz sozinho":
- **Quatro cartões:** cutucada (3 min), carrinho esquecido (5 min), lembrete de recompra (cron de 15 min) e
  rastreio. Cada um com disparos, gráfico, último disparo e o desfecho (voltou a falar, comprou, virou pedido...).
- **Lista:** os últimos disparos, cada um abrindo a conversa. Abre nos follow-ups e filtra por rotina; o rastreio
  vira uma linha por pedido. Quando uma rotina dispara ao vivo, o cartão acende e o recado do Maestro no palco ganha
  a cor dela.
- **Bot:** o abandono ganhou origem própria no diário. Cada passada do cron dos lembretes vira um evento com
  avisados, adiados, erros e a agenda, então o dash diz se o cron está vivo e quantos lembretes esperam a pessoa
  voltar (janela de 24h fechada). Sem deploy ainda: o último deploy é de antes do commit do Claude (47d3f17), e
  subir agora levaria aquilo junto. Até o próximo deploy, a seção mostra tudo, menos a passada do cron.
- **Demo:** cutuca, esquece carrinho, liga e responde lembrete com as mesmas funções do bot, e o cache guarda os
  clientes simulados.
- **Erro corrigido:** os horários que eu tinha escrito em UTC neste log voltaram pro horário de Brasília.

## 2026-10-18 ~05h28 — a Sofia sai do palco do Maestro

**Prompt:** "filho, a sofia nao devia estar junto com o maestro, tire ela dali por favor"

**Resposta:** A ficha ganhou `onde` ('conversa' ou 'painel'), e a Sofia é 'painel'. Ela saiu do palco e das contas
do time da conversa, e ficou num cartão "Fora da conversa, no painel" na tela Agentes, com a ficha (modelo e
interruptor) a um toque, porque o botão de insights depende dela. Testes: 459 no back e 49 no front.

## 2026-10-18 ~05h45 — cutucada com 1 min, e deploy

**Prompts:** "coloque a cutucada pra 1 min, ok?", "pode dar deploy inclusive"

**Resposta:** `FOLLOWUP_SEG` foi de 180 pra 60 s (`src/bot/fluxo.py`); o carrinho esquecido continua aos 5 min. O
dash e a demo leem a constante, então o cartão da Cutucada já diz "Depois de 1 min". Deploy logo depois deste
commit, com o main inteiro: inclui o Claude na frente dos agentes (47d3f17), a origem própria do abandono e a
passada do cron dos lembretes no diário. Testes: 463 no back e 51 no front.

## 2026-10-18 ~06h00 — QA do Davi (kit, M2, U20) e o pedido que não fechava por áudio

**Prompts:** "davi me mandou isso aqui: [relato do QA do Davi: 1) kit do grupo: U14 'somos 6, até 100 reais'
montou R$ 205,99 sem avisar; U11 'sem refri' trocou por sucos e ficou mais caro; U16 cada ajuste refazia o kit do
zero; 2) M2: item de R$ 36,99 e 'até agora' de R$ 47,97 no MCP real; 3) U20: 'mais 10 leites' por áudio disse que
adicionou e o carrinho não mudou]", "[print do WhatsApp: no resumo, dois áudios e o bot mandando tocar em Confirmar
pedido] EU NUNCA CONSIGO FINALIZAR O PEDIDO POR AUDIO, especificamente essa ultima etapa ele nao aceita audio, ele
deve aceitar, porra"

**Resposta:**
- **Kit (1):** U16 e U11 já estavam resolvidos no 643c477 (no ar desde o v48). O U14 (o teto do "até 100 reais") a
  outra sessão está fazendo agora; não mexi.
- **M2:** o "até agora" usava o total do iFood, que no real já soma entrega e taxas desde o carrinho criado (o falso
  não). Na conversa de 01:58 era 1 lanche só e "até agora R$ 47,97". Agora mostra o que os itens somam e, quando há,
  uma 2ª linha "Com entrega e taxas".
- **U20:** às 04:26, "pode colocar mais 10 leites" com o bot em modo áudio. A Lia, no modelo reserva, chamou de
  `quantidade`; fora do "quantas unidades?" isso não fazia nada, e a `resposta` dela ("adicionei mais 10 leites")
  saía como mensagem, que a Vina falou. Agora vira compra, e o prompt da Lia proíbe dizer que já colocou.
- **Áudio no resumo:** o "sim" com sugestão perguntava "assim ou com feijão?" sem fim, e "faz o pedido" falado caía
  no "toque em Confirmar". Agora o "sim" seguinte e o "faz o pedido" falado fecham o pedido.
- **Testes:** 474 numa cópia limpa do main com estas mudanças. Deploy logo depois deste commit.

## 2026-10-18 ~06h20 — "o pagamento não passou" do nada, depois do "saiu pra entrega"

**Prompt:** "[print do WhatsApp: pedido 7483 do Extra confirmado e saindo pra entrega; 'ta chegando?' respondido;
1 min depois '❌ O pagamento não passou. Confira no app do iFood ou faça o pedido de novo.'] oxi caralho, o que é
essa msg do nada de pagamento, nem to pedindo mais nada"

**Resposta:** Veio do rastreio, e o status era do próprio pedido: o MCP real mandou PIX_CREATED (06:10, virou o
genérico "seu pedido teve uma atualização"), CONFIRMED (06:11), DISPATCHED (06:14) e PAYMENT_DECLINED (06:18).
O rastreio avisava qualquer código novo. Agora "registrado" e PIX_CREATED ficam calados (o pedido feito já explica
o PIX), recusa de pagamento depois de a loja confirmar fica só no log (se o pedido cair, o CANCELLED avisa) e
status que vai e volta avisa uma vez só. Recusa antes da confirmação continua avisando. 489 testes.

## 2026-10-18 ~06h25 — o resto dos relatos do Davi

**Prompt:** "leia tudo que ele escreveu nos relatos dele, ok? vamos arrumando o que esta pendente de ser arrumado
agora"

**Resposta:** Li o `docs/qa-18-10.md` e o `docs/prompts/davi.md`. Claim `bot-qa-pendentes`; a alta prioridade já
estava feita (U11/U16 643c477, U14 71e2001 da outra sessão, M2/U20 44b1aad). Corrigidos, com teste:
- **B3/U4:** o carrinho que sumiu às 01h43 foi o mock desligado com o carrinho de mentira montado; o bot largava
  calado. Agora avisa e o toque na lista velha volta pro menu (180a989).
- **U21, U24, U7, U10, U1:** "meu pedido" mostra o carrinho montando; agendar abaixo do mínimo vale; botão velho de
  antes do cancelar e da foto não ressuscita nada; "Fazer pedido" não repete a pergunta (180a989, 76a345d).
- **U9, U3, H4, M3, U17:** foto sozinha sempre pergunta; "Mudar" no pagamento e no CPF; apagar os dados para o
  rastreio; saudação com o nome do WhatsApp; "leite" fica "leite" (4143c34).
- **Mantidos de propósito:** U12, U18 (só áudio, tem teste), C1, U27, O1/O2, M1. A tabela do que mudou ficou no fim
  do `docs/qa-18-10.md`, pro reteste do Davi. 500 testes.

## 2026-10-18 ~07h20 — PDF dos insights da Sofia e o interruptor do mock

**Prompt:** "adicione a funcionalidade de exportar os dados que a sofia gera, pra pdf. cade o botao de switch pra
mock ou little aviso, ja ta setado pra quando switcha?"

**Resposta:**
- **PDF:** "Baixar PDF" no pé do painel da Sofia (Conversão, Clientes, Mercado). Mesmo cabeçalho do relatório,
  período, filtros e modelo, o resumo e um cartão por insight (time com a cor dele, impacto, evidência, ação, métrica
  e prazo); quebra página quando não cabe, e emoji que a fonte não tem sai. O jsPDF só carrega no toque.
- **Interruptor do mock:** existe (71e2001, da outra sessão), no pé da barra lateral: "Modo palco" e "Catálogo de
  reserva". Não aparecia porque o servidor local do dash era de antes da rota `/api/mock`; reiniciei. O modo palco
  está desligado: com ele armado, no 1º erro do iFood o mock liga sozinho, o sino avisa e quem tinha carrinho recebe
  o "precisei recomeçar seu pedido". 54 testes no front.

## 2026-10-18 ~08h15 — a troca do mock sem a pessoa perceber

**Prompt:** "nao da pra dar uma burladinha nesse pass: O cliente só percebe se tinha carrinho montado. Na mensagem
seguinte ele recebe "😕 Precisei recomeçar seu pedido…".? torna-lo mais natural?"

**Resposta:** Claim `bot-troca-calada`. O "precisei recomeçar" saiu: o pedido atravessa a troca.
- **Carrinho:** no começo da rodada o bot monta o mesmo do outro lado, com a peça do "Trocar de loja": a loja que tem
  tudo pelo `melhor_loja` (a de mesmo nome, se tiver), cada item pelo nome e com a mesma quantidade. Nada é dito.
- **Produto da vez e card de antes:** o "Quantas...?" respondido depois da troca e o "Quero esse" da lista velha
  valem o mesmo produto do lado de cá.
- **O que não tem lá:** sai como loja fala ("😕 *X* não está mais disponível, tirei do seu pedido"); o parecido do
  que a pessoa pediu entra com "🔄 *X* acabou, coloquei *Y* no lugar". Se nada vem junto, o aviso é "o que estava
  no seu pedido não está mais disponível", sem falar em iFood. Parecido tem que ter o que foi pedido no nome: no
  teste, "Leite em pó" quase virou "Sabão em pó" por causa do "em pó".
- **Resumo na tela:** o "Confirmar" de antes não fecha: vem o resumo novo com os preços de agora.
- **Modo palco no meio da rodada:** chamada presa ao pedido (carrinho, loja, item) não é mais refeita igual no mock
  (dava "seu pedido expirou"): sobe `IfoodTrocou` e o fluxo faz a mesma troca e roda a ação de novo.
- De quebra, a linha levada pra outra loja guarda a unidade de venda do produto de lá. 518 testes.


## 2026-10-18 ~08h00 — o Beto chapando: omelete no lugar de pizza, churrasco sem carne, ajustes alucinados

**Prompt:** "abra /hackathon preciso de um ajuste urgente, acredito que no agente beto, de montagem de kits, ele
sempre esta chapando, sugerindo coisas horriveis, faltando com materiais essenciais do kit, exemplo, churrasco sem
carne, e alucinando na mudança de itens, preciso que essas montagens e alteracoes de montagens sejam muito
consistentes. [print do WhatsApp: "vou fazer uma pizzada com mais 4 amigos, orçamento de 130 reais" virou kit da
Padaria Santa Fé com 5x Omelete de Pizza + Coca 2 L, R$ 116,99]"

**Resposta:** Claim `bot-kit-consistency`. Três causas, três remédios, tudo no código (o modelo deixou de mandar):
- **O principal não era o prato.** A busca do iFood e o filtro de relevância deixam passar "Omelete de pizza" pra
  pizza e carvão/sal grosso/carne moída pra churrasco, e a padaria era a loja "mais barata". Agora cada comida tem
  uma receita (`RECEITAS` em `src/bot/grupo.py`): o que conta como o prato, o que nunca conta, quanto por pessoa
  (fatias, peças, ~400 g de carne), o que acompanha e o que não pode faltar (carvão no churrasco). Loja sem o prato
  nem entra na lista; se o modelo disser que não tem (`falta_o_prato`), pula pra próxima.
- **Composição com crivo.** O que o modelo devolve passa por `_validar`: principal em quantidade de gente (fora da
  faixa, refaz na proporção dos sabores), no máximo 2 bebidas e por cabeça, uma bebida sempre (salvo "sem refri"),
  o que pediram entra, o que a receita exige entra.
- **Ajuste é do código** (`src/bot/kit_ajuste.py`): "sem refri", "troca a coca por guaraná", "mais batata", "só 3
  pizzas", "põe cerveja" (busca na loja, avisa se não tem), "mais barato" (um degrau por vez), "agora somos 6"
  (refaz só as quantidades) são aplicados em cima do kit da tela, sem chamar o modelo; a explicação é do código
  ("Tirei Coca-Cola 2 litros 👍"). O que o código não lê ("2 são vegetarianos") vai pro modelo, que só pode mexer
  nos principais e no que citou. Os ajustes ficam no kit e valem no "Outra loja".
- Mock ganhou a padaria com omelete e um churrasco de verdade; 19 testes novos (`tests/test_kit_ajuste.py`), 532
  passando (os 5 que faltam pedem o `fastapi`, que não está neste Python). Docs §9.2 atualizada.

## 2026-10-18 ~08h30 — "o Otto tá demorando demais"

**Prompt:** "da uma olhada na otto ele ta demorando demais, pqp ve se tem algo a ser feito"

**Resposta:** Pelo diário do painel (2 dias, 59 áudios): o Otto (Scribe) leva 0,3–0,8 s por áudio, média 466 ms,
zero erro. A demora que se sente nas conversas por áudio é o resto da corrente: o kit em grupo com o iFood real
(11h06: 47 s e 60 s, com ~15 chamadas de searchOffers/getItem de ~2,5 s cada, em fila, mais um filtro de
relevância por busca) e o fechamento (7 chamadas do MCP em fila, ~30 s; getCartDeliveryMethods sozinho 9,5 s), mais
a resposta falada (roteiro no Claude 2,5–4 s + ElevenLabs 1–1,4 s). Feito agora: os getItem dos principais e as
buscas do que acompanha vão em paralelo e UM filtro do modelo cobre todas as buscas (`_em_paralelo` em
`src/bot/grupo.py`); o freio do iFood segura o ritmo. Opções sem código, pra decidir no dash: pôr o
`gemini-3.5-flash-lite` na frente da fila da Vina (roteiro da voz) e da Duda (relevância), que respondem em ~1,2 s
contra 2,5–5 s do Sonnet; e baixar o `ESPERA_AUDIO` (1,8 s) do buffer.
