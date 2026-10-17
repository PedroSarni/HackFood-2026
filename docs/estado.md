# Estado do projeto

> Atualizar a cada ~1h ou depois de entrega importante. Quem terminou o trabalho atualiza.
> Última atualização: 17/10 15h50 por Davi

## Ideia escolhida
- Ainda não fechada. Proposta em votação: agente de compras no WhatsApp para quem não gosta de app (acessibilidade), com compra recorrente (repetir a semana com 1 toque) e foto da lista -> carrinho

## Pronto
- Regras do time (AGENTS.md), hooks e CI de autoria
- docs/whatsapp.md (Cloud API da Meta, número e token emprestados do handwrite_bot)
- Resumo do MCP do iFood em "regras da api/"
- Agente "HackFood Agent" registrado no portal do iFood

## No ar agora (17/10 ~18h)
- Bot no WhatsApp em MODO DEMO (mock do MCP, `IFOOD_MOCK=1` no secret `hackathon-ifood`): o número já aponta pro
  deploy novo. Pedido completo funciona: login simulado, endereço, busca com 3 cards, "Mais opções", carrinho,
  pagamento, resumo, confirmação, rastreio e lembrete. Quando o agente for aprovado: trocar o secret pelas
  credenciais e tirar o IFOOD_MOCK
- 65 testes passando (`.venv/Scripts/python.exe -m pytest`)

## Em andamento
- Fabio, claim `bot-ifood-agent`: back em Python no Modal, em `src/` (webhook do WhatsApp, buffer de rajadas, Gemini, cliente MCP + OAuth, mock do MCP). Reaproveita o setup do handwrite_bot
- Fabio: criando um 2º agente no portal com redirect no backend publicado (o "HackFood Agent" só tem localhost:8080, que não serve pro login pelo celular)

## Bloqueado ou esperando
- Credenciais do MCP: agente em análise no iFood desde ~15h
- Ordem de prioridade dos itens (ranking): esperando a regra do time; entra só em `src/bot/ranking.py`
- Back em Python: está em `src/` (claim `bot-ifood-agent`)

## Próximo passo
- Fechar a ideia com o time
- Mock do MCP (claim mcp-mock) pra ninguém ficar parado esperando credencial

## Horários de corte
- 16h30: ideia fechada e docs no repo
- 19h: fluxo básico (buscar, carrinho, confirmar) rodando, mesmo que em mock
- 06h: começam os entregáveis
- 11h30 de domingo: tudo travado (submissão às 12h30)
