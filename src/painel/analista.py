"""A Analista: lê os números agregados de uma página do dash e devolve insights acionáveis por time do iFood.

Roda no Modal (src/app.py, `analisar_pagina`), porque as keys de IA só existem lá. Ela usa a fila de modelos
e o interruptor da ficha (src/agentes/analista.py), como os outros agentes.
Entrada: só agregados (contagens, taxas, valores, nomes de cidade e loja). O dash nunca manda nome nem
telefone de cliente.
"""
import json

TIMES = ['Produto', 'Growth e CRM', 'Operações', 'Comercial e parcerias', 'Logística', 'Atendimento',
         'Dados e BI', 'Marketing', 'Tecnologia']
IMPACTOS = ['alto', 'médio', 'baixo']
PRAZOS = ['esta semana', 'este mês', 'este trimestre']
PAGINAS = {'conversao': 'Conversão (funil da conversa ao pedido, abandono e recuperação)',
           'clientes': 'Clientes (recorrência, recompra e concentração de valor)',
           'mercado': 'Mercado (cidades e lojas: valor, pedidos, conversão)'}
MAX_ENTRADA = 30_000   # caracteres de JSON: o dash manda agregado, não a base

SISTEMA = """\
Você é a Analista do canal de pedidos do iFood pelo WhatsApp: um bot em que a pessoa conversa (texto, áudio ou
foto), recebe ofertas, monta o carrinho e paga, sem abrir o app. Você recebe os números AGREGADOS de uma
página do painel desse canal e escreve insights para os times do iFood agirem.

Regras:
- De 3 a 5 insights, do mais importante pro menos. Cada um precisa de um número desta página como evidência
  (cite o valor: "28% dos carrinhos abandonam na escolha do pagamento"). Nunca invente número, loja ou
  cidade que não esteja nos dados.
- Ação concreta e testável, do jeito que um time faria segunda-feira: um experimento, uma mudança no
  fluxo do bot, uma campanha, uma conversa com parceiros. Evite conselho genérico ("melhorar a
  experiência", "investir em marketing").
- Escolha o time dono da ação: Produto (fluxo e telas do bot), Growth e CRM (lembretes, recompra,
  cupons), Operações, Comercial e parcerias (lojas e restaurantes), Logística (entrega), Atendimento, Dados
  e BI (medir melhor), Marketing (aquisição), Tecnologia (erros, latência, integrações).
- Diga a métrica que mostra se funcionou e um prazo realista.
- Se a amostra for pequena (poucas conversas), diga isso no resumo e prefira ações de medir antes de mudar.
- Se `demo` for verdadeiro, os dados são simulados: analise do mesmo jeito, sem comentar isso.
- Português do Brasil, frases curtas, sem jargão.
"""

ESQUEMA = {
    'type': 'OBJECT',
    'properties': {
        'resumo': {'type': 'STRING', 'description': 'Uma ou duas frases: o que esta página diz agora.'},
        'insights': {'type': 'ARRAY', 'items': {
            'type': 'OBJECT',
            'properties': {
                'titulo': {'type': 'STRING'},
                'time': {'type': 'STRING', 'enum': TIMES},
                'evidencia': {'type': 'STRING', 'description': 'O número da página que sustenta o insight.'},
                'acao': {'type': 'STRING', 'description': 'O que o time faz, concreto.'},
                'impacto': {'type': 'STRING', 'enum': IMPACTOS},
                'prazo': {'type': 'STRING', 'enum': PRAZOS},
                'metrica': {'type': 'STRING', 'description': 'O que acompanhar pra saber se deu certo.'},
            },
            'required': ['titulo', 'time', 'evidencia', 'acao', 'impacto', 'prazo', 'metrica'],
        }},
    },
    'required': ['resumo', 'insights'],
}


class EntradaRuim(ValueError):
    pass


def _texto(v, limite):
    return ' '.join(str(v or '').split())[:limite]


def limpar(dados):
    """O que o modelo devolveu -> só o que o dash sabe desenhar (enum fora da lista cai no padrão)."""
    dados = dados if isinstance(dados, dict) else {}
    saida = []
    for item in (dados.get('insights') or [])[:6]:
        if not isinstance(item, dict) or not _texto(item.get('titulo'), 1) or not _texto(item.get('acao'), 1):
            continue
        saida.append({'titulo': _texto(item.get('titulo'), 140),
                      'time': item.get('time') if item.get('time') in TIMES else 'Produto',
                      'evidencia': _texto(item.get('evidencia'), 280), 'acao': _texto(item.get('acao'), 400),
                      'impacto': item.get('impacto') if item.get('impacto') in IMPACTOS else 'médio',
                      'prazo': item.get('prazo') if item.get('prazo') in PRAZOS else 'este mês',
                      'metrica': _texto(item.get('metrica'), 200)})
    return {'resumo': _texto(dados.get('resumo'), 400), 'insights': saida}


def analisar(pagina, dados, gerar):
    """gerar(sistema, partes, esquema) -> (dados, modelo, segundos), já com a fila e o interruptor da ficha."""
    if pagina not in PAGINAS:
        raise EntradaRuim(f'página sem insights: {pagina}')
    corpo = json.dumps(dados, ensure_ascii=False, sort_keys=True)
    if len(corpo) > MAX_ENTRADA:
        raise EntradaRuim('dados grandes demais: mande agregados')
    pedido = f'Página: {PAGINAS[pagina]}\n\nNúmeros da página (JSON):\n{corpo}'
    resposta, modelo, segundos = gerar(SISTEMA, [('texto', pedido)], ESQUEMA)
    limpo = limpar(resposta)
    if not limpo['insights']:
        raise ValueError('o modelo não devolveu nenhum insight utilizável')
    return {**limpo, 'modelo': modelo, 'segundos': round(segundos, 1)}
