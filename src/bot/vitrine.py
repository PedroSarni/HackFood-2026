"""Vitrine do "oi": o primeiro contato já chega com ideias de pedido do gosto da pessoa.

Inspirado no Ailo do iFood (cards "Tô afim de Lanches", "Quero pratos até R$ 45", "Descontos pra
você"). Cada card vem de um AGENTE interno, que olha um sinal diferente:
- `agente_gosto`: a categoria que a pessoa mais pede (histórico nosso `hist:{wa}`, ou os pedidos
  recentes do iFood);
- `agente_hora`: o que combina com a hora (pão de manhã, marmita no almoço, açaí à tarde, pizza à noite);
- `agente_precinho`: a categoria do gosto com teto de preço (refinement maxItemPrice da doc);
- `agente_descontos`: itens da categoria que estão com preço promocional de verdade.

Os agentes só PROPÕEM; quem garante é a busca: card sem produto achado não entra, e a foto do card é
a de um produto real. Pra não estourar o firewall do iFood (barra rajada), os agentes reaproveitam as
mesmas buscas (no máximo 2 por vitrine) e a vitrine vale VALIDADE segundos por pessoa.
Tocar no card (`vit:<n>`) busca aquilo de novo, com o mesmo teto/filtro (src/bot/fluxo.py).
"""
import time

from src.bot import ranking
from src.bot.recorrencia import categoria
from src.shared.ifood_mcp import ErroMCP

VALIDADE = 20 * 60
MAX_CARDS = 4
FUSO = -3 * 3600  # hora de Brasília (o servidor roda em UTC)

# categoria (src/bot/recorrencia.py) -> (o que buscar, tipo de loja, nome no card, teto do "precinho",
# como se fala no plural: "os melhores lanches", "as melhores pizzas")
CATEGORIAS = {
    'hambúrguer': ('hambúrguer', 'RESTAURANTE', 'Lanches', 35, 'os melhores lanches'),
    'lanche': ('lanche', 'RESTAURANTE', 'Lanches', 30, 'os melhores lanches'),
    'pizza': ('pizza', 'RESTAURANTE', 'Pizza', 45, 'as melhores pizzas'),
    'açaí': ('açaí', 'RESTAURANTE', 'Açaí', 25, 'os melhores açaís'),
    'sushi': ('sushi', 'RESTAURANTE', 'Japonesa', 50, 'os melhores japoneses'),
    'pastel': ('pastel', 'RESTAURANTE', 'Pastel', 20, 'os melhores pastéis'),
    'esfiha': ('esfiha', 'RESTAURANTE', 'Esfiha', 20, 'as melhores esfihas'),
    'marmita': ('marmita', 'RESTAURANTE', 'Marmita', 30, 'as melhores marmitas'),
    'frango': ('frango frito', 'RESTAURANTE', 'Frango', 40, 'o melhor frango'),
    'sorvete': ('sorvete', 'RESTAURANTE', 'Sorvete', 25, 'os melhores sorvetes'),
    'café': ('café', 'MERCADO', 'Café', 20, 'os melhores cafés'),
    'pão': ('pão francês', 'MERCADO', 'Padaria', 15, 'o pãozinho mais fresco'),
}
POPULARES = ['hambúrguer', 'pizza', 'marmita', 'pão']  # quando o gosto e a hora não acham nada
MAX_BUSCAS = 3
# (das, até, categoria): a hora local manda o palpite de quem ainda não tem histórico
POR_HORA = [(5, 10, 'pão'), (10, 15, 'marmita'), (15, 18, 'açaí'), (18, 23, 'pizza')]
MADRUGADA = 'hambúrguer'
NOME_HORA = {'pão': 'Café da manhã', 'marmita': 'Hora do almoço', 'açaí': 'Lanchinho da tarde',
             'pizza': 'Pra hoje à noite', 'hambúrguer': 'Fome de madrugada'}


def hora_local(agora):
    return time.gmtime(agora + FUSO).tm_hour


def da_hora(agora):
    h = hora_local(agora)
    return next((c for ini, fim, c in POR_HORA if ini <= h < fim), MADRUGADA)


# ------------------------------------------------------------------------------- agentes

def agente_gosto(hist, recentes):
    """A categoria mais pedida: 1º o histórico nosso (mais vezes, depois a mais recente), senão
    os pedidos recentes do iFood (feitos pelo app também). None = ainda não sabemos o gosto."""
    cats = sorted(((k[4:], h) for k, h in (hist or {}).items() if k.startswith('cat:') and k[4:] in CATEGORIAS),
                  key=lambda kv: (-kv[1].get('vezes', 0), -kv[1].get('ultima', 0)))
    if cats:
        return cats[0][0]
    for p in recentes or []:
        for nome in str(p.get('resumo') or '').split(','):
            c = categoria(nome)
            if c in CATEGORIAS:
                return c
    return None


def agente_hora(agora, gosto):
    """O palpite da hora, se não é o mesmo do gosto (aí seria card repetido)."""
    c = da_hora(agora)
    return None if c == gosto else c


