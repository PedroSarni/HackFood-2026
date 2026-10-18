"""MCP falso do iFood: mesmas tools do gateway, dados inventados, estado num dicionário.

Serve pra desenvolver, testar e fazer demo sem credencial (o agente do portal está em
análise). `chamar()` tem a mesma assinatura do ClienteMCP real e levanta ErroMCP do mesmo
jeito, então quem usa não sabe a diferença. As respostas seguem os exemplos das páginas da
doc do portal (resultKind/results, CartDetailsResponse na raiz, `errors` objeto no User e
Discovery, `error` no Cart, campos na raiz no Order Tracking).

Também imita as exigências que derrubam agente na vida real: `options` obrigatório (mesmo
vazio), getCartDeliveryMethods antes do setCartDelivery, paymentMethodId UUID (não "PIX"),
cartão sem cardTokenId recusado, userConsent obrigatório, carrinho excluído ao tirar o último
item, opções obrigatórias do item.

O estado (endereços, carrinhos, pedidos) fica em `armazem[chave]`: em produção, o mesmo
modal.Dict do bot, então sobrevive entre uma mensagem e outra.

Consistente de propósito (17/10, o mock virou o iFood da apresentação): cada loja tem o seu pedido
mínimo, o mesmo no getMerchant e no carrinho; lanchonete, pizzaria, cantina e mercados têm o que
acompanha (refri, suco, batata, sobremesa, manteiga, café) pra sugestão do mínimo sempre achar algo;
a busca ignora palavra vazia ("de", "com") e põe na frente quem tem todas as palavras. Item novo vai
SEMPRE no fim do CATALOGO: o id do item é o índice, e carrinho guardado no armazém aponta pra ele.
"""
import copy
import re
import unicodedata
import uuid

from src.shared.ifood_mcp import ErroMCP, _erro_em

# (nome, vertical, tempo de entrega, taxa, nota, distância km, pedido mínimo)
LOJAS = {
    'm1': ('Mercado Bom Preço', 'GROCERIES', {'min': 25, 'max': 35}, 4.99, 4.6, 1.2, 20.0),
    'm2': ('Supermercado Central', 'GROCERIES', {'min': 40, 'max': 55}, 0.0, 4.4, 2.8, 25.0),
    'm3': ('Padaria Pão Quente', 'GROCERIES', {'min': 15, 'max': 25}, 3.49, 4.8, 0.6, 15.0),
    'r1': ('Pizzaria Bella Napoli', 'RESTAURANT', {'min': 35, 'max': 50}, 6.90, 4.7, 2.1, 35.0),
    'r2': ('Cantina da Vó', 'RESTAURANT', {'min': 30, 'max': 40}, 4.50, 4.9, 1.0, 30.0),
    'f1': ('Drogaria Saúde', 'DRUGSTORE', {'min': 20, 'max': 30}, 2.99, 4.5, 0.9, 20.0),
    'b1': ('Adega do Zé', 'LIQUORSTORE', {'min': 25, 'max': 35}, 5.00, 4.3, 1.7, 30.0),
    'p1': ('Pet Feliz', 'PETSTORE', {'min': 40, 'max': 60}, 7.90, 4.6, 3.3, 40.0),
    'l1': ('Lanchonete do Bairro', 'RESTAURANT', {'min': 20, 'max': 35}, 3.99, 4.7, 0.8, 30.0),
    'r3': ('Esfiharia do Líbano', 'RESTAURANT', {'min': 25, 'max': 40}, 4.90, 4.6, 1.5, 20.0),
}

# grupo: (nome, minSelections, maxSelections, [(opção, preço adicional)])
_PIZZA = [('Tamanho', 1, 1, [('Média (6 fatias)', 0), ('Grande (8 fatias)', 12.0)]),
          ('Borda', 0, 1, [('Sem borda', 0), ('Catupiry', 8.0), ('Cheddar', 8.0)])]
