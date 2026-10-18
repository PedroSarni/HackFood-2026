"""Foto vira pedido: em qualquer momento da conversa, até como 1ª mensagem.

O Gemini olha a foto (e a legenda, e o que mais veio na rajada) e diz o que ela é:
- comida pronta (lanche, pizza, prato): o bot pergunta se a pessoa quer algo parecido e, com o sim,
  busca os `parecidos` (do mais parecido pro mais genérico: "x-bacon", "hambúrguer", "lanche");
- lista de compras (papel, bilhete, print) ou produto (caixa de remédio, pacote de arroz): vira a lista
  do pedido, igual a uma lista escrita;
- outra coisa: o bot comenta e pede o que a pessoa quer.

Quem decide o que fazer é o fluxo (src/bot/fluxo.py, `receber_fotos`); aqui só o prompt, o esquema e a
limpeza do que o modelo devolveu. Documento pessoal (RG, CPF, cartão) nunca é transcrito: vira `outro`.
"""
from src.bot.interpretar import LOJAS, contexto_para_llm

MAX_FOTOS = 4  # mais que isso numa rajada só pesa no Gemini e quase sempre é a mesma lista repetida
TIPOS = ['comida', 'lista', 'produto', 'outro']

_ITEM = {
    'type': 'OBJECT',
    'properties': {
        'termo': {'type': 'STRING', 'description': 'o produto, curto, sem quantidade'},
        'busca': {'type': 'STRING', 'description': 'o que digitar na busca do iFood pra achar ESSE produto'},
        'quantidade': {'type': 'INTEGER', 'nullable': True},
        'tipo_loja': {'type': 'STRING', 'enum': LOJAS},
        'observacao': {'type': 'STRING', 'nullable': True},
    },
    'required': ['termo', 'busca', 'tipo_loja'],
}

ESQUEMA = {
    'type': 'OBJECT',
    'properties': {
        'tipo': {'type': 'STRING', 'enum': TIPOS},
        'descricao': {'type': 'STRING', 'description': 'o que a foto mostra, curto, em português'},
        'itens': {'type': 'ARRAY', 'items': _ITEM},
        'parecidos': {'type': 'ARRAY', 'items': _ITEM},
        'ja_pediu': {'type': 'BOOLEAN'},
        'quantidade': {'type': 'INTEGER', 'nullable': True},
        'pessoas': {'type': 'INTEGER', 'nullable': True},
        'resposta': {'type': 'STRING', 'nullable': True},
    },
    'required': ['tipo', 'descricao'],
}

SISTEMA = """\
Você olha as fotos que uma pessoa mandou no WhatsApp para um assistente que faz pedidos no iFood \
(mercado, restaurante, farmácia, bebidas, pet). Quem manda costuma ser idoso ou ter pouca prática com \
celular. TODA foto aqui é um pedido: descubra o que a pessoa quer comprar. Leve em conta a legenda e as \
mensagens escritas que vieram junto (e o contexto da conversa).

Responda só o JSON do esquema. Campos:
- tipo:
  comida = comida ou bebida pronta, servida ou de cardápio/anúncio (hambúrguer, pizza, prato feito, \
açaí, sushi, bolo de festa, um copo de suco). A pessoa provavelmente quer algo parecido.
  lista = lista de compras (papel, caderno, bilhete, quadro, print de conversa ou de nota) escrita à mão \
ou digitada. Leia TODOS os itens, mesmo com letra ruim, abreviação ou erro ("2 lt leite" = 2 leite).
  produto = embalagem ou produto de loja (caixa de remédio, pacote de arroz, garrafa, lata, ração, \
sabão), inclusive embalagem vazia ou acabando: a pessoa quer comprar mais daquilo.
  outro = nada disso (selfie, paisagem, meme, bicho, tela sem produto). Documento pessoal (RG, CPF, \
CNH, cartão de banco, comprovante): tipo=outro e NUNCA transcreva números ou nomes.
- descricao: o que a foto mostra, curto e em português ("hambúrguer com bacon e batata frita", \
"lista com 6 itens de mercado", "caixa de dipirona 500 mg"). Em documento pessoal, só "documento".
- itens: quando lista ou produto, cada produto, na ordem. termo curto no singular, sem a quantidade \
("arroz", "leite integral", "dipirona 500 mg"). Marca vai na observacao ("marca Tio João"), tamanho e \
sabor no termo ("coca-cola 2 litros"). quantidade só se estiver escrita ou dita (meia dúzia=6). Se a \
mensagem escrita pede mais produtos, inclua também.
- parecidos: quando comida, de 1 a 3 buscas pra achar algo parecido no iFood, da mais parecida pra \
mais genérica ("x-bacon", "hambúrguer", "lanche"; "pizza de calabresa", "pizza"). 1 a 3 palavras cada, \
como aparece num cardápio. tipo_loja RESTAURANTE pra comida pronta.
- busca e tipo_loja: como num catálogo. MERCADO pra alimento cru, bebida não alcoólica, limpeza e \
higiene; RESTAURANTE pra comida pronta; FARMACIA pra remédio; BEBIDAS pra bebida alcoólica; PET pra \
coisa de bicho; LOJA pro resto. Desambigue palavra que engana ("cebola" -> "cebola in natura").
- ja_pediu: true se a legenda ou a mensagem já pede pra comprar ou procurar aquilo ("quero isso", \
"me vê 2 desse", "acha pra mim", "tem esse aí?"). Só a foto, sem pedido escrito = false.
- quantidade: quando comida e a pessoa disse quantos quer ("2 desse" = 2); senão null.
- pessoas: se a pessoa disse pra quantas pessoas é, contando com ela ("pra 5" = 5, "eu e mais 3" = 4, \
"com 4 amigos" = 5); senão null.
- resposta: uma frase curta, calorosa e em português comentando a foto, com 1 emoji ("Que delícia, \
hambúrguer com bacon! 😋"). Nunca diga que já comprou ou que achou algo: o assistente ainda vai buscar.
Nunca invente produto que não está na foto nem na mensagem."""


