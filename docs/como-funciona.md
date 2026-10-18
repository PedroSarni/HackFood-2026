# Como o bot funciona (de ponta a ponta)

> Documentação do funcionamento do sistema em `src/`. Para o contexto do evento e os fatos do
> MCP, veja `docs/contexto-evento.md`. Para a conexão do WhatsApp, `docs/whatsapp.md`.

O produto é um **assistente de compras no WhatsApp**: a pessoa conversa (texto, áudio ou foto),
e o bot faz o pedido no iFood por ela. O público-alvo é quem tem dificuldade com aplicativos
(idosos, baixa familiaridade com celular), então **tudo que dá é resolvido com botão**, as
frases são curtas e nada é comprado sem a pessoa confirmar.

**Tese do projeto: a IA entende, o código garante.** O Gemini só transforma a mensagem numa
*intenção* estruturada. Quem decide o que fazer, chama o iFood e conduz o pedido passo a passo
é o código — nunca a IA. Confirmar a compra, em especial, jamais parte do modelo.

---

## 1. O caminho de uma mensagem

```
A pessoa manda no WhatsApp
        │
        ▼
Meta (Cloud API)  ──POST──►  /whatsapp        (webhook, src/app.py)
                                  │  responde 200 na hora (senão a Meta desliga o webhook)
                                  │  guarda a mensagem na fila da pessoa
                                  ▼
                           rodada(wa_id)        (src/app.py, função Modal)
                                  │  junta a rajada de mensagens (src/shared/buffer.py)
                                  ▼
                           Bot.processar(lote)   (src/bot/fluxo.py)
                              ├─ botão  ─────────► caminho determinístico (sem IA)
                              ├─ texto/áudio/foto► regras rápidas → Gemini (src/bot/interpretar.py)
                              │                     → intenção {acao, itens, numero, ...}
                              └─ chama o iFood (src/bot/ifood.py → src/shared/ifood_mcp.py
                                                 ou o mock src/shared/mcp_fake.py)
                                  │
                                  ▼
                           respostas com botões    (src/shared/whatsapp.py → Graph API da Meta)
```

Cada peça é trocável: em produção o iFood é o MCP real; em teste/demo é o mock, com a mesma
interface. O bot não sabe a diferença.

### Arquivos

| Arquivo | O que faz |
|---|---|
| `src/app.py` | App Modal: webhook do WhatsApp, rotas do login do iFood, páginas, e as funções de fundo (conversa, rastreio, lembretes) |
| `src/shared/whatsapp.py` | Cliente da Cloud API da Meta: manda texto/botões/lista/cards/link, "digitando...", baixa áudio/foto |
| `src/shared/buffer.py` | Junta a rajada de mensagens de cada pessoa antes de responder |
| `src/shared/llm.py` | Gemini: texto/áudio/foto entram, JSON garantido sai (com modelo reserva) |
| `src/shared/scribe.py` | Scribe (ElevenLabs): o áudio vira texto e segue o caminho de uma mensagem escrita; desligado, o Gemini ouve |
| `src/shared/ifood_mcp.py` | Cliente do MCP do iFood (JSON-RPC sobre HTTP) + OAuth (login, refresh, revoke) |
| `src/shared/mcp_fake.py` | iFood falso (mesmas tools, dados inventados) para demo/teste sem credencial |
| `src/bot/fluxo.py` | A conversa: a máquina de etapas que conduz o pedido. O coração do bot |
| `src/bot/interpretar.py` | Entende a mensagem: regras rápidas + o prompt/esquema do Gemini |
| `src/bot/ifood.py` | Tradutor entre o formato do MCP e o formato que o fluxo usa |
| `src/bot/ranking.py` | Ordem em que as ofertas aparecem (aguardando a regra do time) |
| `src/bot/rastreio.py` | Acompanha o pedido depois de feito e avisa cada mudança |
| `src/bot/recorrencia.py` | Compra recorrente: lembra a pessoa de pedir de novo |
| `src/bot/foto.py` | Foto vira pedido: o prompt/esquema que diz se é comida, lista, produto ou outra coisa |
| `src/bot/grupo.py` | Dividir com os amigos: monta o kit numa loja só e faz a conta do "por pessoa" |
| `src/bot/textos.py` | Tudo que o bot fala, num lugar só |
| `src/bot/contexto.py` | Junta as peças (WhatsApp, iFood, Gemini, armazém) num objeto só |
| `src/web/paginas.py` | Páginas HTML: termos, privacidade, exclusão e as telas de login |

