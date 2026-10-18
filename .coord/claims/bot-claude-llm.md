---
slug: bot-claude-llm
owner: Fabio Araujo
status: active
started: 2026-10-18 05:00
---

## O que

Claude Sonnet 5.5 vira o 1º modelo de todos os agentes de IA (entendimento, foto, relevância, kit, tutor, roteiro
da voz, analista); o Gemini fica de reserva logo atrás e o OpenRouter continua por último. Sem crédito (ou key
recusada) o Claude sai da fila sozinho por um tempo e o dash ganha uma central de notificações com o aviso.
Não cobre: áudio (a API do Claude não ouve; continua no Scribe/Gemini) nem a voz da ElevenLabs.

## Arquivos que vou tocar

- src/shared/llm.py, src/agentes/*.py, src/bot/voz.py, src/bot/contexto.py, src/app.py, requirements.txt
- src/painel/servidor.py, Frontend/Rascunho_Dash/ (sino de notificações)

## Peças compartilháveis que vou criar

- `src/shared/alertas.py` — `registrar(armazem, tipo, titulo, detalhe)`, `listar(armazem)`, `marcar_lidas(armazem)` — pronto
- rota `GET /api/alertas`, `POST /api/alertas/lidas` no servidor do dash — pronto

## Onde está (preencher ao terminar)

- 