_MARMITA = [('Acompanhamento', 1, 1, [('Arroz e feijão', 0), ('Arroz e purê', 0), ('Salada', 0)])]
# (loja, nome, descrição, preço, promo, grupos)
CATALOGO = [
    ('m3', 'Pão francês', 'Pacote com 10 unidades', 8.90, 7.90, None),
    ('m1', 'Pão francês', 'Pacote com 10 unidades', 9.50, None, None),
    ('m1', 'Pão de forma tradicional', 'Pacote 500 g', 9.49, None, None),
    ('m2', 'Pão de forma integral', 'Pacote 500 g', 11.20, 9.99, None),
    ('m3', 'Pão de queijo', 'Pacote com 12 unidades', 14.90, None, None),
    ('m2', 'Pão francês', 'Pacote com 6 unidades', 6.20, None, None),
    ('m3', 'Pão doce', 'Unidade', 4.50, None, None),
    ('m1', 'Bisnaguinha', 'Pacote 300 g', 7.99, 6.49, None),
    ('m2', 'Pão sírio', 'Pacote com 6 unidades', 8.79, None, None),
    ('m1', 'Leite integral', 'Caixa 1 litro', 5.49, 4.99, None),
    ('m2', 'Leite integral', 'Caixa 1 litro', 5.29, None, None),
    ('m1', 'Leite desnatado', 'Caixa 1 litro', 5.69, None, None),
    ('m2', 'Leite em pó', 'Lata 400 g', 21.90, 18.90, None),
    ('m3', 'Leite integral', 'Caixa 1 litro', 5.99, None, None),
    ('m1', 'Carne moída (patinho)', 'Bandeja 500 g', 22.90, None, None),
    ('m2', 'Picanha bovina', 'Peça aprox. 1 kg', 89.90, 79.90, None),
    ('m1', 'Contrafilé em bife', 'Bandeja 500 g', 34.90, None, None),
    ('m2', 'Alcatra em bife', 'Bandeja 500 g', 32.50, None, None),
    ('m1', 'Carne de panela (acém)', 'Bandeja 1 kg', 36.90, 33.90, None),
    ('m2', 'Peito de frango', 'Bandeja 1 kg', 19.90, None, None),
    ('m1', 'Arroz branco tipo 1', 'Pacote 5 kg', 27.90, 24.90, None),
    ('m2', 'Feijão carioca', 'Pacote 1 kg', 8.99, None, None),
    ('m1', 'Café torrado e moído', 'Pacote 500 g', 18.90, None, None),
    ('m3', 'Café torrado e moído', 'Pacote 250 g', 10.90, None, None),
    ('m2', 'Açúcar refinado', 'Pacote 1 kg', 4.99, None, None),
    ('m1', 'Banana prata', 'Cacho aprox. 1 kg', 6.90, None, None),
    ('m2', 'Ovos brancos', 'Bandeja com 12', 11.90, 10.49, None),
    ('m1', 'Manteiga com sal', 'Pote 200 g', 12.90, None, None),
    ('m3', 'Manteiga com sal', 'Pote 200 g', 13.50, None, None),
    ('m2', 'Sabão em pó', 'Caixa 1,6 kg', 24.90, 21.90, None),
    ('r1', 'Pizza de calabresa', 'Calabresa, cebola e azeitona', 49.90, None, _PIZZA),
    ('r1', 'Pizza de muçarela', 'Muçarela, tomate e orégano', 46.90, 42.90, _PIZZA),
    ('r1', 'Pizza portuguesa', 'Presunto, ovo, cebola e ervilha', 54.90, None, _PIZZA),
    ('r2', 'Marmita de frango grelhado', 'Frango, arroz, feijão e salada', 24.90, None, _MARMITA),
    ('r2', 'Marmita de carne de panela', 'Carne de panela, arroz e feijão', 27.90, 25.90, _MARMITA),
    ('r2', 'Sopa de legumes', 'Pote 500 ml', 19.90, None, None),
    ('f1', 'Dipirona 500 mg', 'Caixa com 10 comprimidos', 7.90, 5.99, None),
    ('f1', 'Paracetamol 750 mg', 'Caixa com 20 comprimidos', 12.90, None, None),
    ('f1', 'Fralda geriátrica G', 'Pacote com 8', 39.90, 34.90, None),
    ('b1', 'Cerveja pilsen lata', 'Pack com 12 latas 350 ml', 44.90, 39.90, None),
    ('b1', 'Vinho tinto suave', 'Garrafa 750 ml', 29.90, None, None),
    ('p1', 'Ração para cães adultos', 'Pacote 3 kg', 59.90, 49.90, None),
    ('p1', 'Ração para gatos', 'Pacote 1 kg', 29.90, None, None),
    # --- 17/10 21h: o que acompanha (sugestão do pedido mínimo), a lanchonete e o básico do dia a dia ---
    ('l1', 'X-Burger', 'Pão, hambúrguer 120 g, queijo e maionese da casa', 22.90, None, None),
    ('l1', 'X-Salada', 'Pão, hambúrguer 120 g, queijo, alface e tomate', 24.90, None, None),
    ('l1', 'X-Bacon', 'Pão, hambúrguer 120 g, queijo e bacon', 27.90, 25.90, None),
    ('l1', 'Misto quente', 'Pão de forma, presunto e queijo na chapa', 12.90, None, None),
    ('l1', 'Cachorro-quente', 'Salsicha, molho, milho e batata palha', 15.90, None, None),
    ('l1', 'Batata frita (porção)', 'Porção 300 g', 14.90, None, None),
    ('l1', 'Refrigerante lata 350 ml', 'Coca-Cola, Guaraná ou Sprite', 6.50, None, None),
    ('l1', 'Refrigerante 600 ml', 'Coca-Cola ou Guaraná', 8.50, None, None),
    ('l1', 'Suco natural de laranja', 'Copo 500 ml', 9.90, None, None),
    ('r1', 'Refrigerante 2 litros', 'Coca-Cola ou Guaraná', 13.90, None, None),
    ('r1', 'Pizza de chocolate', 'Chocolate ao leite e granulado', 44.90, None, _PIZZA),
    ('r2', 'Refrigerante lata 350 ml', 'Coca-Cola ou Guaraná', 6.00, None, None),
    ('r2', 'Suco natural de laranja', 'Copo 500 ml', 8.90, None, None),
    ('r2', 'Pudim de leite', 'Fatia', 9.90, None, None),
    ('m1', 'Refrigerante 2 litros', 'Coca-Cola', 11.99, 9.99, None),
    ('m2', 'Refrigerante 2 litros', 'Guaraná Antarctica', 9.49, None, None),
    ('m3', 'Refrigerante lata 350 ml', 'Coca-Cola', 5.50, None, None),
    ('m2', 'Manteiga com sal', 'Pote 200 g', 12.49, None, None),
    ('m2', 'Café torrado e moído', 'Pacote 500 g', 17.90, None, None),
    ('m2', 'Queijo muçarela fatiado', 'Bandeja 200 g', 12.90, None, None),
    ('m1', 'Queijo muçarela fatiado', 'Bandeja 200 g', 11.90, None, None),
    ('m3', 'Queijo minas frescal', 'Peça aprox. 400 g', 18.90, None, None),
    ('m1', 'Presunto fatiado', 'Bandeja 200 g', 8.90, None, None),
    ('m3', 'Bolo de fubá', 'Unidade aprox. 600 g', 16.90, None, None),
    ('m1', 'Achocolatado em pó', 'Lata 400 g', 9.90, None, None),
    ('m2', 'Iogurte natural', 'Pote 170 g', 3.49, None, None),
    ('m1', 'Água mineral sem gás', 'Garrafa 1,5 litro', 3.49, None, None),
    ('m2', 'Água mineral sem gás', 'Garrafa 1,5 litro', 2.99, None, None),
    ('m1', 'Óleo de soja', 'Garrafa 900 ml', 7.99, 6.99, None),
    ('m2', 'Macarrão espaguete', 'Pacote 500 g', 4.79, None, None),
    ('m1', 'Molho de tomate', 'Sachê 340 g', 3.29, None, None),
    ('m2', 'Feijão preto', 'Pacote 1 kg', 9.49, None, None),
    ('m2', 'Arroz branco tipo 1', 'Pacote 5 kg', 26.90, None, None),
    ('m1', 'Sal refinado', 'Pacote 1 kg', 2.99, None, None),
    ('m2', 'Farinha de trigo', 'Pacote 1 kg', 5.49, None, None),
    ('m1', 'Farofa pronta', 'Pacote 500 g', 6.90, None, None),
    ('m1', 'Cebola', 'Aprox. 1 kg', 5.99, None, None),
    ('m1', 'Tomate', 'Aprox. 1 kg', 7.49, None, None),
    ('m2', 'Batata', 'Aprox. 1 kg', 6.49, None, None),
    ('m2', 'Alho', 'Cabeça aprox. 100 g', 3.99, None, None),
    ('m2', 'Frango inteiro congelado', 'Aprox. 2,5 kg', 24.90, None, None),
    ('m2', 'Biscoito recheado', 'Pacote 140 g', 3.99, None, None),
    ('m1', 'Biscoito cream cracker', 'Pacote 200 g', 4.49, None, None),
    ('m2', 'Papel higiênico', 'Pacote com 12 rolos', 21.90, 18.90, None),
    ('m1', 'Detergente', 'Frasco 500 ml', 2.49, None, None),
    ('m2', 'Sabonete', 'Pacote com 4', 8.90, None, None),
    ('m1', 'Creme dental', 'Tubo 90 g', 4.99, None, None),
    ('m2', 'Água sanitária', 'Frasco 2 litros', 6.99, None, None),
    ('f1', 'Soro fisiológico', 'Frasco 500 ml', 6.90, None, None),
    ('f1', 'Vitamina C 1 g', 'Tubo com 10 comprimidos efervescentes', 14.90, 11.90, None),
    ('f1', 'Água mineral sem gás', 'Garrafa 500 ml', 2.50, None, None),
    ('b1', 'Refrigerante 2 litros', 'Coca-Cola', 12.90, None, None),
    ('b1', 'Gelo', 'Saco 5 kg', 9.90, None, None),
    ('b1', 'Carvão', 'Saco 3 kg', 19.90, None, None),
    ('p1', 'Areia para gatos', 'Pacote 4 kg', 24.90, None, None),
    ('p1', 'Petisco para cães', 'Pacote 65 g', 9.90, None, None),
    ('r1', 'Pizza margherita', 'Muçarela, tomate e manjericão', 48.90, None, _PIZZA),
    ('r1', 'Pizza de frango com catupiry', 'Frango desfiado e catupiry', 52.90, 47.90, _PIZZA),
    ('r1', 'Pizza quatro queijos', 'Muçarela, provolone, parmesão e catupiry', 56.90, None, _PIZZA),
    ('r3', 'Esfiha de carne', 'Esfiha aberta, carne temperada', 6.90, None, None),
    ('r3', 'Esfiha de queijo', 'Esfiha aberta, muçarela', 6.90, None, None),
    ('r3', 'Esfiha de calabresa', 'Esfiha aberta, calabresa e cebola', 7.50, None, None),
    ('r3', 'Esfiha de frango com catupiry', 'Esfiha fechada', 7.90, None, None),
    ('r3', 'Kibe frito', 'Unidade', 6.50, None, None),
    ('r3', 'Pastel de carne', 'Pastel grande', 9.90, None, None),
    ('r3', 'Pastel de queijo', 'Pastel grande', 9.90, None, None),
    ('r3', 'Coxinha de frango', 'Unidade', 6.90, None, None),
    ('r3', 'Refrigerante lata 350 ml', 'Coca-Cola ou Guaraná', 6.00, None, None),
    ('r3', 'Suco natural de laranja', 'Copo 500 ml', 8.90, None, None),
    ('r2', 'Lasanha à bolonhesa', 'Porção individual', 32.90, 29.90, None),
    ('r2', 'Strogonoff de frango', 'Com arroz e batata palha', 28.90, None, None),
    ('r2', 'Parmegiana de carne', 'Com arroz e fritas', 34.90, None, None),
    ('r2', 'Feijoada', 'Porção individual com acompanhamentos', 36.90, None, None),
]
SINONIMOS = {'paozinho': ['pao frances'], 'carne': ['carne', 'picanha', 'contrafile', 'alcatra', 'acem'],
             'remedio': ['dipirona', 'paracetamol'], 'racao': ['racao'], 'almoco': ['marmita', 'sopa'],
             'refeicao': ['marmita'], 'frios': ['queijo', 'presunto', 'manteiga'],
             'refri': ['refrigerante'], 'coca': ['refrigerante'], 'guarana': ['refrigerante'],
             'lanche': ['x-', 'misto', 'cachorro'], 'sanduiche': ['x-', 'misto'], 'hamburguer': ['x-', 'burger'],
             'bolacha': ['biscoito'], 'sobremesa': ['pudim', 'bolo', 'chocolate'],
             'doce': ['doce', 'chocolate', 'pudim', 'bolo'], 'bebida': ['refrigerante', 'suco', 'agua mineral'],
             'margarita': ['margherita'], 'marguerita': ['margherita'], 'mussarela': ['mucarela'],
             'muzzarela': ['mucarela'], 'esfirra': ['esfiha'], 'quibe': ['kibe'],
             'salgado': ['coxinha', 'esfiha', 'pastel', 'kibe'], 'estrogonofe': ['strogonoff'],
             'strogonof': ['strogonoff']}
