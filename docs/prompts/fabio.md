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
