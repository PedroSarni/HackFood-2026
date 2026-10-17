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
| `src/shared/ifood_mcp.py` | Cliente do MCP do iFood (JSON-RPC sobre HTTP) + OAuth (login, refresh, revoke) |
| `src/shared/mcp_fake.py` | iFood falso (mesmas tools, dados inventados) para demo/teste sem credencial |
| `src/bot/fluxo.py` | A conversa: a máquina de etapas que conduz o pedido. O coração do bot |
| `src/bot/interpretar.py` | Entende a mensagem: regras rápidas + o prompt/esquema do Gemini |
| `src/bot/ifood.py` | Tradutor entre o formato do MCP e o formato que o fluxo usa |
| `src/bot/ranking.py` | Ordem em que as ofertas aparecem (aguardando a regra do time) |
| `src/bot/rastreio.py` | Acompanha o pedido depois de feito e avisa cada mudança |
| `src/bot/recorrencia.py` | Compra recorrente: lembra a pessoa de pedir de novo |
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
           agendar | fora_do_escopo | nao_entendi
itens      [{termo, quantidade?, tipo_loja, observacao?}]   (quando acao=comprar)
numero     1, 2, 3...                                       (quando escolher/quantidade)
texto      o endereço, quando acao=endereco
```

- `tipo_loja` ∈ MERCADO, RESTAURANTE, FARMACIA, BEBIDAS, PET, LOJA — o modelo classifica
  ("dipirona" → FARMACIA, "pizza" → RESTAURANTE, "pão" → MERCADO).
- **O CPF nunca passa pela IA**: na etapa do CPF o texto é validado só no código (dígitos
  verificadores), e documento não vai pra prompt (exigência da LGPD nos Termos do iFood).

---

## 4. Login do iFood — de onde vem o `.../login/CODIGO`

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
  O bot oferece "deixar no automático" na 2ª compra do mesmo item **ou da mesma categoria**, de
  qualquer loja (X-Bacon numa e Smash Burger noutra = 2º hambúrguer; `categoria()`), ou quando a
  pessoa pede ("todo dia às 18h" = `acao=agendar`, até no meio de um pedido). No dia, o bot manda
  "Podemos pedir aqui pra enviar na sua casa?" com itens, loja, endereço, pagamento e valor da
  última vez. **"Sim, pode pedir" é a confirmação**: refaz o carrinho (`createCart(orderId)`) e
  fecha o pedido na hora; se o total subiu mais de 10%, mostra o resumo antes. Sem o sim, nada é
  pedido nem cobrado. Dentro da janela de 24h o lembrete vai direto; fora dela precisa de template
  aprovado pela Meta. Horário dito ("às 18h") é guardado e respeitado (Brasília).
  Demo: `modal run scripts/modo.py --rapido on` faz o 1º lembrete vir em 1 minuto, seja qual for a
  frequência/horário; a pessoa vê o combinado normal ("todo dia às 18h"), como se o tempo tivesse
  passado (função `lembrete_na_hora`, sem esperar o cron de 15 min).

---

## 10. Regras de negócio (resumo)

- **Nada é comprado sem confirmação explícita** da pessoa (`userConsent`), e a confirmação nunca
  vem da IA.
- **Botão é o caminho principal.** Texto/áudio/foto são entendidos, mas a resposta sempre oferece
  botões. Quem digita o número de uma opção é atendido igual a quem toca.
- **Uma loja por pedido.**
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

---

## 12. Credenciais e modos

| Secret Modal | Para quê |
|---|---|
| `hackathon-whatsapp` | Número, token e verify token da Cloud API da Meta (emprestados do handwrite_bot) |
| `hackathon-ifood` | `IFOOD_CLIENT_ID`, `IFOOD_CLIENT_SECRET` (agente "Compras pelo WhatsApp", aprovado). Sem `IFOOD_MOCK` = modo real |
| `llm-conversor` | `GEMINI_API_KEY` (o mesmo do handwrite_bot) |

- **Modo real** (atual): o bot fala com o iFood de verdade. A pessoa precisa fazer o login real
  (conta iFood própria ou uma conta de teste do portal, que tem OTP na tela).
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
# testes (68, roda em segundos)
.venv\Scripts\python.exe -m pytest

# publicar no Modal
.venv\Scripts\python.exe -m modal deploy -m src.app

# ver os esquemas reais das tools do iFood (precisa de alguém logado)
.venv\Scripts\python.exe -m modal run -m src.app::ferramentas_reais --wa-id 55...

# apontar/desapontar o número (webhook) — ver scripts/virar_webhook.py
```

No ar: `https://fabio-araujo-silva--hackfood-bot.us-east.modal.run` (`/saude`, `/termos`,
`/privacidade`, `/whatsapp` é o webhook).

---

## 14. Limitações conhecidas (entram no entregável 06)

- Cartão não funciona por bot (sem API de tokenização); só PIX e vale.
- O `submitOrder` não devolve código PIX copia-e-cola nem QR.
- Entrega agendada tem timeslot sem ID → só entrega imediata.
- Sem cancelamento/reembolso pela API.
- Mapeamento das opções do item → carrinho é ambíguo (o bot tenta os dois formatos).
- Vários hosts e escopos divergentes entre a doc online e o llms.txt (detalhes em
  `docs/contexto-evento.md` §8).