def agente_precinho(cat, ofertas):
    """A categoria do gosto com teto de preço, se tem produto abaixo do teto."""
    teto = CATEGORIAS[cat][3]
    baratas = [o for o in ofertas if o.get('preco') is not None and o['preco'] <= teto]
    return (teto, baratas) if baratas else None


def agente_descontos(ofertas):
    """Itens com preço promocional de verdade (o iFood manda o preço cheio junto)."""
    return [o for o in ofertas if o.get('preco_antigo') and o['preco_antigo'] > (o.get('preco') or 0)]


# ------------------------------------------------------------------------------- montagem

def _foto(ofertas, usadas):
    """A foto de um produto real, de preferência uma que outro card ainda não usou."""
    fotos = [o['imagem'] for o in ofertas if o.get('imagem')]
    foto = next((f for f in fotos if f not in usadas), fotos[0] if fotos else None)
    if foto:
        usadas.add(foto)
    return foto


def _pedido(cat, **extra):
    busca, tipo, *_ = CATEGORIAS[cat]
    return {'termo': busca, 'busca': busca, 'tipo_loja': tipo, 'quantidade': None, 'observacao': None, **extra}


def montar(api, endereco, hist, recentes, agora, foto_padrao):
    """Roda os agentes e devolve até MAX_CARDS cards [{agente, titulo, texto, botao, imagem, pedido}].
    `api` é o Ifood da pessoa (src/bot/ifood.py). Menos de 2 cards = sem vitrine (o carrossel pede 2)."""
    gosto = agente_gosto(hist, recentes)
    hora = da_hora(agora)
    buscas = {}

    def buscar(cat):
        if cat not in buscas:
            if len(buscas) >= MAX_BUSCAS:  # o firewall do iFood barra rajada: vitrine não vale um bloqueio
                return []
            busca, tipo, *_ = CATEGORIAS[cat]
            try:
                achadas, _ = api.buscar(busca, endereco, tipo)
            except ErroMCP as e:
                print(f'vitrine: busca {cat} falhou: {e!r}')
                achadas = []
            buscas[cat] = ranking.ordenar(achadas, {'termo': busca})
        return buscas[cat]

    # a categoria principal: o gosto; sem gosto (ou sem produto), a da hora; senão as populares
    fila = list(dict.fromkeys(c for c in [gosto, hora] + POPULARES if c))
    base = next((c for c in fila if buscar(c)), None)
    if not base:
        return []
    ofertas, usadas, cards = buscas[base], set(), []
    _b, _t, nome, teto, melhores = CATEGORIAS[base]
    agente = 'gosto' if base == gosto else 'hora' if base == hora else 'popular'
    abertura = {'gosto': 'Seu favorito', 'hora': NOME_HORA.get(base, 'Pra agora'), 'popular': 'Os mais pedidos'}[agente]
    cards.append({'agente': agente, 'titulo': f'Tô afim de {nome}', 'texto': f'{abertura}: {melhores} perto de você.',
                  'botao': 'Ver itens', 'imagem': _foto(ofertas, usadas), 'pedido': _pedido(base)})
    precinho = agente_precinho(base, ofertas)
    if precinho:
        teto, baratas = precinho
        cards.append({'agente': 'precinho', 'titulo': f'{nome} até R$ {teto}',
                      'texto': 'Os melhores itens no precinho, com a qualidade que você ama.',
                      'botao': f'Até R$ {teto}', 'imagem': _foto(baratas, usadas),
                      'pedido': _pedido(base, preco_max=teto)})
    descontos = agente_descontos(ofertas)
    if descontos:
        cards.append({'agente': 'descontos', 'titulo': 'Descontos pra você!',
                      'texto': f'Achei {len(descontos)} {"item" if len(descontos) == 1 else "itens"} de '
                               f'{nome.lower()} com preço baixado hoje.',
                      'botao': 'Ver descontos', 'imagem': _foto(descontos, usadas),
                      'pedido': _pedido(base, so_promo=True)})
    # mais uma ideia, diferente da principal: a da hora (se a principal foi o gosto) ou uma popular
    for outra in [agente_hora(agora, base)] + POPULARES:
        if not outra or outra == base or len(cards) >= MAX_CARDS:
            continue
        ofertas2 = buscar(outra)
        if ofertas2:
            nome2, melhores2 = CATEGORIAS[outra][2], CATEGORIAS[outra][4]
            cards.append({'agente': 'hora' if outra == hora else 'popular',
                          'titulo': NOME_HORA.get(outra, f'Que tal {nome2}?') if outra == hora else f'Que tal {nome2}?',
                          'texto': f'Bateu vontade? Separei {melhores2} perto de você.',
                          'botao': f'Ver {nome2.lower()}'[:20], 'imagem': _foto(ofertas2, usadas),
                          'pedido': _pedido(outra)})
            break
    for c in cards:
        c['imagem'] = c['imagem'] or foto_padrao
    return cards[:MAX_CARDS] if len(cards) >= 2 else []
