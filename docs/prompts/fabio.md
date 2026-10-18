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
