"""MCP falso do iFood: mesmas tools do gateway, dados inventados, estado num dicionário.

Serve pra desenvolver, testar e fazer demo sem credencial (o agente do portal está em
análise). `chamar()` tem a mesma assinatura do ClienteMCP real e levanta ErroMCP do mesmo
jeito, então quem usa não sabe a diferença. As respostas imitam o formato documentado
(lowerCamelCase, IDs UUID, preço decimal em BRL, paginação com nextPageToken).

O estado (endereços, carrinhos, pedidos) fica em `armazem[chave]`: em produção, o mesmo
modal.Dict do bot, então sobrevive entre uma mensagem e outra.

Uso: McpFake().chamar('searchOffers', query='pão', userLocation={'addressId': ...})
"""
import copy
import unicodedata
import uuid

from src.shared.ifood_mcp import ErroMCP

LOJAS = {
    'm1': ('Mercado Bom Preço', 'GROCERIES', {'min': 25, 'max': 35}, 4.99),
    'm2': ('Supermercado Central', 'GROCERIES', {'min': 40, 'max': 55}, 0.0),
    'm3': ('Padaria Pão Quente', 'GROCERIES', {'min': 15, 'max': 25}, 3.49),
    'r1': ('Pizzaria Bella Napoli', 'RESTAURANT', {'min': 35, 'max': 50}, 6.90),
    'r2': ('Cantina da Vó', 'RESTAURANT', {'min': 30, 'max': 40}, 4.50),
    'f1': ('Drogaria Saúde', 'DRUGSTORE', {'min': 20, 'max': 30}, 2.99),
    'b1': ('Adega do Zé', 'LIQUORSTORE', {'min': 25, 'max': 35}, 5.00),
    'p1': ('Pet Feliz', 'PETSTORE', {'min': 40, 'max': 60}, 7.90),
}

# (loja, nome, descrição, preço, promo, grupos)
_PIZZA = [('Tamanho', 1, 1, [('Média (6 fatias)', 0), ('Grande (8 fatias)', 12.0)]),
          ('Borda', 0, 1, [('Sem borda', 0), ('Catupiry', 8.0), ('Cheddar', 8.0)])]
_MARMITA = [('Acompanhamento', 1, 1, [('Arroz e feijão', 0), ('Arroz e purê', 0), ('Salada', 0)])]
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
    ('m1', 'Carne moída (patinho)', 'Bandeja 500 g', 22.90, None, None),
    ('m2', 'Picanha bovina', 'Peça aprox. 1 kg', 89.90, 79.90, None),
    ('m1', 'Contrafilé em bife', 'Bandeja 500 g', 34.90, None, None),
    ('m2', 'Alcatra em bife', 'Bandeja 500 g', 32.50, None, None),
    ('m1', 'Carne de panela (acém)', 'Bandeja 1 kg', 36.90, 33.90, None),
    ('m2', 'Peito de frango', 'Bandeja 1 kg', 19.90, None, None),
    ('m1', 'Arroz branco tipo 1', 'Pacote 5 kg', 27.90, 24.90, None),
    ('m2', 'Feijão carioca', 'Pacote 1 kg', 8.99, None, None),
    ('m1', 'Café torrado e moído', 'Pacote 500 g', 18.90, None, None),
    ('m2', 'Açúcar refinado', 'Pacote 1 kg', 4.99, None, None),
    ('m1', 'Banana prata', 'Cacho aprox. 1 kg', 6.90, None, None),
    ('m2', 'Ovos brancos', 'Bandeja com 12', 11.90, 10.49, None),
    ('m1', 'Manteiga com sal', 'Pote 200 g', 12.90, None, None),
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
]
SINONIMOS = {'pao': ['pao'], 'paozinho': ['pao frances'], 'carne': ['carne', 'picanha', 'contrafile', 'alcatra', 'acem'],
             'remedio': ['dipirona', 'paracetamol'], 'cerveja': ['cerveja'], 'racao': ['racao'],
             'marmita': ['marmita'], 'almoco': ['marmita', 'sopa'], 'leite': ['leite']}
