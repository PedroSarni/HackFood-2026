# Estado do projeto

> Atualizar a cada ~1h ou depois de entrega importante. Quem terminou o trabalho atualiza.
> Última atualização: 17/10 16h59 por Davi

## Ideia escolhida
Fechada às 16h55. Agente de compras no WhatsApp pra quem não gosta ou não sabe usar app (idosos e pouca familiaridade digital): botões sempre, 3 opções por vez com Mais opções, texto, áudio e foto, várias mensagens seguidas, e repete a compra da semana com 1 toque. Diferenciais: acessibilidade e recorrência, usando o MCP do iFood como agente externo. Ainda a decidir: pedido em grupo e áudio de saída (item B2).

## Pronto
- Regras do time (AGENTS.md), hooks e CI de autoria
- docs/whatsapp.md (Cloud API da Meta, número e token emprestados do handwrite_bot)
- Resumo do MCP do iFood em "regras da api/"
- Agente "HackFood Agent" aprovado no portal do iFood em menos de 1h

## No ar agora (17/10 ~16h40)
- Bot no WhatsApp em MODO DEMO (mock do MCP, `IFOOD_MOCK=1` no secret `hackathon-ifood`): o número já aponta pro
  deploy novo. Pedido completo funciona: login simulado, endereço, busca com 3 cards, "Mais opções", carrinho,
  pagamento, resumo, confirmação, rastreio e lembrete. Quando o 2º agente (o do backend) for aprovado: trocar o secret pelas
  credenciais e tirar o IFOOD_MOCK
- 65 testes passando (`.venv/Scripts/python.exe -m pytest`)

## Em andamento
- Fabio, claim `bot-ifood-agent`: back em Python no Modal, em `src/` (webhook do WhatsApp, buffer de rajadas, Gemini, cliente MCP + OAuth, mock do MCP). Reaproveita o setup do handwrite_bot
- Fabio: 2º agente "Compras pelo WhatsApp" criado às ~16h05 e em análise no iFood (item C1) com redirect no backend publicado (o "HackFood Agent" só tem localhost:8080, que não serve pro login pelo celular)

## Bloqueado ou esperando
- MCP real: o agente do Davi foi aprovado em cerca de 1h, mas POST /token no id.ifood.com.br devolve invalid_client com o secret recém gerado (testado por post, por Basic e sem secret). Levar a um mentor (item A2). O Fabio está criando um 2º agente com redirect no backend (item C1).
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
- [ ] A4 Combinar canal do time e divisão dos entregáveis — Davi
### Produto
- [ ] B1 Regra da ordem de prioridade dos itens (ranking). Davi decide, Fabio implementa em src/bot/ranking.py
- [ ] B2 Decidir se pedido em grupo, áudio de saída e foto entram ou ficam fora — time
### MCP real
- [ ] C1 Credenciais reais funcionando no bot (2º agente do Fabio) — Fabio
- [ ] C2 Primeiro pedido real na conta de teste, sem PIX real — Fabio e Davi
- [ ] C3 Registrar bugs e inconsistências do MCP na seção 8 do contexto-evento.md (contínuo) — todos
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
