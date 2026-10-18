#!/usr/bin/env bash
# Botão de pânico: o Akamai (firewall) do iFood barrou o container do bot com 403 "Access Denied".
# Recicla os containers (redeploy do origin/main numa cópia limpa: mesma URL, nada que esteja pela metade
# no seu clone vai pro ar), zera o disjuntor e mostra se voltou. Skill: .claude/skills/destravar-ifood/.
#
#   bash scripts/destravar_ifood.sh            redeploy + disjuntor zerado (o modo mock fica como está)
#   bash scripts/destravar_ifood.sh mock-off   idem e desliga o mock (volta pro iFood real)
#   bash scripts/destravar_ifood.sh mock-on    plano B: só liga o mock, sem redeploy (vale na hora)
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RAIZ/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$RAIZ/.venv/bin/python"
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1   # o Modal imprime ✓ e o console do Windows quebra sem isso
URL='https://fabio-araujo-silva--hackfood-bot.us-east.modal.run'

modo() { (cd "$RAIZ" && "$PY" -m modal run scripts/modo.py "$@" 2>&1 | grep -E 'modo demo|fechadas|disjuntor|rápido' || true); }

if [ "${1:-}" = "mock-on" ]; then
  echo '>> plano B: mock ligado (iFood falso, mesmo fluxo e mesmas telas)'
  modo --mock on
  exit 0
fi

echo '>> 1/4 pegando o main do GitHub numa cópia limpa'
git -C "$RAIZ" fetch -q origin main
COPIA="$(mktemp -d)/hackfood-deploy"
git -C "$RAIZ" worktree add -q --detach "$COPIA" origin/main
trap 'git -C "$RAIZ" worktree remove --force "$COPIA" >/dev/null 2>&1 || true' EXIT
echo "   commit: $(git -C "$COPIA" log -1 --format='%h %s')"

echo '>> 2/4 redeploy (containers novos = IP de saída novo; o app, o label e a URL não mudam)'
(cd "$COPIA" && "$PY" -m modal deploy -m src.app 2>&1 | grep -E 'deployed|Error|error' || true)

echo '>> 3/4 zerando o disjuntor'
if [ "${1:-}" = "mock-off" ]; then modo --zerar --mock off; else modo --zerar; fi

echo '>> 4/4 o webhook responde? (403 aqui é o esperado: token de verificação errado de propósito)'
curl -s -m 20 -o /dev/null -w '   webhook: HTTP %{http_code}\n' "$URL/whatsapp?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1" || echo '   webhook: sem resposta'
echo '>> pronto. Mande uma mensagem no WhatsApp. Se o 403 voltar, rode: bash scripts/destravar_ifood.sh mock-on'