PAGAMENTOS = [('PIX', 'PIX'), ('Dinheiro na entrega', 'CASH'), ('Cartão na entrega', 'OFFLINE_CARD')]
STATUS = [('CONFIRMED', 'Pedido confirmado pela loja'), ('PREPARING', 'Pedido em preparo'),
          ('ON_THE_WAY', 'Pedido saiu para entrega'), ('DELIVERY_ARRIVED_AT_DESTINATION', 'Entregador chegou'),
          ('DELIVERED', 'Pedido entregue')]


def _n(s):
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def _uid(*partes):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'hackfood:' + ':'.join(map(str, partes))))


def _img(nome):
    texto = _n(nome).replace(' ', '+')[:40]
    return f'https://placehold.co/800x500/1f8f4e/ffffff/png?text={texto}'


def _item(i):
    loja, nome, desc, preco, promo, grupos = CATALOGO[i]
    d = {'itemId': _uid('item', i), 'merchantId': _uid('loja', loja), 'name': nome, 'description': desc,
         'unitDescription': desc, 'unitPrice': preco, 'imageUrl': _img(nome), 'available': True}
    if promo:
        d['promotionalUnitPrice'] = promo
    return d


def _loja(chave):
    nome, tipo, eta, taxa = LOJAS[chave]
    return {'merchantId': _uid('loja', chave), 'name': nome, 'merchantType': tipo, 'deliveryTime': eta,
            'deliveryFee': taxa, 'isOpen': True}


_ITEM_POR_ID = {_uid('item', i): i for i in range(len(CATALOGO))}
_LOJA_POR_ID = {_uid('loja', k): k for k in LOJAS}


