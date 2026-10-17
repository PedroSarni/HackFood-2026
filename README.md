# hackathon

## Começando (cada pessoa, uma vez por clone)

```sh
git config core.hooksPath .githooks
git config pull.rebase true
git config rebase.autoStash true
git config user.name  "Seu Nome"        # sua identidade real: é ela que assina os commits
git config user.email "seu@email.com"
```

As regras de trabalho (para humanos e agentes) estão em [AGENTS.md](AGENTS.md). Resumo:

1. Antes de pedir uma feature ao agente, ele confere `.coord/claims/` e o código para ver se já existe.
2. Se não existe, ele cria um claim e faz push **antes** de escrever código. O push funciona como trava.
3. Commit + push a cada passo que funciona (no máximo ~20 min sem push), sempre com `pull --rebase` antes.
4. Commits só com a autoria de quem escreveu. Co-autoria ou assinatura de IA é bloqueada por hook e pelo CI.
5. Para checar redundância: `/redundancia` no Claude Code.