# não ajudam a achar produto: "pão de forma" é pão + forma, e o "de" casava com meio catálogo
PALAVRAS_VAZIAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'com', 'sem', 'pra', 'para', 'um', 'uma', 'o', 'a',
                   'os', 'as', 'em', 'no', 'na', 'in', 'natura', 'kg', 'g', 'ml', 'l', 'un'}
PAGAMENTOS = [('CREDIT_CARD', 'Cartão de Crédito'), ('DEBIT_CARD', 'Cartão de Débito'), ('PIX', 'PIX'),
              ('MEAL_VOUCHER', 'Vale Refeição')]
STATUS = [('ORDER_CREATED', 'Order created.'), ('CONFIRMED', 'Merchant confirmed the order.'),
          ('PREPARING', 'Merchant is preparing the order.'), ('DISPATCHED', 'Merchant released order for delivery.'),
          ('ON_THE_WAY', 'Delivery person is on the way.'),
          ('DELIVERY_ARRIVED_AT_DESTINATION', 'Delivery person arrived at order delivery address.'),
          ('DELIVERED', 'Order delivered to the customer.')]
COORD = {'latitude': -22.0087, 'longitude': -47.8909}  # São Carlos


def _n(s):
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def _uid(*partes):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'hackfood:' + ':'.join(map(str, partes))))