class McpFake:
    def __init__(self, armazem=None, chave='mock'):
        self.armazem = armazem if armazem is not None else {}
        self.chave = chave
        self.chamadas = []  # (tool, args) na ordem, pros testes conferirem

    # --- estado ---

    def _st(self):
        st = self.armazem.get(self.chave)
        if not st:
            st = {'enderecos': [], 'carrinhos': {}, 'pedidos': {}, 'seq': 0}
        return copy.deepcopy(st)

    def _gravar(self, st):
        self.armazem[self.chave] = st

    def chamar(self, ferramenta, **args):
        args = {k: v for k, v in args.items() if v is not None}
        self.chamadas.append((ferramenta, args))
        fn = getattr(self, f't_{ferramenta}', None)
        if not fn:
            raise ErroMCP('TOOL_NOT_FOUND', f'tool {ferramenta} não existe')
        st = self._st()
        r = fn(st, **args)
        self._gravar(st)
        return r

    def chamadas_de(self, ferramenta):
        return [a for t, a in self.chamadas if t == ferramenta]

    # --- User ---

    def t_getUser(self, st):
        return {'user': {'name': 'Cliente Teste', 'email': 'cliente@test.ifood.com.br', 'phone': '+55 16 90000-0000'}}

    def t_listAddresses(self, st):
        return {'addresses': st['enderecos']}

    def t_createAddress(self, st, address=None, candidateId=None, complement=None, alias=None,
                        neighborhood=None, reference=None):
        if candidateId:
            cand = st.get('candidatos', {}).get(candidateId)
            if not cand:
                raise ErroMCP('MISSING_CANDIDATE_ID', 'candidateId desconhecido')
            end = {'addressId': _uid('end', self.chave, len(st['enderecos'])), 'alias': alias or 'Casa',
                   'streetName': cand['streetName'], 'streetNumber': cand['streetNumber'],
                   'neighborhood': neighborhood or cand['neighborhood'], 'city': cand['city'],
                   'complement': complement or '', 'isLastUsedAddress': True, 'isMostUsedAddress30d': True}
            for e in st['enderecos']:
                e['isLastUsedAddress'] = False
            st['enderecos'].append(end)
            return {'address': end, 'created': True}
        texto = (address or '').strip()
        if not any(ch.isdigit() for ch in texto) or len(texto) < 8:
            raise ErroMCP('PLACE_NOT_FOUND', 'endereço não encontrado', tentar_de_novo=True)
        rua, _, resto = texto.partition(',')
        numero = ''.join(ch for ch in resto if ch.isdigit())[:6] or '1'
        cands = {}
        for bairro in ('Centro', 'Jardim São Paulo'):
            cid = _uid('cand', texto, bairro)
            cands[cid] = {'candidateId': cid, 'streetName': rua.strip().title(), 'streetNumber': numero,
                          'neighborhood': bairro, 'city': 'São Carlos - SP',
                          'formattedAddress': f'{rua.strip().title()}, {numero} - {bairro}, São Carlos - SP'}
        st['candidatos'] = cands
        return {'match': 'MULTIPLE', 'candidates': list(cands.values())}

    # --- Offer Discovery ---

    def t_searchOffers(self, st, query='', userLocation=None, refinements=None, pageSize=10, nextPageToken=None):
        if not userLocation:
            raise ErroMCP('INVALID_LOCATION', 'userLocation obrigatório')
        refin = refinements or {}
        termos = _n(query).split()
        alvos = set()
        for t in termos:
            alvos.update(SINONIMOS.get(t, [t]))
        tipo = refin.get('merchantType')
        loja = refin.get('merchantId')
        teto = refin.get('maxItemPrice')
        achados = []
        for i, (lj, nome, desc, preco, promo, _g) in enumerate(CATALOGO):
            if tipo and LOJAS[lj][1] != tipo:
                continue
            if loja and _uid('loja', lj) != loja:
                continue
            if teto and (promo or preco) > float(teto):
                continue
            nn = _n(nome)
            if alvos and not any(a in nn for a in alvos):
                continue
            achados.append(i)
        tam = max(1, min(int(pageSize or 10), 25))
        ini = int(nextPageToken or 0)
        pagina = achados[ini:ini + tam]
        mais = ini + tam < len(achados)
        return {'results': [{'resultKind': 'ITEM', 'item': _item(i), 'merchant': _loja(CATALOGO[i][0])} for i in pagina],
                'hasMore': mais, 'nextPageToken': str(ini + tam) if mais else None}

    def t_browseOffers(self, st, userLocation=None, merchantType='GROCERIES', **_):
        return self.t_searchOffers(st, '', userLocation, {'merchantType': merchantType})

    def t_getMerchant(self, st, merchantId):
        if merchantId not in _LOJA_POR_ID:
            raise ErroMCP('MERCHANT_NOT_FOUND', 'loja não encontrada')
        return {'merchant': _loja(_LOJA_POR_ID[merchantId])}

    def t_getItem(self, st, itemId, merchantId=None):
        if itemId not in _ITEM_POR_ID:
            raise ErroMCP('ITEM_NOT_FOUND', 'item não encontrado')
        i = _ITEM_POR_ID[itemId]
        d = _item(i)
        grupos = []
        for gi, (nome, mn, mx, ops) in enumerate(CATALOGO[i][5] or []):
            grupos.append({'optionGroupId': _uid('grupo', i, gi), 'name': nome, 'min': mn, 'max': mx,
                           'options': [{'optionId': _uid('op', i, gi, oi), 'name': on, 'price': op}
                                       for oi, (on, op) in enumerate(ops)]})
        d['optionGroups'] = grupos
        return {'item': d}

    def t_getRecommendations(self, st, contentMode='RECENT_ORDERS', **_):
        if contentMode != 'RECENT_ORDERS':
            return {'items': []}
        peds = sorted(st['pedidos'].values(), key=lambda p: -p['seq'])
        return {'items': [{'orderId': p['orderId'], 'merchant': {'name': p['merchantName']},
                           'items': [{'name': it['name'], 'quantity': it['quantity']} for it in p['items']]}
                          for p in peds[:5]]}

    # --- Cart ---

    def _preco(self, i, opcoes):
        preco = CATALOGO[i][4] or CATALOGO[i][3]
        for gi, (_n2, _mn, _mx, ops) in enumerate(CATALOGO[i][5] or []):
            for oi, (_on, op) in enumerate(ops):
                if any(o.get('optionId') == _uid('op', i, gi, oi) for o in opcoes):
                    preco += op
        return round(preco, 2)

    def _linha(self, st, item):
        iid = item.get('itemId')
        if iid not in _ITEM_POR_ID:
            raise ErroMCP('ITEM_NOT_FOUND', 'item não encontrado')
        if 'options' not in item:
            raise ErroMCP('INVALID_PARAMS', 'options é obrigatório (pode ser [])')
        i = _ITEM_POR_ID[iid]
        grupos = CATALOGO[i][5] or []
        for gi, (nome, mn, _mx, ops) in enumerate(grupos):
            escolhidas = [o for o in item['options'] if o.get('optionId') in {_uid('op', i, gi, oi) for oi in range(len(ops))}]
            if len(escolhidas) < mn:
                raise ErroMCP('MISSING_REQUIRED_OPTION', f'grupo obrigatório {nome}')
        st['seq'] += 1
        qtd = int(item.get('quantity') or 1)
        unit = self._preco(i, item['options'])
        return {'cartItemId': _uid('cartitem', self.chave, st['seq']), 'itemId': iid, 'name': CATALOGO[i][1],
                'quantity': qtd, 'unitPrice': unit, 'totalPrice': round(unit * qtd, 2), 'options': item['options']}

    def _totais(self, car):
        sub = round(sum(it['totalPrice'] for it in car['items']), 2)
        taxa = LOJAS[_LOJA_POR_ID[car['merchantId']]][3]
        desc = car.get('voucher', {}).get('discountValue', 0) if car.get('voucher') else 0
        car['totals'] = {'subtotal': sub, 'deliveryFee': taxa, 'discount': desc,
                         'total': round(max(0, sub + taxa - desc), 2)}
        return car

    def _carrinho(self, st, cid):
        car = st['carrinhos'].get(cid)
        if not car:
            raise ErroMCP('CART_NOT_FOUND', 'carrinho não encontrado')
        return car

    def t_createCart(self, st, merchantId=None, addressId=None, items=None, orderId=None, **_):
        if orderId and (merchantId or addressId or items):
            raise ErroMCP('INVALID_PARAMS', 'orderId não combina com merchantId/addressId/items')
        if orderId:
            ped = st['pedidos'].get(orderId)
            if not ped:
                raise ErroMCP('ORDER_NOT_FOUND', 'pedido não encontrado')
            merchantId, addressId = ped['merchantId'], ped['addressId']
            items = [{'itemId': it['itemId'], 'quantity': it['quantity'], 'options': it.get('options', [])}
                     for it in ped['items']]
        if merchantId not in _LOJA_POR_ID:
            raise ErroMCP('MERCHANT_NOT_FOUND', 'loja não encontrada')
        if not addressId:
            raise ErroMCP('INVALID_PARAMS', 'addressId obrigatório')
        st['seq'] += 1
        cid = _uid('cart', self.chave, st['seq'])
        car = {'cartId': cid, 'merchantId': merchantId, 'merchant': {'name': LOJAS[_LOJA_POR_ID[merchantId]][0]},
               'addressId': addressId, 'items': [self._linha(st, it) for it in items or []]}
        st['carrinhos'][cid] = self._totais(car)
        return {'cart': car}

    def t_getCart(self, st, cartId):
        return {'cart': self._totais(self._carrinho(st, cartId))}

    def t_addItemToCart(self, st, cartId, itemId, quantity=1, options=None, customerNote=None, **_):
        car = self._carrinho(st, cartId)
        if options is None:
            raise ErroMCP('INVALID_PARAMS', 'options é obrigatório (pode ser [])')
        if _ITEM_POR_ID.get(itemId) is not None and _uid('loja', CATALOGO[_ITEM_POR_ID[itemId]][0]) != car['merchantId']:
            raise ErroMCP('ITEM_FROM_OTHER_MERCHANT', 'item de outra loja')
        linha = self._linha(st, {'itemId': itemId, 'quantity': quantity, 'options': options})
        car['items'].append(linha)
        self._totais(car)
        return {'cartItemId': linha['cartItemId'], 'cart': car}

    def t_updateCartItem(self, st, cartId, cartItemId, itemId, quantity=1, options=None, **_):
        car = self._carrinho(st, cartId)
        for it in car['items']:
            if it['cartItemId'] == cartItemId:
                it['quantity'] = int(quantity)
                it['totalPrice'] = round(it['unitPrice'] * it['quantity'], 2)
                self._totais(car)
                return {'cart': car}
        raise ErroMCP('CART_ITEM_NOT_FOUND', 'cartItemId não encontrado')

    def t_removeItemFromCart(self, st, cartId, cartItemId):
        car = self._carrinho(st, cartId)
        antes = len(car['items'])
        car['items'] = [it for it in car['items'] if it['cartItemId'] != cartItemId]
        if len(car['items']) == antes:
            raise ErroMCP('CART_ITEM_NOT_FOUND', 'cartItemId não encontrado')
        self._totais(car)
        return {'cart': car}

    def t_getCartDeliveryMethods(self, st, cartId):
        car = self._carrinho(st, cartId)
        car['deliveryChecked'] = True
        eta = LOJAS[_LOJA_POR_ID[car['merchantId']]][2]
        taxa = LOJAS[_LOJA_POR_ID[car['merchantId']]][3]
        return {'deliveryMethods': [
            {'deliveryMethodId': _uid('ent', 'agora', car['merchantId']), 'name': 'Entregar agora', 'mode': 'DELIVERY',
             'deliveryTime': eta, 'fee': taxa},
            {'deliveryMethodId': _uid('ent', 'agendada', car['merchantId']), 'name': 'Agendar', 'mode': 'SCHEDULED',
             'fee': taxa, 'timeSlots': [{'timeSlotId': _uid('slot', h), 'label': f'Hoje, {h}h-{h + 1}h'}
                                        for h in (18, 19, 20)]}]}

    def t_setCartDelivery(self, st, cartId, deliveryMethodId, selectedTimeSlotId=None):
        car = self._carrinho(st, cartId)
        if not car.get('deliveryChecked'):
            raise ErroMCP('DELIVERY_METHODS_NOT_LOADED', 'chame getCartDeliveryMethods antes')
        car['delivery'] = {'deliveryMethodId': deliveryMethodId, 'timeSlotId': selectedTimeSlotId}
        return {'cart': car}

    def t_listPaymentMethods(self, st, merchantId):
        return {'paymentMethods': [{'paymentMethodId': _uid('pag', tipo, merchantId), 'name': nome, 'type': tipo}
                                   for nome, tipo in PAGAMENTOS]}

    def t_setCartPayment(self, st, cartId, paymentMethodId, cardTokenId=None):
        car = self._carrinho(st, cartId)
        validos = {_uid('pag', tipo, car['merchantId']): tipo for _, tipo in PAGAMENTOS}
        if paymentMethodId not in validos:
            raise ErroMCP('INVALID_PAYMENT_METHOD', 'paymentMethodId inválido (é UUID, não "PIX")')
        car['payment'] = {'paymentMethodId': paymentMethodId, 'type': validos[paymentMethodId]}
        return {'cart': car}

    def t_listVouchers(self, st, cartId):
        car = self._totais(self._carrinho(st, cartId))
        if car['totals']['subtotal'] < 30:
            return {'vouchers': []}
        return {'vouchers': [{'code': 'BEMVINDO5', 'campaignId': _uid('camp', 'bemvindo'),
                              'description': 'R$ 5 de desconto', 'effect': 'FIXED', 'discountValue': 5.0}]}

    def t_setVoucher(self, st, cartId, code, campaignId):
        car = self._carrinho(st, cartId)
        if code != 'BEMVINDO5' or campaignId != _uid('camp', 'bemvindo'):
            raise ErroMCP('INVALID_VOUCHER', 'cupom inválido')
        car['voucher'] = {'code': code, 'campaignId': campaignId, 'discountValue': 5.0}
        self._totais(car)
        return {'cart': car}

    def t_removeVoucher(self, st, cartId):
        car = self._carrinho(st, cartId)
        car.pop('voucher', None)
        self._totais(car)
        return {'cart': car}

    def t_submitOrder(self, st, cartId, userConsent=False, document=None):
        car = self._carrinho(st, cartId)
        if userConsent is not True:
            raise ErroMCP('USER_CONSENT_REQUIRED', 'userConsent precisa ser true')
        if not car['items']:
            raise ErroMCP('EMPTY_CART', 'carrinho vazio')
        if not car.get('delivery'):
            raise ErroMCP('DELIVERY_NOT_SET', 'chame setCartDelivery antes')
        if not car.get('payment'):
            raise ErroMCP('PAYMENT_NOT_SET', 'chame setCartPayment antes')
        if car.get('submitted'):
            raise ErroMCP('CART_ALREADY_SUBMITTED', 'carrinho já virou pedido')
        car['submitted'] = True
        st['seq'] += 1
        oid = _uid('pedido', self.chave, st['seq'])
        st['pedidos'][oid] = {'orderId': oid, 'seq': st['seq'], 'merchantId': car['merchantId'],
                              'merchantName': car['merchant']['name'], 'addressId': car['addressId'],
                              'items': car['items'], 'totals': car['totals'], 'consultas': 0}
        pedido = {'orderId': oid, 'shortId': str(4800 + st['seq'])}
        if car['payment']['type'] == 'PIX':
            pedido['pix'] = {'copyPaste': '00020126580014br.gov.bcb.pix0136' + oid.replace('-', '')[:32] + '5204000053039865802BR'}
        return {'order': pedido}

    # --- Order Tracking ---

    def t_trackOrder(self, st, orderId):
        ped = st['pedidos'].get(orderId)
        if not ped:
            return {'errorType': 'NOT_FOUND', 'code': 'ORDER_NOT_FOUND', 'message': 'pedido não encontrado',
                    'retryable': False} if False else self._erro_rastreio()
        i = min(ped['consultas'], len(STATUS) - 1)
        ped['consultas'] += 1
        cod, desc = STATUS[i]
        fim = cod == 'DELIVERED'
        return {'status': {'code': cod, 'description': desc},
                'statusHistory': [{'code': c, 'description': d} for c, d in STATUS[:i + 1]][-5:],
                'agentHints': {'retryMessage': None if fim else 'Check again in 20 seconds',
                               'pollingStop': fim, 'stopMessage': 'Pedido entregue' if fim else None}}

    def _erro_rastreio(self):
        raise ErroMCP('ORDER_NOT_FOUND', 'pedido não encontrado')

    def t_getOrder(self, st, orderId):
        ped = st['pedidos'].get(orderId)
        if not ped:
            raise ErroMCP('ORDER_NOT_FOUND', 'pedido não encontrado')
        return {'order': {'orderId': orderId, 'merchant': {'name': ped['merchantName']}, 'items': ped['items'],
                          'totals': ped['totals']}}
