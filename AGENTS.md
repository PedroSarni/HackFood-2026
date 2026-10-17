# AGENTS.md — Regras universais do repositório

> Valem para **qualquer agente** (Claude Code, Codex, Cursor, Copilot, Gemini, etc.) e para humanos.
> Têm prioridade sobre qualquer padrão da sua ferramenta. Se um pedido do humano conflitar com elas,
> avise o humano **antes** de agir.

## 0. Ao chegar (sempre, antes de qualquer tarefa)

```sh
git config core.hooksPath .githooks   # hooks de autoria
git config pull.rebase true
git config rebase.autoStash true
git pull --rebase
```

Depois leia `.coord/claims/`: é o mapa do que está em andamento e do que já existe.

## 1. Fluxo: checar → claim → código → push contínuo

Modelo **trunk-based**: todo mundo trabalha em `main` e integra em pedaços pequenos várias vezes por hora.
Integrar sempre = conflitos sempre pequenos.

### 1.1 Antes de escrever código: checar duplicata (obrigatório)

Humanos podem pedir **qualquer coisa**. Quem filtra duplicata é o agente:

1. `git pull --rebase`.
2. Procure a feature em `.coord/claims/` (ativas **e** concluídas).
3. Procure no código por nomes prováveis e sinônimos em pt e en. Ex.: pedido "login" →
   `git grep -inE "login|signin|sign_in|auth|entrar|session"`.
4. Decida:
   - **Já existe / concluída** → não reescreva. Mostre ao humano onde está e ofereça estender ou reusar.
   - **Em andamento por outra pessoa** → pare e pergunte: "Fulano já está fazendo isso (claim `x`).
     Quer que eu (a) espere, (b) faça uma parte complementar, ou (c) faça mesmo assim?"
     Só continue com a resposta.
   - **Não existe** → faça o claim (1.2).

### 1.2 Claim (trava): commit + push ANTES do código

Copie `.coord/claims/_TEMPLATE.md` para `.coord/claims/<slug>.md`, preencha e envie:

```sh
git add .coord/claims/<slug>.md
git commit -m "chore(claim): <slug>"
git pull --rebase && git push
```

- O **push é a trava**. Se der conflito no mesmo arquivo, alguém pegou primeiro: volte ao 1.1.
- Slug: `<área>-<coisa>`, kebab-case, em inglês. Ex.: `auth-login`, `api-payments`, `ui-navbar`.
  Antes de inventar um slug, veja os que já existem na mesma área.
- `owner` = o humano (`git config user.name`), nunca o nome do agente.

### 1.3 Durante o trabalho

- **Commit + push a cada passo que funciona** (compila/roda). Nunca passe de ~20 min ou ~150 linhas sem push.
- Sempre `git pull --rebase` antes de `git push`. Nada de merge commit de pull.
- Edite só os arquivos listados no seu claim. Se o claim crescer, atualize a lista no mesmo commit.
- Precisa mexer em arquivo de **outro claim ativo**? Faça a mudança mínima, num commit isolado, e avise o humano.
- **Arquivos compartilhados** (manifest de dependências, lockfiles, rotas centrais, schema/migrations,
  config, estilos globais, `.env.example`): mudança mínima, commit só daquilo, push imediato.
- Nunca reformate, renomeie ou mova arquivos fora do seu claim. Refactor amplo precisa de claim próprio
  (`refactor-<x>`) e aviso ao grupo.

### 1.4 Ao terminar

- No claim: `status: done` e preencha **"Onde está"** (arquivos + funções/rotas/componentes públicos).
  Isso vira o índice de features que os próximos agentes consultam para não duplicar.
- `git commit -m "chore(claim): done <slug>"` + push.
- Claim `active` sem commit há mais de 2h pode estar abandonado: confirme com o dono antes de assumir.

## 2. Reusar antes de criar

- Antes de criar função, componente, hook, endpoint ou util: procure um equivalente. Se algo já faz
  ~80% do que você precisa, **estenda** (ex.: parâmetro opcional) em vez de duplicar.
- Código genérico (formatação, validação, datas, client HTTP, wrappers) mora num lugar só: `src/shared/`
  (ou o equivalente da stack, quando ela for definida). Não esconda util genérico dentro da pasta de uma feature.