def _img(nome):
    texto = _n(nome).replace(' ', '+')[:40]
    return f'https://placehold.co/800x500/1f8f4e/ffffff/png?text={texto}'


def _loja(chave):
    nome, _tipo, eta, taxa, nota, dist, _minimo = LOJAS[chave]
    return {'merchantId': _uid('loja', chave), 'merchantName': nome,
            'merchantLogoUrl': _img(nome), 'reviewRating': nota, 'isOpen': True,
            'deliveryMethod': {'deliveryMethodMode': 'DELIVERY', 'fee': taxa, 'promotionalFee': None,
                               'estimatedMinutes': eta},
            'straightLineDistanceKm': dist, 'nextOpenAt': None}


def _resultado_item(i):
    lj, nome, _desc, preco, promo, _g = CATALOGO[i]
    r = {'itemId': _uid('item', i), 'itemName': nome, 'itemImageUrl': _img(nome), 'unitPrice': preco,
         'merchant': _loja(lj), 'matchScore': 0.9}
    if promo:
        r['promotionalUnitPrice'] = promo
    return r


_ITEM_POR_ID = {_uid('item', i): i for i in range(len(CATALOGO))}
_LOJA_POR_ID = {_uid('loja', k): k for k in LOJAS}


def loja_do_mock(merchant_id):
    """A loja é deste mock? O bot usa pra largar o carrinho do iFood real quando o mock liga (e vice-versa)."""
    return merchant_id in _LOJA_POR_ID


def _erro_discovery(codigo, msg, retry=False):
    return ErroMCP(codigo, msg, tentar_de_novo=retry,
                   bruto={'errors': {'mcpCode': -32301, 'code': codigo, 'message': msg, 'retryable': retry}})


def _erro_cart(codigo, msg, amigavel):
    return ErroMCP(codigo, msg, para_usuario=amigavel,
                   bruto={'error': {'code': codigo, 'message': msg, 'details': {}, 'userFriendlyMessage': amigavel}})


