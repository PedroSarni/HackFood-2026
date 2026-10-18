---
slug: ops-ifood-unblock
owner: araujo.fabio@usp.br
status: active
started: 2026-10-18 02:50
---

## O que

Botão de pânico pra apresentação: quando o Akamai do iFood barra o container do bot (403 Access Denied),
um comando só recicla os containers (redeploy do main, mesma URL), zera o disjuntor e confere se voltou.
Vem com uma skill do Claude Code que explica o porquê, pra qualquer agente rodar sem hesitar.
NÃO cobre: proxy/IP fixo, mudar app/label/região do Modal, contornar o firewall de outro jeito.

## Arquivos que vou tocar

- `scripts/destravar_ifood.sh` (novo), `scripts/modo.py` (só a opção `--zerar`)
- `.claude/skills/destravar-ifood/SKILL.md` (novo)
- `docs/como-funciona.md`, `docs/prompts/fabio.md`

## Peças compartilháveis que vou criar

- nenhuma em `src/shared/`

## Onde está (preencher ao terminar)
