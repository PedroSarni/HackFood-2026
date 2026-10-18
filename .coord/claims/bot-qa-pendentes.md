---
slug: bot-qa-pendentes
owner: araujo.fabio@usp.br
status: active
started: 2026-10-18 06:30
---

## O que

Os itens abertos de prioridade baixa do QA de 18/10 (`docs/qa-18-10.md`), um commit por item, com teste:
- B3/U4: o carrinho que sumiu às 01h43 (tem rastro no diário) e o texto digitado tratado como botão velho
- U21: "meu pedido" com carrinho montando mostra o pedido antigo
- U24: o pedido mínimo bloqueia o agendamento
- U7/U10: botão velho depois de cancelar e o "Sim, quero!" velho da foto
- U9: foto de comida indo direto pra busca
- U3: sem voltar no pagamento e no CPF
- U1: o "Fazer pedido" repete a pergunta
- U17: "leite" vira "leite integral"
- U18: "me responde por áudio" confirma só em áudio
- H4: rastreio depois de "apagar meus dados"
- M3: o mock cumprimenta "Oi, Fabio!"

NÃO cobre: kit do grupo (U11, U14, U16: já feitos), U12 (arredondar pra cima é de propósito), C1 (lojas
fechadas, decisão), O1/O2 e M1 (diferenças do mock), U27 (resolvido junto com o U26).

## Arquivos que vou tocar

- `src/bot/fluxo.py`, `src/bot/textos.py`, `src/bot/interpretar.py`, `src/bot/rastreio.py`, `src/bot/foto.py`
- `src/shared/mcp_fake.py` (só o M3)
- `tests/test_achados_qa.py`

## Peças compartilháveis que vou criar

- nenhuma
