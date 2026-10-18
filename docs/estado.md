# Estado do projeto

> Atualizar a cada ~1h ou depois de entrega importante. Quem terminou o trabalho atualiza.
> Última atualização: 18/10 11h30 por Davi

## Ideia escolhida
Fechada às 16h55. Agente de compras no WhatsApp pra quem não gosta ou não sabe usar app (idosos e pouca familiaridade digital): botões sempre, 3 opções por vez com Mais opções, texto, áudio e foto, várias mensagens seguidas, e repete a compra da semana com 1 toque. Diferenciais: acessibilidade e recorrência, usando o MCP do iFood como agente externo. Pedido em grupo (kit pra dividir com os amigos) e foto vira pedido já estão no bot (e821eef), assim como a resposta em áudio (51ef4ff) (item B2).

## Pronto
- Regras do time (AGENTS.md), hooks e CI de autoria
- docs/whatsapp.md (Cloud API da Meta, número e token emprestados do handwrite_bot)
- Resumo do MCP do iFood em "regras da api/"
- Agente "HackFood Agent" aprovado no portal do iFood em menos de 1h
- QA do MCP real concluído (conta de teste): achados no contexto-evento.md §8
- Foto vira pedido e kit pra dividir com os amigos (e821eef)
- Resposta por áudio com ElevenLabs, só quando a pessoa pede (51ef4ff)
- OpenRouter de reserva quando o Gemini cai (764c617)
- Sugestão pra fechar o pedido mínimo (123d7c7)
- Carrinho pela fala: "quero esse e pode fechar" vai direto pro checkout (2b5e513)
- Fixes do endereço, complemento/bairro e "cancelar pedido" (d0b0c3c, 59d4abe, 62fefce, 3a13b42)
- Sessão ociosa: 30 min parado no meio de uma pergunta volta pro menu (4797590)
- Dash do Pedro lê o diário do bot ao vivo (Fabio, claim `dash-live-data`, done) e ganhou mascote no perfil (Breno, claim `dash-profile-mascot`, done)
- Vitrine do "oi": primeira mensagem curta com ideias do gosto da pessoa (0b30faa)
- A lista vai pro mercado que tem tudo e sai mais em conta (db33ba9)
- Loja fechada aparece nos testes com "🔒 fechada agora", interruptor `scripts/modo.py --fechadas` (f94bdc6)
- B1: "mudar" digitado no pagamento abre o mudar (e5f3d73)
- B2: "sim"/"não" no resumo com sugestão de acompanhamento pergunta de novo com 3 botões (074bcd0)
- B4: aviso de botão antigo não empilha mais (53e8466)
- Dash de uso do MCP e rastro dos agentes de IA (Davi, claim `dash-agentes-mcp`, done; 051ea08 a 2a348f7)
- Dash de controle dos agentes: crachá, interruptor e modelo por agente (Fabio, claim `dash-agents-control`, done)
- 2º agente "Compras pelo WhatsApp" (Fabio, criado às ~16h05) APROVADO, com redirect no backend publicado (o "HackFood Agent" só tem localhost:8080, que não serve pro login pelo celular)
- Analista Sofia: lê a página do dash e diz qual time mexe no quê (Fabio, 9626e97)
- Botão de insights com IA no dash, por time do iFood (Fabio, claim `dash-ai-insights`, done; 054d7d2)