---

## 2. Rajada de mensagens (o detalhe que faz a diferença pro público)

Quem tem pouca prática manda "oi", "quero", "pão", "e leite" em quatro mensagens separadas — e
continua digitando enquanto o bot pensa. Responder cada uma geraria uma bagunça de respostas
cruzadas.

Solução (`src/shared/buffer.py`): o webhook põe cada mensagem numa fila por pessoa e dispara uma
*rodada*. A rodada espera um silêncio curto; se nesse meio-tempo chegou outra mensagem, ela
desiste — quem responde é a rodada da mensagem mais nova, que então pega **tudo** que estava na
fila de uma vez. Uma trava garante que só uma rodada processe por pessoa de cada vez, então nunca
sai resposta duplicada.

- O tempo de silêncio depende do tipo: botão ~0,6 s (toque é decidido), "oi" curto ~4 s (quase
  sempre vem mais), texto normal ~2,5 s, com teto de 9 s desde a primeira mensagem.
- As mensagens são reordenadas pelo horário da Meta antes de processar (a Meta às vezes entrega
  fora de ordem).

---

## 3. Entendendo a mensagem (src/bot/interpretar.py)

Duas camadas, barata primeiro:

1. **Regras rápidas** (sem IA): cobrem o que mais aparece — "sim"/"s"/"pode", "não", "oi", um
   número digitado ("2", "o segundo", "meia dúzia"), "menu", "ajuda", "parar lembrete". Resposta
   instantânea e sem custo.
2. **Gemini** (quando as regras não bastam): recebe a mensagem (e o contexto da etapa atual) e
   devolve **só** um JSON no formato fixo abaixo. Modelo principal `gemini-3.1-flash-lite` (~1 s);
   se falhar ou demorar, cai no reserva `gemini-3.8-flash`; se os dois falharem, o fluxo ainda
   tenta buscar pelo texto cru.

Intenção que o modelo devolve (`ESQUEMA` em `interpretar.py`):

```
acao       comprar | mais_opcoes | escolher | sim | nao | quantidade | endereco |
           ver_pedido | finalizar | tirar_item | cancelar | acompanhar | repetir |
           ajuda | saudacao | agradecer | sair | apagar_dados | parar_lembrete |
           agendar | grupo | fora_do_escopo | nao_entendi
itens      [{termo, quantidade?, tipo_loja, observacao?}]   (quando acao=comprar; no grupo, o principal 1º)
numero     1, 2, 3...                                       (escolher/quantidade; no grupo, quantas pessoas)
texto      o endereço, quando acao=endereco; no grupo, só a restrição ("sem refri")
```

- `tipo_loja` ∈ MERCADO, RESTAURANTE, FARMACIA, BEBIDAS, PET, LOJA — o modelo classifica
  ("dipirona" → FARMACIA, "pizza" → RESTAURANTE, "pão" → MERCADO).
- **O CPF nunca passa pela IA**: na etapa do CPF o texto é validado só no código (dígitos
  verificadores), e documento não vai pra prompt (exigência da LGPD nos Termos do iFood).

---

## 4. Login do iFood — de onde vem o `.../login/CODIGO`

> **A URL do bot é fixa.** O callback (`.../ifood/callback`) está cadastrado no portal e a edição está
> bloqueada: não mude o nome do app, o label, o workspace nem a região no Modal (`AGENTS.md` §0.0).

Quando o bot precisa que a pessoa entre na conta iFood, ele manda um botão "Entrar no iFood"
cujo link é `https://<nosso-backend>/login/<codigo>`.

- O `<codigo>` (ex.: `Prl3r8be-YoCgdiN`) é **gerado por nós** a cada toque
  (`novo_link_login` em `src/app.py`): é aleatório, de uso único, aponta para o número de
  WhatsApp da pessoa e vale 30 minutos. **Não é do iFood** — é a nossa URL no Modal.
- Ao abrir o link (`GET /login/<codigo>`), no **modo real** o backend gera o par PKCE, guarda o
  `code_verifier` no servidor e redireciona a pessoa para o **login de verdade do iFood**
  pelo login web (`https://id.ifood.com.br/authorize`, sem OneLink do app), pedindo os escopos
  `mcp.*`. A pessoa entra na conta dela e autoriza.
