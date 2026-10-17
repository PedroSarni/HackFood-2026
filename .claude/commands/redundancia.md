---
description: Varre o repo por código redundante (quem escreveu o quê) com o agente redundancy-checker
argument-hint: "[full | caminho | desde <commit>]"
---

Use o subagente `redundancy-checker` para varrer o repositório. Escopo: $ARGUMENTS (vazio = repositório inteiro).

Mostre o relatório ao usuário sem modificar nenhum código. Depois pergunte se ele quer abrir claims
`refactor-dedupe-*` para os grupos de severidade ALTA.
