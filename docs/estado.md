# Estado do projeto

> Atualizar a cada ~1h ou depois de entrega importante. Quem terminou o trabalho atualiza.
> Última atualização: 17/10 21h18 por Davi

## Ideia escolhida
Fechada às 16h55. Agente de compras no WhatsApp pra quem não gosta ou não sabe usar app (idosos e pouca familiaridade digital): botões sempre, 3 opções por vez com Mais opções, texto, áudio e foto, várias mensagens seguidas, e repete a compra da semana com 1 toque. Diferenciais: acessibilidade e recorrência, usando o MCP do iFood como agente externo. Ainda a decidir: pedido em grupo e áudio de saída (item B2).

## Pronto
- Regras do time (AGENTS.md), hooks e CI de autoria
- docs/whatsapp.md (Cloud API da Meta, número e token emprestados do handwrite_bot)
- Resumo do MCP do iFood em "regras da api/"
- Agente "HackFood Agent" aprovado no portal do iFood em menos de 1h
- QA do MCP real concluído (conta de teste): achados no contexto-evento.md §8

## No ar agora (17/10 ~17h10) — MODO REAL
- Agente "Compras pelo WhatsApp" APROVADO no portal. Credenciais reais no secret `hackathon-ifood`
  (`IFOOD_CLIENT_ID`/`IFOOD_CLIENT_SECRET`, sem `IFOOD_MOCK`). O número já atende pelo deploy novo.
- OAuth verificado de ponta a ponta: o botão "Entrar no iFood" leva ao login REAL do iFood (client,
  escopos `mcp.*` e redirect todos aceitos). Falta só a pessoa logar (conta iFood ou conta de teste do portal).
  Importante: o escopo `openid` NÃO é permitido pro nosso cliente — a string é só `mcp.*`.
- Pedido completo testado no mock (login, endereço, 3 cards, "Mais opções", carrinho, pagamento, resumo,
  confirmação, rastreio, lembrete). Pra demo sem conta iFood, voltar ao mock: `IFOOD_MOCK=1` no secret.
- Como tudo funciona: `docs/como-funciona.md`. 68 testes passando (`.venv/Scripts/python.exe -m pytest`).

## Em andamento
- Fabio, claim `bot-ifood-agent`: back em Python no Modal, em `src/` (webhook do WhatsApp, buffer de rajadas, Gemini, cliente MCP + OAuth, mock do MCP). Reaproveita o setup do handwrite_bot
- Fabio: 2º agente "Compras pelo WhatsApp" (criado às ~16h05) já APROVADO, com redirect no backend publicado (o "HackFood Agent" só tem localhost:8080, que não serve pro login pelo celular)
- Pedro: `Frontend/Rascunho_Dash` (dashboard de analytics, só dados simulados), sem claim ainda
- Rascunho do 06 (Davi): em andamento, fora do repo

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
- [ ] B2 Decidir se pedido em grupo, áudio de saída e foto entram ou ficam fora — time
- [ ] B3 (futuro) Mockar cupom e clube, se der tempo — time
### MCP real
- [x] C1 Credenciais reais funcionando no bot (2º agente do Fabio) — Fabio
- [ ] C2 Primeiro pedido real na conta de teste, sem PIX real — Fabio e Davi
- [ ] C3 Registrar bugs e inconsistências do MCP na seção 8 do contexto-evento.md (contínuo) — todos
- [ ] C5 Fabio avaliar 5 pontos do QA no ifood.py — Fabio
### Entregáveis (travar às 11h30 de domingo)
- [ ] D1 01 Proposta de Negócio — Davi
- [ ] D2 02 Desenho de Solução — a definir
- [ ] D3 03 Racional da Experiência — Davi
- [ ] D4 04 Interface Visual — a definir
- [ ] D5 05 Documento Técnico Resumido — a definir
- [ ] D6 06 Feedback sobre os MCPs — Davi
### Pitch
- [ ] E1 Roteiro (5 a 8 min) — Davi
- [ ] E2 Roteiro da demo e plano B se o MCP ou a internet cair
- [ ] E3 Respostas às perguntas da banca (3 min) e ensaio cronometrado, 2 vezes
### Higiene
- [ ] F1 Segredos fora do repo; estado.md a cada 1h; /redundancia a cada 2h; cada um na própria conta de IA; Fabio preenche META_APP_SECRET
### Fechamento
- [ ] G1 11h30 tudo travado, 12h30 submissão, 13h pitches