## Mudou desde as 05h10 de 18/10 (todos com commit)
- Rename para AiFood em marca, textos, docs e código (6490957, 10h26). Os identificadores do Modal seguem `hackfood-*` de propósito (URL fixa do OAuth).
- Confirmação do pedido: toque em "Confirmar pedido" ou um "sim" no resumo; "já pode passar no pix" fecha direto, sem resumo e sem CPF (9e861a3). Por áudio, o 1º "sim" com sugestão ainda pergunta e o seguinte fecha (44b1aad).
- Kit em grupo: o ajuste parte do kit da tela (643c477); receitas por comida e ajuste feito pelo código (ddc2dc2, `src/bot/kit_ajuste.py`); "adiciona tomate" põe tomate (1f8806e); "com 13 amigos" são 13 (326ea19, 0aadc9b); teto do orçamento (71e2001).
- Agentes: Claude Sonnet 5.5 na frente de todos, Gemini de reserva (47d3f17); Vina e Duda no Haiku 5.5 (9ef9ea0); Beto no Fable 5.1 (4ca5e9a) e, 10 min depois, no Opus 5.5 (7f5b635).
- Loja que recusa o pedido mesmo com CPF leva a lista inteira para outra loja (65f6fe8); CPF exigido no item não perde o item nem pede de novo (6a82859).
- Cutucada com 1 min (65a480d); `cfg:cutucar` liga e desliga cutucada e abandono (7ea8fdd).
- Modo palco e catálogo de reserva do MCP (71e2001, 8c86fb4, 5e47d87); o pedido atravessa a troca de iFood sem a pessoa perceber (12eb264).
- Proteção contra o 403 do Akamai: botão de pânico (58e8e1a), freio local, ponte por outro container e aposentadoria do container (a14e210).
- Correções do QA de 18/10 (`docs/qa-18-10.md`): 643c477, 44b1aad, d9c8c71, 180a989, 76a345d, 4143c34, e692cd3 e outras; quantidade na unidade de venda, "12 ovos" = 1 dúzia (e5ebade, a0d2b6c); aviso de status diz qual pedido é (69b0b49).
- Dash: rotinas automáticas (8a68731), insights da Sofia em PDF (ae53a49), sino de alertas (47d3f17).
- Entregáveis 01 a 06 no repo (06e2983, d9e9c7a, e8bf964), `docs/entregaveis/entrega-unica.md` (9238ee2), nome AiFood nos entregáveis (3544a96) e prints do dash B1 a B7 no 04 e na entrega única (1a558b4; imagens em `docs/entregaveis/prints/`).
- Testes rodados em 18/10 após 10h26: 545 no back (pytest) e 54 no dash (Vitest).

## Não confirmado
- Reteste das correções de 18/10 em produção (`docs/qa-18-10.md` pede reteste; resultado não registrado).
- Qual commit está em produção: o `fabio.md` registra deploys até a troca do Beto para o Opus (~09h35), sem hash. O rename 6490957 (10h26) e os commits seguintes não têm deploy registrado.
- Se o mock está ligado ou desligado agora: o último registro é do Fabio, mock religado às ~02h40 (`fabio.md`); depois disso não há registro de troca. O modo palco foi registrado como desligado às ~07h20.
- Se B4 (53e8466) e os fixes das 05h às 06h45 já foram para o ar: dependem do deploy acima.
- Pedidos reais feitos no MCP: só um está registrado (rastreio de ~06h10 a 06h18); quantos e em que conta, não registrado.

## No ar agora (18/10 02h20; desatualizado, ver "Mudou desde as 05h10" e "Não confirmado") — MOCK LIGADO
- Mock ligado de novo às ~02h00 (Fabio, `scripts/modo.py --mock on`, sem deploy); às ~01h45 ele tinha voltado ao iFood real.
  Se a demo roda em mock ou no iFood real: a decidir (H3).
- Deploys depois das 23h00 (bbfd811), segundo docs/prompts/fabio.md: ~01h31 (já com e5f3d73, logo com 99c2c31) e ~02h30 (2af1cf6).
  Há também "deploy feito" na entrada do mercado fechado (f94bdc6); o registro não traz hora nem hash.
- Em produção: follow-up e abandono (99c2c31) e B1 (e5f3d73). B2 (074bcd0) entra no deploy de f94bdc6 só se ele partiu de um
  main que já o tinha: a confirmar com o Fabio. B4 (53e8466) NÃO está em produção, é posterior a todos os deploys registrados.
