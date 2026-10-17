#!/bin/sh
# Regra de autoria (AGENTS.md §3): commits e PRs são de autoria humana, sem atribuição a IA.
#
# Uso:
#   check-authorship.sh --msg-file <arquivo>   hook commit-msg (checa também a identidade atual)
#   check-authorship.sh --stdin                checa texto, ex.: descrição de PR
#   check-authorship.sh <rev-range...>         checa commits (pre-push e CI)
#
# Para ajustar a lista de ferramentas, edite AI_IDENT / AI_TRAILER.

# Nomes inequívocos de IA: bloqueados na identidade do autor/committer e em trailers.
AI_IDENT='claude|anthropic|openai|chatgpt|gpt|copilot|cursor|codex|gemini|aider|windsurf|codeium|tabnine|codewhisperer|cognition|lovable|replit'
# Em trailers também entram nomes que podem ser de gente (só bloqueados como co-autor).
AI_TRAILER="$AI_IDENT|devin|jules|astra|bard|bot"

fail=0
report() { printf '\n✖ autoria: %s\n' "$1" >&2; fail=1; }

check_text() { # $1 = rótulo, $2 = texto
  text=$(printf '%s\n' "$2" | grep -v '^#')
  hit=$(printf '%s\n' "$text" | grep -iE '^[[:space:]]*co-authored-by:' | grep -iwE "$AI_TRAILER")
  [ -n "$hit" ] && report "$1 tem co-autoria de IA: $hit"
  hit=$(printf '%s\n' "$text" | grep -iE '(generated|created|written|made|assisted)[[:space:]]+(with|by|using)' | grep -iwE "$AI_TRAILER|ai|ia|llm")
  [ -n "$hit" ] && report "$1 tem assinatura de IA: $hit"
  printf '%s\n' "$text" | grep -qF '🤖' && report "$1 contém 🤖 (assinatura de ferramenta de IA)"
}

check_ident() { # $1 = rótulo, $2 = "Nome <email>"
  if printf '%s\n' "$2" | grep -iwqE "$AI_IDENT" || printf '%s\n' "$2" | grep -qF '[bot]'; then
    report "$1 parece ser IA/bot: $2 (use sua identidade em git config user.name / user.email)"
  fi
}

case "$1" in
  --msg-file)
    check_text "mensagem do commit" "$(cat "$2")"
    check_ident "autor" "$(git var GIT_AUTHOR_IDENT)"
    check_ident "committer" "$(git var GIT_COMMITTER_IDENT)"
    ;;
  --stdin)
    check_text "texto" "$(cat)"
    ;;
  "")
    echo "uso: $0 --msg-file <arquivo> | --stdin | <rev-range...>" >&2
    exit 2
    ;;
  *)
    commits=$(git rev-list "$@") || exit 2
    for c in $commits; do
      short=$(git rev-parse --short "$c")
      check_text "commit $short" "$(git log -1 --format=%B "$c")"
      check_ident "autor do commit $short" "$(git log -1 --format='%an <%ae>' "$c")"
      check_ident "committer do commit $short" "$(git log -1 --format='%cn <%ce>' "$c")"
    done
    ;;
esac

if [ "$fail" -ne 0 ]; then
  cat >&2 <<'EOF'

Regra universal (AGENTS.md §3): commits e PRs são de autoria de quem escreveu.
Remova a atribuição de IA e tente de novo. Não use --no-verify.
EOF
  exit 1
fi