class McpFake:
    def __init__(self, armazem=None, chave='mock'):
        self.armazem = armazem if armazem is not None else {}
        self.chave = chave
        self.chamadas = []  # (tool, args) na ordem, pros testes conferirem

    # --- estado ---

    def _st(self):
        st = self.armazem.get(self.chave)
        if not st:
            st = {'enderecos': [], 'carrinhos': {}, 'pedidos': {}, 'candidatos': {}, 'seq': 0}
        return copy.deepcopy(st)

    def chamar(self, ferramenta, **args):
        args = {k: v for k, v in args.items() if v is not None}
        self.chamadas.append((ferramenta, copy.deepcopy(args)))
        fn = getattr(self, f't_{ferramenta}', None)
        if not fn:
            raise ErroMCP('RPC_-32602', f'Unknown tool: {ferramenta}')
        st = self._st()
        try:
            r = fn(st, **args)
        finally:
            self.armazem[self.chave] = st
        erro = _erro_em(r)  # mesmo tratamento do cliente real (ex.: erro do Order Tracking na raiz)
        if erro:
            raise erro
        return r

    def chamadas_de(self, ferramenta):
        return [a for t, a in self.chamadas if t == ferramenta]

    # --- User ---

    def t_getUser(self, st):
        # demo: usa o nome do perfil de WhatsApp da pessoa (o bot guarda em u:{wa_id}['nome']);
        # sem isso, um nome genérico. No real, isto vem da conta iFood de verdade.
        wa_id = self.chave.split(':', 1)[-1]
        nome = (self.armazem.get(f'u:{wa_id}') or {}).get('nome') or 'Cliente'
        return {'success': True, 'data': {'fullName': nome, 'email': 'cliente@test.ifood.com.br',
                                          'phone': '5520900000000'}, 'agentHints': {}}

    def t_listAddresses(self, st):
        if not st['enderecos']:
            return {'results': [], 'agentHints': {'noResultsGuidance': 'No saved addresses found.'}}
        return {'results': st['enderecos'], 'agentHints': {'addressCount': len(st['enderecos'])}}

    def t_createAddress(self, st, address=None, candidateId=None, complement=None, alias=None,
                        neighborhood=None, reference=None):
        if candidateId:
            cand = st['candidatos'].get(candidateId)
            if not cand:
                raise ErroMCP('MISSING_CANDIDATE_ID', 'candidateId desconhecido',
                              bruto={'errors': {'mcpCode': -32304, 'code': 'MISSING_CANDIDATE_ID'}})
            bairro = neighborhood or cand['location']['neighborhood']
            if not bairro:
                raise ErroMCP('MISSING_NEIGHBORHOOD', 'bairro obrigatório', tentar_de_novo=False,
                              bruto={'errors': {'mcpCode': -32301, 'code': 'MISSING_NEIGHBORHOOD'}})
            loc = {**cand['location'], 'neighborhood': bairro}
            partes = [loc['street'], loc['number']] + ([complement] if complement else []) + [bairro, loc['city'], loc['state']]
            end = {'addressId': _uid('end', self.chave, candidateId), 'alias': alias,
                   'formattedAddress': ', '.join(p for p in partes if p), 'location': loc,
                   'complement': complement, 'reference': reference, 'coordinates': dict(COORD),
                   'isLastUsedAddress': True, 'isMostUsedAddress30d': True}
            for e in st['enderecos']:
                e['isLastUsedAddress'] = False
            st['enderecos'] = [e for e in st['enderecos'] if e['addressId'] != end['addressId']] + [end]
            return {**end, 'agentHints': {'nextStepWhenUserPicksAddress': 'Address saved.'}}
        texto = (address or '').strip()
        if not texto:
            raise ErroMCP('MISSING_ADDRESS', 'endereço vazio', bruto={'errors': {'code': 'MISSING_ADDRESS'}})
        if not any(ch.isdigit() for ch in texto) or len(texto) < 8:
            raise ErroMCP('PLACE_NOT_FOUND', 'endereço não encontrado', tentar_de_novo=False,
                          bruto={'errors': {'mcpCode': -32301, 'code': 'PLACE_NOT_FOUND'}})
        # "Rua X, 120, Cidade" ou "rua x 120 cidade": rua é o que vem antes do 1º número
        m = re.search(r'\d+', texto)
        rua = texto[:m.start()].strip(' ,-') if m and m.start() > 0 else texto.partition(',')[0]
        numero = m.group(0)[:6] if m else '1'
        rua = ' '.join(p if p in ('de', 'da', 'do', 'das', 'dos', 'e') else p.capitalize() for p in rua.lower().split())
        sem_bairro = 'sem bairro' in _n(texto)  # gatilho de teste pro fluxo do bairro
        bairros = [''] if sem_bairro else ['Centro', 'Jardim São Paulo']
        cands = []
        for bairro in bairros:
            cid = f'cand-{_uid(texto, bairro)[:8]}'
            loc = {'street': rua, 'number': numero, 'neighborhood': bairro, 'city': 'São Carlos', 'state': 'SP'}
            c = {'candidateId': cid, 'location': loc, 'postalCode': '13560-000', 'coordinates': dict(COORD),
                 'formattedAddress': ', '.join(p for p in (loc['street'], numero, bairro, 'São Carlos', 'SP') if p)}
            st['candidatos'][cid] = c
            cands.append(c)
        return {'matchConfidence': 'SINGLE' if len(cands) == 1 else 'MULTIPLE', 'candidates': cands,
                'agentHints': {'confirmAddressGuidance': 'Confirm with the user.'}}

    # --- Offer Discovery ---

    def t_searchOffers(self, st, query='', userLocation=None, resultKind='MERCHANT', merchantType=None,
                       refinements=None, pageSize=10, nextPageToken=None):
        if not isinstance(userLocation, dict) or 'latitude' not in userLocation:
            raise _erro_discovery('MISSING_LOCATION', 'No delivery location provided.', True)
        if not _n(query).strip():
            raise _erro_discovery('INVALID_QUERY', 'The search query is empty.', True)
        refin = refinements or {}
        todas = re.findall(r'[a-z0-9]+', _n(query))
        palavras = [t for t in todas if t not in PALAVRAS_VAZIAS and len(t) > 1] or todas
        alvos = [SINONIMOS.get(t, [t]) for t in palavras]  # cada palavra casa com ela ou um sinônimo
        pontos = {}
        for i, (lj, nome, _d, preco, promo, _g) in enumerate(CATALOGO):
            if merchantType and LOJAS[lj][1] != merchantType:
                continue
            if refin.get('merchantId') and _uid('loja', lj) != refin['merchantId']:
                continue
            if refin.get('maxItemPrice') and (promo or preco) > float(refin['maxItemPrice']):
                continue
            nn = _n(nome)
            casou = [any(a in nn for a in alts) for alts in alvos]
            if any(casou):
                pontos[i] = (sum(casou), casou[0])
        # 1º quem tem todas as palavras; depois quem tem a 1ª, o produto ("leite" de "leite integral"),
        # do que casa mais pro que casa menos; o resto só se não sobrou nada
        cheios = [i for i, (n, _p) in pontos.items() if n == len(alvos)]
        do_produto = sorted((i for i, (n, p) in pontos.items() if p and n < len(alvos)),
                            key=lambda i: -pontos[i][0])
        achados = (cheios + do_produto) or sorted(pontos, key=lambda i: -pontos[i][0])
        tam = max(1, min(int(pageSize or 10), 25))
        ini = int(nextPageToken or 0)
        pagina = achados[ini:ini + tam]
        mais = ini + tam < len(achados)
        if resultKind == 'ITEM':
            results = [_resultado_item(i) for i in pagina]
        else:
            vistos, results = set(), []
            for i in pagina:
                if CATALOGO[i][0] not in vistos:
                    vistos.add(CATALOGO[i][0])
                    results.append(_loja(CATALOGO[i][0]))
        resp = {'resultKind': resultKind, 'interpretedQuery': query, 'results': results, 'facets': {},
                'nextPageToken': str(ini + tam) if mais else None, 'hasMore': mais, 'agentHints': {}}
        if not results:
            resp['agentHints'] = {'noResultsGuidance': f"No results found for '{query}' in this area."}
        return resp

    def t_browseOffers(self, st, merchantType=None, userLocation=None, resultKind='MERCHANT', **kw):
        if not merchantType:
            raise _erro_discovery('MISSING_MERCHANT_VERTICAL', 'merchantType is required for browseOffers.', True)
        return self.t_searchOffers(st, 'a', userLocation, resultKind, merchantType, **kw)

    def t_getMerchant(self, st, merchantId, userLocation=None):
        if merchantId not in _LOJA_POR_ID:
            raise _erro_discovery('MERCHANT_NOT_FOUND', 'merchant not found')
        lj = _LOJA_POR_ID[merchantId]
        return {**_loja(lj), 'merchantType': LOJAS[lj][1], 'minimumOrderAmount': LOJAS[lj][6],
                'deliveryMethods': [{'deliveryMethodId': 'ECONOMIC', 'deliveryMethodMode': 'DELIVERY',
                                     'fee': LOJAS[lj][3], 'estimatedMinutes': LOJAS[lj][2]}]}

    def t_getItem(self, st, itemId, merchantId=None, userLocation=None):
        if not isinstance(userLocation, dict):
            raise _erro_discovery('MISSING_LOCATION', 'userLocation required', True)
        if itemId not in _ITEM_POR_ID:
            raise _erro_discovery('ITEM_NOT_FOUND', 'item not found')
        i = _ITEM_POR_ID[itemId]
        lj, nome, desc, preco, promo, grupos = CATALOGO[i]
        if merchantId and merchantId != _uid('loja', lj):
            raise _erro_discovery('ITEM_MERCHANT_MISMATCH', 'item does not belong to merchant', True)
        d = {'itemId': itemId, 'itemName': nome, 'merchantId': _uid('loja', lj), 'merchantName': LOJAS[lj][0],
             'unitPrice': preco, 'itemDescription': desc, 'itemImageUrl': _img(nome),
             'optionGroups': [{'optionGroupId': _uid('grupo', i, gi), 'name': gn, 'minSelections': mn,
                               'maxSelections': mx,
                               'options': [{'optionId': _uid('op', i, gi, oi), 'name': on, 'description': on,
                                            'additionalPrice': op} for oi, (on, op) in enumerate(ops)]}
                              for gi, (gn, mn, mx, ops) in enumerate(grupos or [])],
             'agentHints': {'nextStep': 'Add this item to the active cart.'}}
        if promo:
            d['promotionalUnitPrice'] = promo
        return d

    def t_getRecommendations(self, st, contentMode=None, userLocation=None, resultKind='MERCHANT', **_):
        if contentMode != 'RECENT_ORDERS':
            return {'contentMode': contentMode, 'resultKind': resultKind, 'results': [], 'hasMore': False}
        results = []
        for p in sorted(st['pedidos'].values(), key=lambda p: -p['seq']):
            for it in p['items']:
                i = _ITEM_POR_ID[it['itemId']]
                results.append({**_resultado_item(i), 'lastOrderId': p['orderId'], 'timesOrdered': 1,
                                'lastOrderedAt': f'2026-10-{10 + p["seq"] % 9:02d}T12:00:00Z'})
        return {'contentMode': 'RECENT_ORDERS', 'resultKind': 'ITEM', 'results': results[:25],
                'nextPageToken': None, 'hasMore': False}

    # --- Cart ---

    def _opcoes_validas(self, i, options):
        """Aceita o modo A (optionId = grupo, customizations = opções), como a doc descreve."""
        grupos = CATALOGO[i][5] or []
        escolhidas = {}
        for o in options:
            if 'quantity' not in o or 'customizations' not in o:
                raise _erro_cart('INVALID_OPTION', 'Option.quantity e Option.customizations são obrigatórios',
                                 'Opção inválida.')
            gi = next((g for g in range(len(grupos)) if _uid('grupo', i, g) == o['optionId']), None)
            if gi is None:
                raise _erro_cart('INVALID_OPTION', f'optionId {o["optionId"]} não é um grupo deste item',
                                 'Opção inválida.')
            ids = {_uid('op', i, gi, oi): oi for oi in range(len(grupos[gi][3]))}
            for c in o['customizations']:
                if c.get('customizationId') not in ids:
                    raise _erro_cart('INVALID_OPTION', 'customizationId inválido', 'Opção inválida.')
                escolhidas.setdefault(gi, []).append(ids[c['customizationId']])
        for gi, (gn, mn, mx, _ops) in enumerate(grupos):
            n = len(escolhidas.get(gi, []))
            if n < mn or n > mx:
                raise _erro_cart('ITEM_NOT_AVAILABLE' if False else 'INVALID_OPTION',
                                 f'grupo {gn}: escolha entre {mn} e {mx}', f'Escolha {gn}.')
        return escolhidas

    def _linha(self, st, it):
        iid = it.get('itemId')
        if iid not in _ITEM_POR_ID:
            raise _erro_cart('ITEM_NOT_AVAILABLE', 'item fora do cardápio', 'Esse item não está disponível.')
        if 'options' not in it:
            raise _erro_cart('INVALID_REQUEST', 'options é obrigatório (pode ser [])', 'Erro no pedido.')
        i = _ITEM_POR_ID[iid]
        escolhidas = self._opcoes_validas(i, it['options'])
        unit = CATALOGO[i][4] or CATALOGO[i][3]
        for gi, ois in escolhidas.items():
            unit += sum(CATALOGO[i][5][gi][3][oi][1] for oi in ois)
        st['seq'] += 1
        return {'itemId': iid, 'cartItemId': _uid('cartitem', self.chave, st['seq']), 'name': CATALOGO[i][1],
                'quantity': int(it.get('quantity') or 1), 'unitPrice': round(unit, 2),
                'customerNote': it.get('customerNote'), 'options': it['options']}

    def _resposta(self, car):
        sub = round(sum(it['unitPrice'] * it['quantity'] for it in car['items']), 2)
        taxa = LOJAS[_LOJA_POR_ID[car['merchant']['merchantId']]][3] if car.get('deliveryMethod') else 0.0
        cupom = car.get('voucher', {}).get('valor', 0.0) if car.get('voucher') else 0.0
        car['summary'] = {'totalName': 'Total', 'totalAmount': round(max(0.0, sub + taxa - cupom), 2),
                          'subtotalName': 'Subtotal', 'subtotalAmount': sub,
                          'deliveryFeeName': 'Taxa de entrega', 'deliveryFeeAmount': taxa,
                          'feeTotalName': 'Taxas', 'feeTotalAmount': 0.0,
                          'benefitsTotalName': 'Benefícios', 'benefitsTotalAmount': 0.0,
                          'voucherTotalName': 'Cupom', 'voucherTotalAmount': cupom}
        r = {k: v for k, v in car.items() if not k.startswith('_') and k != 'voucher'}
        r['appDeeplink'] = f'ifoodapp://cart/{car["cartId"]}'
        r['agentHints'] = {'nextStep': 'Configure entrega e pagamento antes de enviar o pedido.'}
        return copy.deepcopy(r)

    def _carrinho(self, st, cid):
        car = st['carrinhos'].get(cid)
        if not car or car.get('_enviado'):
            raise _erro_cart('CART_NOT_FOUND', f"O carrinho '{cid}' não foi encontrado.",
                             'Carrinho não encontrado. Crie um novo carrinho.')
        return car

    def t_createCart(self, st, merchantId=None, addressId=None, items=None, orderId=None, **_):
        if orderId:
            ped = st['pedidos'].get(orderId)
            if not ped:
                raise _erro_cart('ORDER_NOT_FOUND', 'pedido não encontrado', 'Pedido não encontrado.')
            merchantId, addressId = ped['merchantId'], ped['addressId']
            items = [{'itemId': it['itemId'], 'quantity': it['quantity'], 'options': it.get('options', [])}
                     for it in ped['items']]
        if merchantId not in _LOJA_POR_ID:
            raise _erro_cart('MERCHANT_NOT_FOUND', 'merchant not found', 'Restaurante não encontrado.')
        if not addressId:
            raise _erro_cart('INVALID_REQUEST', 'addressId obrigatório', 'Endereço não informado.')
        if not items:
            raise _erro_cart('CART_EMPTY', 'items vazio', 'Seu carrinho está vazio.')
        linhas = [self._linha(st, it) for it in items]
        for lin in linhas:
            if CATALOGO[_ITEM_POR_ID[lin['itemId']]][0] != _LOJA_POR_ID[merchantId]:
                raise _erro_cart('ITEM_NOT_AVAILABLE', 'item de outra loja', 'Esse item não é desta loja.')
        st['seq'] += 1
        cid = _uid('cart', self.chave, st['seq'])
        lj = _LOJA_POR_ID[merchantId]
        end = next((e for e in st['enderecos'] if e['addressId'] == addressId), {})
        loc = end.get('location') or {}
        car = {'cartId': cid, 'merchant': {'merchantId': merchantId, 'merchantName': LOJAS[lj][0],
                                           'orderMinimumPrice': LOJAS[lj][6], 'formattedAddress': 'Rua da Loja, 10'},
               'items': linhas, 'deliveryAddress': {'streetName': loc.get('street'), 'streetNumber': loc.get('number'),
                                                    'neighborhood': loc.get('neighborhood')},
               'deliveryMethod': None, 'paymentMethod': None, 'fees': [], 'warning': None, '_endereco': addressId}
        st['carrinhos'][cid] = car
        return self._resposta(car)

    def t_getCart(self, st, cartId):
        return self._resposta(self._carrinho(st, cartId))

    def t_addItemToCart(self, st, cartId, itemId, quantity=1, options=None, customerNote=None):
        car = self._carrinho(st, cartId)
        if options is None:
            raise _erro_cart('INVALID_REQUEST', 'options é obrigatório (pode ser [])', 'Erro no pedido.')
        if itemId in _ITEM_POR_ID and _uid('loja', CATALOGO[_ITEM_POR_ID[itemId]][0]) != car['merchant']['merchantId']:
            raise _erro_cart('ITEM_NOT_AVAILABLE', 'item de outra loja', 'Esse item não é desta loja.')
        car['items'].append(self._linha(st, {'itemId': itemId, 'quantity': quantity, 'options': options,
                                             'customerNote': customerNote}))
        return self._resposta(car)

    def t_updateCartItem(self, st, cartId, cartItemId, itemId, quantity=1, options=None, customerNote=None):
        car = self._carrinho(st, cartId)
        for it in car['items']:
            if it['cartItemId'] == cartItemId and it['itemId'] == itemId:
                it['quantity'] = int(quantity)
                return self._resposta(car)
        raise _erro_cart('CART_ITEM_NOT_FOUND', 'cartItemId não encontrado', 'Item não encontrado no carrinho.')

    def t_removeItemFromCart(self, st, cartId, cartItemId):
        car = self._carrinho(st, cartId)
        restantes = [it for it in car['items'] if it['cartItemId'] != cartItemId]
        if len(restantes) == len(car['items']):
            raise _erro_cart('CART_ITEM_NOT_FOUND', 'cartItemId não encontrado', 'Item não encontrado no carrinho.')
        if not restantes:
            st['carrinhos'].pop(cartId, None)
            return {'agentHints': {'cartDeletedAfterLastItemRemoved': 'O último item foi removido e o carrinho foi excluído.'}}
        car['items'] = restantes
        return self._resposta(car)

    def t_getCartDeliveryMethods(self, st, cartId):
        car = self._carrinho(st, cartId)
        car['_entregas_vistas'] = True
        lj = _LOJA_POR_ID[car['merchant']['merchantId']]
        eta, taxa = LOJAS[lj][2], LOJAS[lj][3]
        return {'cartId': cartId, 'deliveryMethods': [
            {'deliveryMethodId': 'DEFAULT', 'deliveryMethodMode': 'DELIVERY', 'deliveryMethodName': 'Entrega Padrão',
             'fee': taxa, 'estimatedMinutes': eta, 'timeslots': None},
            {'deliveryMethodId': 'EXPRESS', 'deliveryMethodMode': 'DELIVERY', 'deliveryMethodName': 'Entrega Expressa',
             'fee': round(taxa + 6, 2), 'estimatedMinutes': {'min': max(10, eta['min'] - 10), 'max': eta['max'] - 10},
             'timeslots': None},
            {'deliveryMethodId': 'SCHEDULED', 'deliveryMethodMode': 'DELIVERY', 'deliveryMethodName': 'Entrega Agendada',
             'fee': taxa, 'estimatedMinutes': {'min': 120, 'max': 180},
             'timeslots': [{'from': '2026-10-18T18:00:00Z', 'to': '2026-10-18T18:30:00Z'}]},
            {'deliveryMethodId': 'TAKEOUT', 'deliveryMethodMode': 'TAKEOUT', 'deliveryMethodName': 'Retirada no local',
             'fee': 0.0, 'estimatedMinutes': {'min': 15, 'max': 25}, 'timeslots': None}],
            'warning': None, 'agentHints': {}}

    def t_setCartDelivery(self, st, cartId, deliveryMethodId, selectedTimeSlotId=None):
        car = self._carrinho(st, cartId)
        if not car.get('_entregas_vistas'):
            raise _erro_cart('DELIVERY_METHOD_UNAVAILABLE', 'chame getCartDeliveryMethods antes',
                             'Esta modalidade de entrega não está disponível.')
        nomes = {'DEFAULT': 'Entrega Padrão', 'EXPRESS': 'Entrega Expressa'}
        if deliveryMethodId not in nomes:
            raise _erro_cart('DELIVERY_METHOD_UNAVAILABLE', f'método {deliveryMethodId} indisponível',
                             'Esta modalidade de entrega não está disponível.')
        lj = _LOJA_POR_ID[car['merchant']['merchantId']]
        car['deliveryMethod'] = {'deliveryMethodMode': 'DELIVERY', 'deliveryMethodName': nomes[deliveryMethodId],
                                 'fee': LOJAS[lj][3], 'estimatedMinutes': LOJAS[lj][2], 'timeSlot': None}
        return self._resposta(car)

    def t_listPaymentMethods(self, st, merchantId):
        if merchantId not in _LOJA_POR_ID:
            raise _erro_cart('MERCHANT_NOT_FOUND', 'merchant not found', 'Restaurante não encontrado.')
        return {'paymentMethods': [{'paymentMethodId': _uid('pag', kind, merchantId), 'kind': kind,
                                    'displayName': nome, 'cardTokenId': None, 'brand': None, 'issuerBank': None}
                                   for kind, nome in PAGAMENTOS],
                'agentHints': {'nextStep': 'Para CREDIT_CARD e DEBIT_CARD, um cardTokenId será necessário.'}}

    def t_setCartPayment(self, st, cartId, paymentMethodId, cardTokenId=None):
        car = self._carrinho(st, cartId)
        mid = car['merchant']['merchantId']
        validos = {_uid('pag', kind, mid): (kind, nome) for kind, nome in PAGAMENTOS}
        if paymentMethodId not in validos:
            raise _erro_cart('PAYMENT_METHOD_UNAVAILABLE', f"A forma de pagamento '{paymentMethodId}' não é aceita.",
                             'Esta forma de pagamento não é aceita por este restaurante. Escolha outra opção.')
        kind, nome = validos[paymentMethodId]
        if kind in ('CREDIT_CARD', 'DEBIT_CARD') and not cardTokenId:
            raise _erro_cart('CARD_TOKEN_REQUIRED', 'cardTokenId obrigatório para cartão',
                             'Para pagar com cartão, cadastre o cartão no app do iFood.')
        car['paymentMethod'] = {'paymentMethodId': paymentMethodId, 'kind': kind, 'displayName': nome,
                                'cardTokenId': cardTokenId, 'brand': None, 'issuerBank': None}
        return self._resposta(car)

    def t_listVouchers(self, st, cartId):
        car = self._carrinho(st, cartId)
        sub = sum(it['unitPrice'] * it['quantity'] for it in car['items'])
        if sub < 30:
            return {'vouchers': [], 'agentHints': {'noResultsGuidance': 'Nenhum voucher se aplica.'}}
        return {'vouchers': [{'code': 'VCH-5', 'campaignId': _uid('camp', 'vch5'), 'effectType': 'FIXED',
                              'effectValue': 5.0, 'maxDiscountValue': None,
                              'description': 'R$5 de desconto em pedidos acima de R$30', 'available': True}],
                'agentHints': {}}

    def t_setVoucher(self, st, cartId, code, campaignId):
        car = self._carrinho(st, cartId)
        if code != 'VCH-5' or campaignId != _uid('camp', 'vch5'):
            raise _erro_cart('VOUCHER_INVALID', f"O voucher '{code}' não pôde ser aplicado.",
                             'Este cupom não pode ser aplicado a este carrinho.')
        car['voucher'] = {'code': code, 'valor': 5.0}
        return self._resposta(car)

    def t_removeVoucher(self, st, cartId):
        car = self._carrinho(st, cartId)
        car.pop('voucher', None)
        return self._resposta(car)

    def t_submitOrder(self, st, cartId, userConsent=False, document=None):
        car = self._carrinho(st, cartId)
        if userConsent is not True:
            raise _erro_cart('CONSENT_REQUIRED', 'userConsent deve ser true',
                             'Você precisa confirmar que deseja finalizar o pedido.')
        faltam = [k for k in ('deliveryMethod', 'paymentMethod') if not car.get(k)]
        if not car['items']:
            faltam.insert(0, 'items')
        if faltam:
            raise _erro_cart('CART_NOT_READY', f'Faltando: {faltam}',
                             'Seu carrinho não está pronto. Configure ' + ', '.join(faltam) + '.')
        car['_enviado'] = True
        st['seq'] += 1
        oid = _uid('pedido', self.chave, st['seq'])
        st['pedidos'][oid] = {'orderId': oid, 'seq': st['seq'], 'merchantId': car['merchant']['merchantId'],
                              'merchantName': car['merchant']['merchantName'], 'addressId': car['_endereco'],
                              'items': car['items'], 'total': car['summary']['totalAmount'],
                              'pagamento': car['paymentMethod']['displayName'], 'consultas': 0,
                              'codigo': 'ABCD'[st['seq'] % 4] + str(1000 + st['seq'])}
        return {'orderId': oid, 'agentHints': {'nextStep': 'Pedido enviado com sucesso! Comece a rastrear com trackOrder.'}}

    # --- Order Tracking ---

    def t_trackOrder(self, st, orderId):
        ped = st['pedidos'].get(orderId)
        if not ped:
            return {'errorType': 'ResourceNotFoundError', 'code': 'ORDER_NOT_FOUND',
                    'message': f"Order ID '{orderId}' not found", 'retryable': False,
                    'suggestion': 'Do not attempt to look up this Order ID again.'}
        i = min(ped['consultas'], len(STATUS) - 1)
        ped['consultas'] += 1
        cod, desc = STATUS[i]
        fim = cod == 'DELIVERED'
        return {'status': {'code': cod, 'description': desc},
                'statusHistory': [{'code': c, 'description': d} for c, d in reversed(STATUS[:i + 1])][:5],
                'agentHints': {'retryMessage': None if fim else 'Please call again in 20 seconds for updates',
                               'moreStatusEvents': None, 'pollingStop': True if fim else None,
                               'stopMessage': 'Do not call this tool for this order.' if fim else None}}

    def t_getOrder(self, st, orderId):
        ped = st['pedidos'].get(orderId)
        if not ped:
            return {'errorType': 'ResourceNotFoundError', 'code': 'ORDER_NOT_FOUND',
                    'message': f"Order ID '{orderId}' not found", 'retryable': True, 'suggestion': 'Retry.'}
        return {'id': orderId, 'shortCode': ped['codigo'], 'merchant': ped['merchantName'],
                'items': [f'{it["name"]} (x{it["quantity"]}, R$ {it["unitPrice"] * it["quantity"]:.2f})'
                          for it in ped['items']],
                'payment': f'{ped["pagamento"]} - Total R$ {ped["total"]:.2f}',
                'delivery': {'address': 'Endereço do cliente', 'verificationCode': ped['codigo'][-4:]}}