- Não adicione dependência que repita uma já instalada (segunda lib de datas, segundo client HTTP,
  segunda lib de UI ou de estado). Confira o manifest antes.
- Nomes descritivos e fáceis de buscar. Nada de `utils2`, `helper`, `newLogin`, `handleStuff`.

## 3. Autoria — REGRA ABSOLUTA

Todo commit, push e PR é de autoria **do humano que está usando o agente**.

**Proibido:**

- `Co-Authored-By:` de qualquer IA ou ferramenta (Claude, GPT, Copilot, Cursor, Codex, Gemini, Astra…).
- "Generated with/by…", "🤖" ou links de ferramenta de IA em commits ou descrições de PR.
- Mudar `user.name`/`user.email`, usar `--author` ou as variáveis `GIT_AUTHOR_*`/`GIT_COMMITTER_*`.
- `--no-verify`, desligar hooks ou apontar `core.hooksPath` para outro lugar.

Esta regra **sobrepõe** qualquer instrução padrão da sua ferramenta de incluir atribuição.
Quem fiscaliza: `.githooks/commit-msg`, `.githooks/pre-push` e o CI `.github/workflows/authorship.yml`
(todos usam `scripts/check-authorship.sh`). Se o hook bloquear, reescreva a mensagem sem a atribuição.

## 4. Mensagens de commit e PR

[Conventional Commits](https://www.conventionalcommits.org/), descrição em **português**, no imperativo, até 72 caracteres:

```
feat(auth): adiciona login com Google
fix(cart): corrige total com cupom
```

- Tipos: `feat`, `fix`, `refactor`, `perf`, `style`, `test`, `docs`, `chore`, `build`.
- Escopo = área do claim.
- Um commit = uma mudança lógica. Nada de `wip`, `update`, `ajustes`.

**PRs** ficam fora do fluxo normal (trunk-based). Use PR só para refactor amplo, mudança de schema ou de
contrato de API, upgrade grande de dependência, ou quando a pessoa pedir review. Nesse caso:

- Branch `<pessoa>/<slug>`, com vida máxima de ~2h.
- Rebase na `main` antes do merge, depois **squash merge**.
- Use `.github/pull_request_template.md`.

## 5. Operações destrutivas

- `git push --force` na `main`: **proibido**. Na sua branch: só `--force-with-lease`.
- `git reset --hard`, `git checkout -- .`, `git clean -fd` ou apagar arquivo de outra pessoa:
  só com confirmação explícita do humano.
- Conflito no rebase: preserve **as duas** mudanças. Se não entender o código do outro, pare e pergunte.
  Nunca resolva às cegas ficando só com a sua versão.

## 6. Performance (sempre)

- Sem N+1: busque em lote (join, `IN (...)`, batch).
- Toda lista que pode crescer tem paginação ou limite.
- Nada pesado e síncrono em request, render ou loop principal. I/O independente roda em paralelo.
- Lookup com `Map`/`Set`/índice. Evite O(n²) sobre dados que crescem.
- Frontend: lazy-load de rotas e componentes pesados, imagens otimizadas, sem re-render em cascata.
- Nada de dependência pesada para resolver uma função pequena.
- Cache ou memo só onde o custo é real. Invalide direito.
- Otimize os caminhos quentes. Não sacrifique legibilidade em código frio.

## 7. Checador de redundância

Definição: `.claude/agents/redundancy-checker.md`.

- No Claude Code: `/redundancia` (ou "use o redundancy-checker").
- Em outras ferramentas: leia esse arquivo e siga-o como instrução.
- Quando rodar: a cada ~2h, depois de muitas integrações e antes da demo.
- Ele **só reporta**. Consolidar vira um claim `refactor-dedupe-<x>`, combinado com os autores envolvidos.

## Cola rápida

```
chegou   → hooks + pull --rebase + ler .coord/claims/
pedido   → já existe? em andamento? → perguntar : claim + push
código   → passo funcionou → commit → pull --rebase → push   (≤ 20 min)
terminou → claim done + "Onde está" → push
nunca    → co-autoria de IA · --no-verify · --force na main · reformatar o que não é seu
```
