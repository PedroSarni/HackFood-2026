# AiFood — compras no iFood pelo WhatsApp

Assistente de compras do iFood que vive dentro do WhatsApp: a pessoa escreve, manda áudio ou a foto da lista,
e o bot monta o pedido, fecha e acompanha a entrega. Feito para quem domina o WhatsApp mas não o app.

Time: Davi, Fabio, Pedro e Breno · Hackathon SEMCOMP × iFood "Vendendo com Agentes" (ONOVOLAB, São Carlos), 17–18/10/2026.

**Entregáveis:** [`docs/entregaveis/entrega-unica.md`](docs/entregaveis/entrega-unica.md) (proposta, solução, experiência,
interface, técnico, feedback do MCP) · slides em [`docs/entregaveis/slides/`](docs/entregaveis/slides/) · PDF na raiz.

## O que ele faz

- **Lista de mercado em uma frase**: "quero arroz, feijão, farofa, banana e 1 kg de carne friboi" → escolhe o mercado que
  tem tudo e sai mais em conta, mostra cards com foto item a item, pergunta a quantidade na unidade certa (quilo, pacote,
  bandeja), fecha o pedido.
- **Áudio e foto**: nota de voz é transcrita (ElevenLabs Scribe) e tratada como texto; foto de lista, de prato ou de
  produto vira busca. No modo áudio, o bot responde falando.
- **Kit pra galera**: "churrasco com picanha pra 13 amigos por até R$ 300 com cerveja" → monta o kit numa loja só,
  respeita o orçamento e mostra quanto fica por pessoa.
- **Recorrência**: na 2ª compra do mesmo item (ou categoria: carne, pão, hambúrguer…) oferece o automático; no dia,
  chama com tudo pronto e só pede com o "sim" da pessoa.
- **Quem manda é a pessoa**: "já pode passar no pix" fecha o pedido na hora, sem perguntas a mais; uma sugestão por
  pedido, e só uma vez.
- **Acompanhamento**: cada mudança de status chega no WhatsApp dizendo de qual pedido é.

## Como funciona (resumo)

```
WhatsApp Cloud API ──▶ src/app.py (Modal: webhook + filas) ──▶ src/bot/fluxo.py (o "Maestro")
                                                                 ├─ src/agentes/   (Claude Sonnet 5.5 1º, Gemini reserva)
                                                                 ├─ src/shared/ifood_mcp.py (MCP oficial do iFood)
                                                                 └─ src/shared/mcp_fake.py  (catálogo de reserva)
Frontend/Rascunho_Dash ◀── src/painel/servidor.py (dash: conversas, agentes, MCP, interruptores)
```

- O fluxo é código; a IA só interpreta (entendimento, foto, relevância, kit, roteiro da voz). Dinheiro e etapas são
  sempre do código.
- Todas as chamadas ao iFood passam pelo MCP oficial (`src/shared/ifood_mcp.py`); login por OAuth + PKCE.
- O firewall do iFood bloqueia por IP de saída: quando um container cai num IP barrado, a chamada é refeita por outro
  container (ponte) e o container se aposenta. Com o "modo palco" armado, se tudo falhar o bot passa para o catálogo de
  reserva sem mostrar erro (o conteúdo desse catálogo mora num Volume do Modal, fora do git).
- Detalhes: [`docs/como-funciona.md`](docs/como-funciona.md) · decisões: [`docs/decisoes.md`](docs/decisoes.md) ·
  estado: [`docs/estado.md`](docs/estado.md) · WhatsApp: [`docs/whatsapp.md`](docs/whatsapp.md).

## Rodar

```sh
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Python 3.12
.venv/Scripts/python.exe -m pytest -q                                     # 550+ testes, sem rede

# bot em produção (Modal; secrets hackathon-* já cadastrados; a URL é fixa por causa do OAuth do iFood)
.venv/Scripts/python.exe -m modal deploy -m src.app

# dash local
.venv/Scripts/python.exe -m src.painel.servidor        # http://127.0.0.1:8787
cd Frontend/Rascunho_Dash && npm install && npm run dev  # http://localhost:5173
```

Interruptores sem deploy (`scripts/modo.py`): `--mock on|off` (catálogo de reserva), `--palco on|off` (troca
automática se o iFood cair), `--rapido on` (recorrência em 1 min), `--fechadas on` (lojas fechadas aparecem),
`--cutucar on|off` (follow-up de quem some). Os mesmos interruptores ficam no pé da barra lateral do dash.

## Mapa do repositório

| Pasta | O que tem |
|---|---|
| `src/bot/` | o fluxo da conversa (`fluxo.py`), textos, interpretação, foto, kit em grupo, recorrência, rastreio |
| `src/agentes/` | a ficha de cada agente de IA (modelo, prompt, plano B) que o dash liga/desliga |
| `src/shared/` | MCP do iFood, catálogo de reserva, LLM (Claude/Gemini), WhatsApp, voz, alertas |
| `src/painel/` | servidor do dash e a analista de insights |
| `Frontend/Rascunho_Dash/` | o dash (React + Vite): conversas, agentes, uso do MCP, dinheiro, conversão |
| `tests/` | suíte completa com WhatsApp, iFood e IA de mentira (`tests/fakes.py`) |
| `docs/` | entregáveis, como funciona, decisões, QA e prompts do time |
| `scripts/` | interruptores de produção, sondas e validações |

## Trabalho em equipe

Regras para humanos e agentes em [AGENTS.md](AGENTS.md): claim antes de codar (`.coord/claims/`), trunk-based com push
contínuo, commits só com a autoria de quem escreveu (hook e CI barram co-autoria de IA).