- O iFood então volta para `GET /ifood/callback?code=...&state=...`. O backend troca o `code`
  pelos tokens (`access_token` ~1 h, `refresh_token` ~30 dias), guarda-os e avisa a pessoa no
  WhatsApp ("Pronto, você entrou!") retomando o que ela tinha pedido.
- No **modo demo**, em vez do iFood, aparece a nossa tela de consentimento (`paginas.login_demo`,
  claramente marcada "modo demonstração", sem pedir senha) e o "Permitir e entrar" simula o login.

Fluxo OAuth (`src/shared/ifood_mcp.py`): Authorization Code + PKCE (S256), cliente confidencial
(client_secret no backend). **Importante:** o escopo `openid` **não** é permitido para o nosso
cliente — a string de escopos é só `mcp.*` (confirmado no endpoint real). O token é renovado 5
min antes de expirar; o refresh rotaciona (guardamos sempre o novo).

---

## 5. De onde vem o endereço de entrega

O endereço **mora na conta iFood da pessoa**, não no nosso banco. O fluxo (`garantir_endereco`
em `src/bot/fluxo.py`) segue a orientação da própria API:

1. `listAddresses` traz os endereços salvos, com dados de hábito (qual é o último usado, o mais
   usado em 30 dias). A doc manda:
   - **1 endereço** → usa direto e avisa pelo apelido, sem perguntar.
   - **vários, com histórico** → sugere o provável e **confirma numa pergunta** ("Entrego em
     *Casa*?").
   - **vários, sem histórico** → mostra as opções pela etiqueta (Casa, Trabalho).
   - **nenhum** → pede o endereço e salva na conta.
   Quando a mensagem tem **CEP**, ele é resolvido antes (`src/shared/geocoder.py`: BrasilAPI, cai pro
   ViaCEP) e o iFood recebe `Rua X, 123 - Bairro, Cidade - UF, CEP`: CEP solto deixa o geocode do iFood
   perdido (`01310-100, 1578` já deu Canadá). Texto com nome de rua vai direto, porque o iFood entende
   bem mesmo bagunçado. A pessoa não vê nada disso; se não resolver, vai o texto original.
2. Endereço novo usa `createAddress` em dois passos (regra do iFood): primeiro o texto livre
   vira uma lista de *candidatos* (geocodificação, sem salvar nada); a pessoa escolhe; se o
   bairro não veio, o bot pergunta; aí confirma com o `candidateId` + complemento + bairro, e o
   endereço é salvo. (O bairro vai no campo dele, nunca no complemento.)
3. A busca precisa de **latitude/longitude**, que vêm no `coordinates` do endereço. Quando o
   `listAddresses` devolve um endereço sem coordenadas, o bot geocodifica o texto só para pegar
   lat/long (sem criar nada).

---

## 6. Busca e as "3 opções com foto"

- `searchOffers` recebe **só o termo descritivo** ("pão"), e o resto vai em refinamentos
  (`merchantType`, `onlyOpen`, a loja quando o carrinho já começou). Regra do iFood:
  qualificador como "barato"/"perto" nunca vai na query.
- O bot busca **uma vez** (até 25 itens) e guarda a lista inteira. Mostra os 3 primeiros como
  **cards com foto + botão "Quero esse"**, e um botão **"Mais opções"**.
- **"Mais opções" NÃO busca de novo**: mostra os próximos 3 da mesma lista já carregada (índice
  3, 4, 5...). Só quando a lista acaba é que ele pede a página seguinte ao iFood. Isso deixa
  rápido e barato (pedido explícito do time).
- A pessoa pode **tocar** em "Quero esse" ou **digitar o número** ("2", "o do meio") — o código
  aceita os dois.

A **ordem** em que as ofertas aparecem fica em `src/bot/ranking.py`, isolada num único ponto.
Hoje é neutra (tira indisponível e repetido, mantém a ordem do iFood); entra aqui a
[ORDEM DE PRIORIDADE] do time quando ela for definida.

---

## 7. Montando o carrinho

- Escolhido o item, `getItem` traz as opções obrigatórias (tamanho da pizza, etc.). O bot
  pergunta uma de cada vez e só então a quantidade.
- `createCart` (primeiro item) ou `addItemToCart` (demais). O carrinho é de **uma loja só**; um
  item de outra loja vira outro pedido depois.
- As opções do item viram o campo `options` do carrinho. O mapeamento exato não está claro na
  doc, então o bot tenta um formato (modo A) e cai sozinho no outro (modo B) se o iFood recusar.

---

## 8. Fechando o pedido (a parte sensível)

Sequência obrigatória do iFood, que o fluxo (`finalizar`) respeita:

1. **Entrega**: `getCartDeliveryMethods` → `setCartDelivery`. O bot escolhe sozinho a entrega
   padrão (uma pergunta a menos) e mostra prazo e taxa no resumo. (Só entrega em casa; retirada e
   agendamento ficam de fora.)
2. **Pagamento**: `listPaymentMethods` → `setCartPayment`. Só **PIX e vales** — cartão exige um
   `cardTokenId` que a API nunca fornece, então não é oferecido. Repete a forma da última vez.
3. **Cupom**: aplica sozinho o melhor que existir (desconto nunca atrapalha).
4. **CPF**: pega da conta iFood se tiver; senão pergunta uma vez (com opção "Sem CPF"). Validado
   no código.
5. **Resumo**: `getCart` confirma os números, e o bot mostra tudo (itens, entrega, pagamento,
   endereço, total) com os botões **Confirmar / Mudar / Cancelar**.
6. **`submitOrder(userConsent=true)`** — só aqui o pedido é feito, **e só depois do toque em
   Confirmar** (ou "sim" na tela do resumo). Toque duplo não gera dois pedidos (trava).

---

## 9. Depois do pedido

- **Rastreio** (`src/bot/rastreio.py`): o backend consulta `trackOrder` no ritmo que o próprio
  iFood indica (`agentHints.retryMessage`) e para quando ele diz (`pollingStop`). Cada mudança de
  status vira uma mensagem no WhatsApp ("saiu pra entrega", "o entregador chegou"). Isso resolve
  a falta de notificação automática da API.
- **Recorrência** (`src/bot/recorrencia.py`): o MCP não tem recorrência nativa, então ela é nossa.
  O bot oferece "deixar no automático" na 2ª compra do mesmo item **ou da mesma categoria** (só na 2ª,
  e um "Não precisa" segura a oferta por uma semana), de
  qualquer loja (X-Bacon numa e Smash Burger noutra = 2º hambúrguer; `categoria()`), ou quando a
  pessoa pede ("todo dia às 18h" = `acao=agendar`, até no meio de um pedido). Se ela diz **o que**
  quer ("todo dia às 7h, dois pães"), o automático é disso: o bot monta o pedido uma vez com ela (loja
  e produto) e guarda como **modelo**, sem pedir agora; no dia o lembrete monta o carrinho do modelo
  (`createCart` com loja e itens). Sem dizer o quê, oferece o último pedido. No dia, o bot manda
  "Podemos pedir aqui pra enviar na sua casa?" com itens, loja, endereço, pagamento e valor da
  última vez. **"Sim, pode pedir" é a confirmação**: refaz o carrinho (`createCart(orderId)`) e
  fecha o pedido na hora; se o total subiu mais de 10%, mostra o resumo antes. Sem o sim, nada é
  pedido nem cobrado. Dentro da janela de 24h o lembrete vai direto; fora dela precisa de template
  aprovado pela Meta. Horário dito ("às 18h") é guardado e respeitado (Brasília).
  Demo: `modal run scripts/modo.py --rapido on` faz o 1º lembrete vir em 1 minuto, seja qual for a
  frequência/horário; a pessoa vê o combinado normal ("todo dia às 18h"), como se o tempo tivesse
  passado (função `lembrete_na_hora`, sem esperar o cron de 15 min).

---

## 9.1 Foto vira pedido (src/bot/foto.py)

Foto mandada **em qualquer momento**, até como 1ª mensagem e antes do login, é pedido. O Gemini olha a foto
junto com a legenda e o que veio na mesma rajada (até 4 fotos; "documento" de imagem ou PDF também vale) e
diz o que ela é:

- **Comida** (lanche, pizza, prato, foto de cardápio): o bot comenta e pergunta *"Quer que eu procure algo
  parecido?"* (botões `foto:sim:<id>` / `foto:nao:<id>`, ou "sim" escrito). Com o sim, busca os
  `parecidos` que o modelo sugeriu, do mais parecido pro mais genérico ("x-bacon", "hambúrguer"), no máximo 3
  buscas, e junta tudo num carrossel só. Legenda que já é pedido ("quero isso", "me vê 2 desse") pula a
  pergunta e a quantidade da legenda já vale; legenda com pessoas ("pra mim e mais 3") vira o kit da §9.2.
  As duas coisas também são pegas por regra no código (`QUER_ISSO`, `pessoas_em`), porque o modelo às vezes
  não marca.
- **Lista de compras** (papel, bilhete, print) ou **produto** (caixa de remédio, pacote): vira a lista do
  pedido, igual a uma lista escrita (um item de cada vez). No meio do endereço, a lista espera o endereço
  terminar (vira o `pendente`).
- **Outra coisa**: comenta e volta pra onde a pessoa estava. Se veio texto pedindo algo junto ("quero ração
  pra ele" + foto do gato), o pedido escrito vale.
- **Etapa do CPF**: a foto nem é aberta nem vai pra IA (pode ser o documento). Documento pessoal em qualquer
  etapa vira "outro" e nada dele é transcrito nem vai pro log.
- O id no botão (`<id>`) impede que o "Sim" de uma foto antiga busque os parecidos de uma foto nova.

## 9.2 Dividir com os amigos: o kit em grupo (src/bot/grupo.py)

"Quero lanchar em 5 pessoas hambúrguer", "pizza pra 4 dividindo", "eu e mais 3 vamos rachar uma pizza" =
`acao=grupo`. O número de pessoas conta quem escreve ("com 4 amigos" = 5). Falta algo? O bot pergunta só o
que falta (quantas pessoas, com botões 2/4/6 ou o número escrito; ou o que querem comer). Mais de 30 pessoas
pede outro número; 1 pessoa vira pedido normal.

Como o kit é montado, **sempre numa loja só** (o iFood fecha um pedido por loja):

1. busca o principal e agrupa as ofertas por loja, na ordem do iFood (guardado pro **🔄 Outra loja**, que
   troca de loja sem buscar de novo);
2. abre os principais da loja (`getItem`) e já escolhe as opções obrigatórias pelo código: pizza pra 3+
   pessoas vai **grande**, o que bate com o pedido ("coca") vem antes;
3. busca na mesma loja o que acompanha (`combina.py`: refri e batata pro lanche) e o que pediram junto
   ("com coca"); bebida alcoólica só se pedirem;
4. **o Gemini decide a composição** (1 lanche por pessoa variando sabor, pizza grande serve ~3, refri de 2
   litros pra cada ~4, batata pra cada ~3, o que pediram entra sempre, respeita "sem refri", "mais barato");
   se ele falhar ou devolver bobagem, uma regra fixa monta o kit (`kit_padrao`);
5. **o código faz a conta**: preço × quantidade + taxa de entrega da loja, e o **por pessoa arredondado pra
   cima no centavo** (5 × R$ 36,42 cobre R$ 182,09). A fala do modelo nunca traz valor em reais.

O kit aparece com *✅ Quero esse kit*, *🔄 Outra loja* (só se houver outra) e *❌ Não quero*; texto livre
ajusta ("sem refri", "agora somos 6", "troca por guaraná", "na verdade quero pizza" = outro kit). Só no
"Quero esse kit" o carrinho é criado (`createCart` com todas as linhas e opções); se já havia pedido de
outra loja, o kit avisou que troca, e da mesma loja, soma. Daí é o pedido de sempre, e o **"👥 R$ X por
pessoa"** aparece no total, no resumo e no "Pedido feito". "Vamos dividir em 3" com um pedido já montado só
liga o "por pessoa" nele. O iFood cobra uma conta só: o bot diz quanto dá pra cada, não divide o pagamento.

Validação contra o Gemini de verdade (só Gemini, nada de iFood): `modal run scripts/validar_foto_grupo.py`.

---

## 10. Regras de negócio (resumo)

- **Nada é comprado sem confirmação explícita** da pessoa (`userConsent`), e a confirmação nunca
  vem da IA.
- **O que a pessoa diz manda; botão é atalho.** Em qualquer etapa a mensagem (texto ou áudio) é
  interpretada antes de ser encaixada na etapa: se é outro assunto, o bot muda de função (pedido no meio
  do endereço vira o pedido, "cancelar" cancela, papo é respondido e a pergunta volta). A resposta sempre
  oferece botões, mas só os que levam a algo ("Meu pedido" só com pedido feito). Quem digita o número de
  uma opção é atendido igual a quem toca. Nada em inglês chega na tela.
- **Escolha falada adiciona certeiro.** Com os cards na tela, "quero esse", "essa tá boa", "a de
  calabresa grande" escolhem o card (pelo número, pelo único da tela ou pelo nome) sem perguntar
  quantidade (a dita, senão 1) nem opção (a dita, senão a padrão da loja). "Pode fechar" junto vai
  direto pro fim do checkout: total, pagamento e uma sugestão do que acompanha. Pagamento dito antes
  ("no pix") não é perguntado de novo. Número solto ("2") continua igual a tocar o botão.
- **Pergunta sobre o pedido é respondida, em qualquer etapa.** "Qual o código de entrega?" (reconhecido
  até sem o Gemini), "quanto deu?", "o que eu pedi?", "como paguei?", "pra onde vai?" respondem o que
  perguntaram, e a pessoa volta pra etapa em que estava (endereço, cards, pagamento...). O pedido feito
  guarda código de entrega, pagamento e endereço pra isso, e o Gemini sabe qual foi o último pedido.
  "A primeira foto", "o último" escolhem pela posição ("segunda-feira" não). CPF dito antes da hora
  fica guardado pra nota e nunca vai pro Gemini.
- **Status inteiro.** "Tá chegando?", "cadê meu pedido?", "o entregador chegou?" respondem onde o pedido
  está, quando chega em horário ("entre 23h46 e 23h56", da hora do pedido + o tempo da loja), loja,
  número, código de entrega, o que vem e o total, com *Atualizar status*. Quem já pediu vê *Fazer novo
  pedido* no lugar de *Fazer pedido*.
- **A lista vai pra loja que tem tudo.** Pedido com 2+ itens (lista escrita, falada ou de foto, e também
  "uma pizza e uma coca") busca tudo antes (uma busca por item e UM filtro do Gemini pra lista toda: um por
  item estourava a cota por minuto da chave) e escolhe a loja que tem TODOS os itens; entre essas, a de menor
  conta (o mais barato de cada item x a quantidade + a entrega; empate vai pela nota e pelo tempo). Nenhuma
  com tudo: a que tem mais, dizendo o que fica de fora (isso vai pro fim da lista). O iFood fecha um pedido
  por loja, então a loja é escolhida antes do 1º item (`src/bot/melhor_loja.py`). *Trocar de loja* (botão
  nos cards ou "tem outro mercado?") mostra as outras com quanto sai e leva o carrinho junto, pelo
  equivalente da loja nova; *Continuar aqui* volta. O kit em grupo usa a mesma conta: "pizza pra 10 com
  coca" vai pra pizzaria que tem Coca, a mais em conta.
- **Uma loja por pedido.**
- **Pedido mínimo não trava ninguém.** O aviso de mínimo (e o "O que mais você quer?" abaixo dele)
  vem com **💡 Me sugere algo**: na loja do carrinho, o bot oferece 1º o que acompanha o pedido
  (refri pro lanche, manteiga pro pão: `src/bot/combina.py`, mais o que o Gemini sugerir), depois o
  que a pessoa costuma comprar (histórico `hist:`), depois algo parecido com o carrinho, e quem fecha
  o mínimo sozinho aparece primeiro. Remédio nunca entra como sugestão. "Me sugere", "algo que complete esse valor" e afins caem
  na sugestão mesmo com o Gemini fora (`pede_sugestao`, sem IA).
- **Pagamento: só PIX e vales** (limitação da API para cartão).
- **O CPF e documentos não passam pela IA.**
- **"Mais opções" reaproveita a lista já buscada** a partir do 3º item.
- **O bot só fala de pedido.** Assunto fora disso recebe uma recusa educada e volta pro pedido
  (também por causa da política da Meta contra "chatbot de IA genérico").
- **Mensagem proativa exige template** aprovado (janela de 24h da Meta).
- **LGPD**: "sair" desconecta a conta iFood; "apagar meus dados" apaga tudo o que guardamos.

---

## 11. O estado de cada pessoa

Tudo que é de uma pessoa fica num dicionário (`modal.Dict` chamado `hackfood-estado`), em chaves
com o número dela:

| Chave | O que guarda |
|---|---|
| `u:{wa_id}` | O estado da conversa: etapa atual, carrinho, endereço, lista de ofertas, última pergunta, pedidos feitos, nome |
| `tok:{wa_id}` | Os tokens OAuth do iFood (access + refresh) |
| `login:{codigo}` | Um pedido de login pendente (aponta pro wa_id, 30 min) |
| `oauth:{state}` | O `code_verifier` do PKCE durante o login |
| `visto:{mid}` | Dedup: a Meta reenvia a mesma mensagem em retry |
| `ult:` / `prim:` / `trava:` | Controle da rajada de mensagens |

A etapa atual (`u['fase']`) é o que o fluxo usa pra saber o que fazer com a próxima mensagem:
`inicio`, `pedido`, `endereco`, `escolhendo`, `quantidade`, `opcao`, `mais`, `pagamento`, `cpf`,
`confirmar`, `acompanhando`, `recorrencia`, etc.

Quem cala: rodada que termina com pergunta aberta ou itens no carrinho dispara `pessoa_calada` (`src/app.py`). Aos 3 min (`FOLLOWUP_SEG`)
o bot cutuca uma vez ("Ainda está por aí?" + a pergunta da etapa); aos 5 min (`ABANDONO_SEG`), ainda calada e com itens, esquece o carrinho
(só o local, sem chamar o iFood) e volta ao menu, até no resumo. Nada disso muda `u['ultima_msg']`: a volta depois de 30 min (`IDLE_MAX`) segue igual.

---

## 12. Credenciais e modos

| Secret Modal | Para quê |
|---|---|
| `hackathon-whatsapp` | Número, token e verify token da Cloud API da Meta (emprestados do handwrite_bot) |
| `hackathon-ifood` | `IFOOD_CLIENT_ID`, `IFOOD_CLIENT_SECRET` (agente "Compras pelo WhatsApp", aprovado). Sem `IFOOD_MOCK` = modo real |
| `hackathon-gemini` | `GEMINI_API_KEY` (key própria do HackFood; o `llm-conversor` do handwrite_bot não é mais usado aqui) |
| `hackathon-elevenlabs` | `ELEVENLABS_API_KEY` do Scribe (`PREENCHER` = desligado: o áudio vai pro Gemini, como antes) |

- **Modo real** (atual): o bot fala com o iFood de verdade. A pessoa precisa fazer o login real
  (conta iFood própria ou uma conta de teste do portal, que tem OTP na tela).
- **Mock no ar desde 17/10 ~21h25**: o iFood real cai muito por firewall, então a demo roda no mock.
  Liga e desliga sem deploy: `scripts/modo.py --mock on|off`. O mock é consistente de propósito:
  pedido mínimo por loja (o mesmo na loja e no carrinho), lanchonete, pizzaria, cantina e mercados com
  o que acompanha (refri, suco, batata, sobremesa), e busca que ignora "de"/"com" e põe na frente quem
  tem todas as palavras.
- **Lojas fechadas na busca** (pros testes de madrugada): `scripts/modo.py --fechadas on|off`, sem deploy.
  A busca para de mandar `onlyOpen` e a loja fechada aparece depois das abertas, como se estivesse
  aberta (sem aviso no card: é só teste). Fechar o pedido nela ainda depende do iFood: se ele recusar, o bot oferece outra loja.
- **Modo demo**: ligar com `IFOOD_MOCK=1` no secret `hackathon-ifood`. O iFood vira o mock e o
  login é simulado. Útil pra demonstrar sem depender de uma conta iFood.

```powershell
# voltar pro modo demo:
.venv\Scripts\python.exe -m modal secret create hackathon-ifood IFOOD_CLIENT_ID=... IFOOD_CLIENT_SECRET=... IFOOD_MOCK=1 --force
# (ou, mais simples, manter os dois secrets e trocar só o IFOOD_MOCK)
```

---

## 13. Rodar, testar, publicar

```powershell
# testes (rodam em segundos)
.venv\Scripts\python.exe -m pytest

# publicar no Modal
.venv\Scripts\python.exe -m modal deploy -m src.app

# ver os esquemas reais das tools do iFood (precisa de alguém logado)
.venv\Scripts\python.exe -m modal run -m src.app::ferramentas_reais --wa-id 55...

# apontar/desapontar o número (webhook) — ver scripts/virar_webhook.py
```

No ar: `https://fabio-araujo-silva--hackfood-bot.us-east.modal.run` (`/saude`, `/termos`,
`/privacidade`, `/whatsapp` é o webhook).

### 13.1 O painel (dash do time)

O bot anota um diário (`src/shared/painel.py`, modal.Dict `hackfood-painel`) com espiões na borda; o fluxo
não sabe que existe e o registro nunca derruba o bot. Tipos de evento: `entrada`, `saida`, `mcp` (tool,
ok, ms, erro, resumo) e `ia` (agente, modelo que respondeu, se caiu pro reserva, ms, ok/erro e só contagens:
a ação entendida, o tipo da foto, quantos itens). Texto da pessoa, endereço, telefone e CPF não entram no `ia`.
Agentes de IA: entendimento, foto, kit em grupo, relevância/sugestão, tutor, voz (roteiro + ElevenLabs) e
ouvido (Scribe). Follow-up, recorrência e vitrine são **regras** sem IA, reconhecidas pela mensagem que mandaram.

O servidor local (`python -m src.painel.servidor`, só em 127.0.0.1) lê o diário e **agrega lá**: o navegador
recebe só o resumo e a conversa aberta (`/api/mcp`, `/api/agentes`, `/api/equipe`, `/api/ao-vivo`). No dash
(`Frontend/Rascunho_Dash`, `npm run dev`) o menu é **Agentes → Uso do MCP → Dinheiro → Conversas**. As outras
telas ficam em "Mais análises". "Agentes" é a 1ª tela e tem três partes:
- o palco ao vivo, com cada passo do diário virando um recado entre cliente, Maestro, agente e iFood;
- os cards de desempenho, com filtros;
- a ficha de cada agente: modelo, system prompt, keys e interruptor.

A fonte "Demonstração" é simulada e vem sempre com esse rótulo.

### 13.2 O time de agentes: como melhorar um agente sem mexer nos outros

Cada agente tem um arquivo em `src/agentes/<id>.py`: Lia (entendimento), Íris (foto), Duda (relevância), Beto
(kit em grupo), Tungs (tutor), Vina (voz) e Otto (ouvido). O arquivo guarda:
- o crachá do agente (nome, cargo, bordão);
- o plano B, ou seja, o que o bot faz sem ele;
- onde fica o prompt;
- **a fila de modelos só dele**.

Quem orquestra é o código (`src/bot/fluxo.py`, o "Maestro"). Os agentes não se chamam entre si.

- **Trocar só o modelo de um agente** (ex.: a leitura de foto errando): em `src/agentes/foto.py`, preencha
  `modelos=[('gemini-3.8-flash', 12.0, 'low'), ...]` e faça o deploy. Sem deploy, há dois caminhos:
  - o secret `AGENTE_FOTO_MODELOS="modelo:prazo:pensamento,..."`;
  - a ficha da Íris no dash, em "Modelo principal". Vale na próxima mensagem e o resto da fila vira reserva.
- **Mexer no prompt:** o prompt fica junto da lógica, em `src/bot/<módulo>.py` (`SISTEMA`). A ficha mostra a
  versão (hash) do prompt daqui e a do que está no ar, e avisa quando falta deploy.
- **Desligar um agente por um tempo:** use o interruptor na ficha. Fica no armazém (`cfg:agentes`), sem deploy.
  O agente desligado nem é chamado: o fluxo recebe um `ErroLLM` e segue pelo plano B de sempre. O dash conta
  isso como "pulo", não como erro.
- **Keys:** o bot publica a cada 5 min (`cfg:agentes_ar`) quais keys estão configuradas, só com os 4 últimos
  caracteres. A key inteira nunca sai do Modal.
- **Agente novo:** crie `src/agentes/<id>.py` com a `FICHA` e acrescente o módulo em `_carregar()`
  (`src/agentes/__init__.py`). O roteador reconhece o agente pelo system prompt.

---

## 14. Limitações conhecidas (entram no entregável 06)

- Cartão não funciona por bot (sem API de tokenização); só PIX e vale.
- O `submitOrder` não devolve código PIX copia-e-cola nem QR.
- Entrega agendada tem timeslot sem ID → só entrega imediata.
- Sem cancelamento/reembolso pela API.
- Mapeamento das opções do item → carrinho é ambíguo (o bot tenta os dois formatos).
- Vários hosts e escopos divergentes entre a doc online e o llms.txt (detalhes em
  `docs/contexto-evento.md` §8).