- Agente "Compras pelo WhatsApp" APROVADO no portal. Credenciais reais no secret `hackathon-ifood`
  (`IFOOD_CLIENT_ID`/`IFOOD_CLIENT_SECRET`, sem `IFOOD_MOCK`). O número já atende pelo deploy novo.
- OAuth verificado de ponta a ponta: o botão "Entrar no iFood" leva ao login REAL do iFood (client,
  escopos `mcp.*` e redirect todos aceitos). Falta só a pessoa logar (conta iFood ou conta de teste do portal).
  Importante: o escopo `openid` NÃO é permitido pro nosso cliente — a string é só `mcp.*`.
- Pedido completo testado no mock (login, endereço, 3 cards, "Mais opções", carrinho, pagamento, resumo,
  confirmação, rastreio, lembrete). Pra demo sem conta iFood, voltar ao mock: `IFOOD_MOCK=1` no secret.
- Como tudo funciona: `docs/como-funciona.md`. 428 testes passando em 18/10 02h20 (`.venv/Scripts/python.exe -m pytest`).

## Em andamento
- Fabio, claim `bot-ifood-agent`: back em Python no Modal, em `src/` (webhook do WhatsApp, buffer de rajadas, Gemini, cliente MCP + OAuth, mock do MCP). Reaproveita o setup do handwrite_bot
- Painel com seletor dados reais ou demonstração (aad024d); diário de prompts em `docs/prompts/` (regra do Fabio, 6bbeb88)
- Claim `bot-ifood-agent` (Fabio) segue ativo; `docs-vivos` (Davi) foi fechado em 18/10
- Teste manual da noite (QA): ver H5 a H12

## Bloqueado ou esperando
- Ordem de prioridade dos itens (ranking): esperando a regra do time; entra só em `src/bot/ranking.py`

## Próximo passo
Ver a Lista do projeto abaixo. Itens A1 a A4 primeiro.

## Horários de corte
- 16h30: ideia fechada e docs no repo
- 19h: fluxo básico (buscar, carrinho, confirmar) rodando, mesmo que em mock
- 06h: começam os entregáveis
- 11h30 de domingo: tudo travado (submissão às 12h30)

## Lista do projeto (fixa: só marque [x] ou acrescente itens, nunca apague)
### Feito
- [x] Docs de contexto no repo e ponteiro no AGENTS.md
- [x] Bot no ar em modo demo com MCP falso, 65 testes
- [x] Agente "HackFood Agent" aprovado no portal do iFood
### Agora (até 18h)
- [x] A1 Registrar a ideia (decisoes.md e estado.md) — Davi
- [ ] A2 Mentor: MCP real (invalid_client), perguntas da seção 7 do contexto-evento.md, e COMO submeter os entregáveis — Davi
- [ ] A3 Testar o bot no WhatsApp como usuário (idoso apressado) e anotar problemas — Davi e time
  - corrigidos 2 bugs achados nos testes: fase endereço prendia a pessoa em loop com "Olá"/"novo pedido" (d0b0c3c) e sessão nunca expirava (4797590)
- [ ] A4 Combinar canal do time e divisão dos entregáveis — Davi
### Produto
- [ ] B1 Regra da ordem de prioridade dos itens (ranking). Davi decide, Fabio implementa em src/bot/ranking.py
- [x] B2 Decidir se pedido em grupo, áudio de saída e foto entram ou ficam fora — time
  - voz.py (stub do Fabio) sugere que áudio de saída pode voltar; confirmar com Fabio
  - entraram: foto e kit em grupo (e821eef), áudio de saída (51ef4ff)
