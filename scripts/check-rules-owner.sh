#!/bin/sh
# Arquivos de regras só podem ser alterados pelo dono (AGENTS.md §0.1).
#
# Uso:
#   check-rules-owner.sh --staged        hook pre-commit
#   check-rules-owner.sh <rev-range...>  CI

OWNER_EMAIL='araujo.fabio@usp.br'
PROTECTED='AGENTS.md CLAUDE.md GEMINI.md .github/copilot-instructions.md .github/workflows .githooks scripts/check-authorship.sh scripts/check-rules-owner.sh .claude/settings.json'

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
owner=$(lower "$OWNER_EMAIL")

case "$1" in
  --staged)
    [ "$(lower "$(git config user.email)")" = "$owner" ] && exit 0
    bad=$(git diff --cached --name-only -- $PROTECTED)
    ;;
  "")
    echo "uso: $0 --staged | <rev-range...>" >&2
    exit 2
    ;;
  *)
    bad=$(git log --format='%h %ae' "$@" -- $PROTECTED | awk -v o="$owner" 'tolower($2) != o')
    ;;
esac

[ -z "$bad" ] && exit 0
cat >&2 <<EOF

✖ arquivos protegidos: só $OWNER_EMAIL pode alterar as regras do repositório (AGENTS.md §0.1).
$bad

Desfaça a mudança nesses arquivos e leve a sugestão ao Fabio.
EOF
exit 1