def _item(it, tipo_padrao='MERCADO'):
    termo = ' '.join(str(it.get('termo') or '').split())[:60]
    if not termo:
        return None
    qtd = it.get('quantidade')
    return {'termo': termo, 'busca': ' '.join(str(it.get('busca') or '').split())[:60] or termo,
            'quantidade': qtd if isinstance(qtd, int) and 0 < qtd <= 99 else None,
            'tipo_loja': it.get('tipo_loja') if it.get('tipo_loja') in LOJAS else tipo_padrao,
            'observacao': (it.get('observacao') or '')[:140] or None}


def ler(llm, estado, fotos, textos=()):
    """fotos: [(mime, bytes)]; textos: legenda e mensagens escritas da rajada, na ordem.
    Devolve {tipo, descricao, itens, parecidos, ja_pediu, quantidade, pessoas, resposta}.
    Levanta ErroLLM se o Gemini estiver fora (o fluxo explica e pede pra escrever)."""
    partes = [('texto', contexto_para_llm(estado) + '\n\nO que a pessoa mandou, na ordem:')]
    partes += [('arquivo', mime, dados) for mime, dados in fotos[:MAX_FOTOS]]
    escrito = '\n'.join(t for t in textos if t and t.strip())
    if escrito:
        partes.append(('texto', f'Escrito junto com a foto: {escrito[:600]}'))
    dados, _modelo, _seg = llm(SISTEMA, partes, ESQUEMA)
    dados = dados if isinstance(dados, dict) else {}
    tipo = dados.get('tipo') if dados.get('tipo') in TIPOS else 'outro'
    itens = [i for i in (_item(x) for x in dados.get('itens') or []) if i][:15]
    parecidos = [i for i in (_item(x, 'RESTAURANTE') for x in dados.get('parecidos') or []) if i][:3]
    if tipo in ('lista', 'produto') and not itens and parecidos:
        itens = parecidos  # o modelo pôs o produto no campo errado: ainda é o que a pessoa quer
    if tipo == 'comida' and not parecidos and itens:
        parecidos = itens[:3]
    qtd, pessoas = dados.get('quantidade'), dados.get('pessoas')
    return {'tipo': tipo, 'descricao': ' '.join(str(dados.get('descricao') or '').split())[:120],
            'itens': itens, 'parecidos': parecidos, 'ja_pediu': dados.get('ja_pediu') is True,
            'quantidade': qtd if isinstance(qtd, int) and 0 < qtd <= 50 else None,
            'pessoas': pessoas if isinstance(pessoas, int) and 1 < pessoas <= 99 else None,
            'resposta': ' '.join(str(dados.get('resposta') or '').split())[:300] or None}