- [ ] B3 (futuro) Mockar cupom e clube, se der tempo — time
### MCP real
- [x] C1 Credenciais reais funcionando no bot (2º agente do Fabio) — Fabio
- [ ] C2 Primeiro pedido real na conta de teste, sem PIX real — Fabio e Davi
- [ ] C3 Registrar bugs e inconsistências do MCP na seção 8 do contexto-evento.md (contínuo) — todos
- [ ] C5 Fabio avaliar 5 pontos do QA no ifood.py — Fabio
### Entregáveis (travar às 11h30 de domingo)
- [x] D1 01 Proposta de Negócio — Davi
- [x] D2 02 Desenho de Solução — a definir
- [x] D3 03 Racional da Experiência — Davi
- [x] D4 04 Interface Visual — a definir
- [x] D5 05 Documento Técnico Resumido — a definir
- [x] D6 06 Feedback sobre os MCPs — Davi
- [ ] D7 Prints A1 a A9 do WhatsApp (ainda não existem) — a definir
- [ ] D8 Print B4 com o painel da conversa aberta (marcador `[PREENCHER]` no 04 e na entrega única) — a definir
- [ ] D9 Decidir o número ou QR de demonstração do WhatsApp (marcador `[PREENCHER]` no 04) — time
- [ ] D10 Formato final da entrega (PDF, Word ou o próprio .md): indefinido — time
### Pitch
- [ ] E1 Roteiro (5 a 8 min) e slides — Davi
- [ ] E2 Roteiro da demo e plano B se o MCP ou a internet cair
- [ ] E3 Respostas às perguntas da banca (3 min) e ensaio cronometrado, 2 vezes
- [ ] E4 Vídeo de reserva da demo, se o MCP ou a internet cair — time
### Higiene
- [ ] F1 Segredos fora do repo; estado.md a cada 1h; /redundancia a cada 2h; cada um na própria conta de IA; Fabio preenche META_APP_SECRET
### Fechamento
- [ ] G1 11h30 tudo travado, 12h30 submissão, 13h pitches
### Pendências da noite
- [ ] H1 Confirmar com o Fabio a versão do deploy que tem os fixes e a foto (fabio.md: deploy das 23h00 do bbfd811)
- [x] H2 Follow-up e carrinho abandonado aos 5 min no app.py (Davi): código em 99c2c31, no ar desde o deploy de ~01h31 (fabio.md). Follow-up era aos 3 min; com 1 min desde o deploy v49 de 18/10 05h53 (65a480d)
- [ ] H3 Decidir antes do pitch se a demo roda em mock ou no iFood real
- [x] H4 Perguntar ao Fabio se o rastreio deve parar quando a pessoa apaga os dados (no mock ele continua): para (4143c34)
- [ ] H5 B3 (alta): carrinho sumiu no meio de uma lista por foto em mock, por volta de 01h43, junto com "botão antigo" no card do pão. Não reproduzido; precisa do diário do número do Davi (01h40 a 01h46) ou reprodução com o mock ligado
- [x] H6 B4 (média): o aviso "botão antigo" empilha a cada toque (repetir_pergunta). Corrigido na main (53e8466), falta deploy
- [ ] H7 M2: no MCP real, "Seu pedido até agora" deu R$ 47,97 com 1 item de R$ 36,99; explicar os R$ 10,98
- [ ] H8 C1: loja fechada hoje diz "Não achei X perto de você, tente escrever de outro jeito"; devia dizer que está fechada
- [ ] H9 O2: no MCP real o carrossel traz 10 cards de uma vez, o D1 promete 3 por vez; confirmar a regra
- [ ] H10 O1/M1/V1: leite com só 3 ofertas no mock; desconto de R$ 5 só em uma loja; vitrine possivelmente chegando depois do pedido
- [ ] H11 U1/U3/U4/U5: botão "Fazer pedido" repete a pergunta; sem voltar no pagamento/CPF; texto digitado não destrava depois do botão antigo; lista da foto sem acento e sem quantidades
- [ ] H13 Reteste em produção das correções de 18/10 (tabela no fim de `docs/qa-18-10.md`) e conferir qual commit está no ar
- [ ] H12 QA ainda por fazer: foto (restante), grupo, áudio, recorrência, reteste de B1 e B2 em produção depois do deploy, relatório final
