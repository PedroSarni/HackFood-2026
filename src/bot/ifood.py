"""Tradutor entre o MCP do iFood e o fluxo: chama as tools e devolve dicionários nossos.

O fluxo nunca vê o formato cru do iFood. Formatos seguem a referência do portal (páginas da
doc, não o llms.txt, que está desatualizado); o que a doc deixa em aberto está marcado com
INCERTO e tem plano B no código.

Formatos nossos (o fluxo depende só destes campos):
  endereço  {id, apelido, texto, lat, lng, bairro, ultimo, mais_usado}
  oferta    {item_id, loja_id, nome, descricao, preco, preco_antigo, imagem, loja, tempo, nota,
             distancia, disponivel}
  item      {item_id, loja_id, nome, descricao, preco, grupos: [{id, nome, min, max, opcoes: [{id, nome, preco}]}]}
  carrinho  {id, loja_id, loja, itens: [{cart_item_id, item_id, nome, qtd, preco_total}], subtotal,
             taxa_entrega, desconto, total}
  entrega   {id, nome, tempo, preco, agendada}
  pagamento {id, nome, tipo, cartao}
  cupom     {codigo, campanha, descricao, valor}
  status    {codigo, descricao, parar, proxima}
"""
import os

from src.shared.ifood_mcp import ErroMCP

TIPO_LOJA = {'MERCADO': 'GROCERIES', 'RESTAURANTE': 'RESTAURANT', 'FARMACIA': 'DRUGSTORE',
             'BEBIDAS': 'LIQUORSTORE', 'PET': 'PETSTORE', 'LOJA': 'SHOPPING'}
TAMANHO_PAGINA = 25  # máximo do iFood; a lista inteira fica guardada pro "Mais opções"
# pagamento que um bot consegue usar: cartão exige cardTokenId e o listPaymentMethods sempre
# devolve null (não há API de tokenização), então cartão só entra se vier com token
PAGAVEIS = ('PIX', 'MEAL_VOUCHER', 'FOOD_VOUCHER')
NOME_PAGAMENTO = {'PIX': 'PIX', 'MEAL_VOUCHER': 'Vale-refeição', 'FOOD_VOUCHER': 'Vale-alimentação',
                  'CREDIT_CARD': 'Cartão de crédito', 'DEBIT_CARD': 'Cartão de débito'}

# INCERTO (doc, seção 3.4): como as opções do getItem viram options[] do carrinho.
#  A: options[].optionId = optionGroupId e customizations[].customizationId = optionId
#  B: options[].optionId = optionId, customizations = []
# Começa pelo A (o mais coerente com a doc); se o iFood recusar, tenta o B e lembra qual valeu.
_MODO_OPCOES = [os.environ.get('IFOOD_OPCOES_MODO') or 'A']


class PrecisaLogin(Exception):
    """A pessoa não tem token (nunca entrou, saiu, ou o refresh venceu)."""


def _campo(d, *nomes, padrao=None):
    """Primeiro campo existente (aceita caminho com ponto: 'merchant.merchantName')."""
    if not isinstance(d, dict):
        return padrao
    for n in nomes:
        atual = d
        for parte in n.split('.'):
            atual = atual.get(parte) if isinstance(atual, dict) else None
            if atual is None:
                break
        if atual not in (None, ''):
            return atual
    return padrao


def _num(v):
    try:
        return round(float(v), 2) if v is not None else None
    except (TypeError, ValueError):
        return None


def _lista(d, *nomes):
    v = _campo(d, *nomes)
    return v if isinstance(v, list) else []


def _minutos(m):
    """{'min': 25, 'max': 35} -> '25-35 min'"""
    if not isinstance(m, dict):
        return None
    lo, hi = m.get('min'), m.get('max')
    if lo and hi:
        return f'{lo}-{hi} min'
    return f'{lo or hi} min' if (lo or hi) else None


def opcoes_para_carrinho(opcoes, modo=None):
    """Nossas opções escolhidas -> options[] do Cart (sempre lista, mesmo vazia)."""
    modo = modo or _MODO_OPCOES[0]
    if not opcoes:
        return []
    if modo == 'B':
        return [{'optionId': o['opcao_id'], 'quantity': 1, 'customizations': []} for o in opcoes]
    grupos = {}
    for o in opcoes:
        g = grupos.setdefault(o['grupo_id'], {'optionId': o['grupo_id'], 'quantity': 1, 'customizations': []})
        g['customizations'].append({'customizationId': o['opcao_id'], 'quantity': 1})
    return list(grupos.values())


UFS_BR = {'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE',
          'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'}


def _sem_envelope(d):
    """O MCP real responde `{"success": true, "data": {...}, "agentHints": {...}}` (visto em
    17/10 no createAddress: os candidates vêm DENTRO de data). Achata pra o resto do código ler
    os campos direto, aceite a resposta venha embrulhada ou não."""
    if not isinstance(d, dict):
        return d
    dados = d.get('data')
    resto = {k: v for k, v in d.items() if k != 'data'}
    if isinstance(dados, dict):
        return {**resto, **dados}
    if isinstance(dados, list):
        return {**resto, 'results': dados}
    return d


class Ifood:
    def __init__(self, chamar):
        self._chamar_cru = chamar   # função chamar(tool, **args) -> dict (ClienteMCP ou McpFake)

    def _chamar(self, ferramenta, **args):
        return _sem_envelope(self._chamar_cru(ferramenta, **args))

    # --- usuário e endereço -------------------------------------------------------------

    def usuario(self):
        d = self._chamar('getUser')
        return {'nome': _campo(d, 'fullName', padrao=''), 'email': _campo(d, 'email'),
                'telefone': _campo(d, 'phone'), 'cpf': _campo(d, 'taxPayerIdentificationNumber')}

    @staticmethod
    def _endereco(a):
        coords = _campo(a, 'coordinates', padrao={}) or {}
        texto = _campo(a, 'formattedAddress', padrao='')
        if not texto:
            loc = _campo(a, 'location', padrao={}) or {}
            texto = ', '.join(str(x) for x in (loc.get('street'), loc.get('number'), loc.get('neighborhood'),
                                               loc.get('city')) if x)
        return {'id': _campo(a, 'addressId'), 'apelido': _campo(a, 'alias') or 'Endereço',
                'texto': texto, 'lat': coords.get('latitude'), 'lng': coords.get('longitude'),
                'bairro': _campo(a, 'location.neighborhood'),
                'ultimo': bool(_campo(a, 'isLastUsedAddress', padrao=False)),
                'mais_usado': bool(_campo(a, 'isMostUsedAddress30d', padrao=False))}

    def enderecos(self):
        d = self._chamar('listAddresses')
        return [self._endereco(a) for a in _lista(d, 'results') if _campo(a, 'addressId')]

    def geocodificar(self, texto):
        """Passo 1 do createAddress (sem efeito colateral): texto livre -> candidatos."""
        d = self._chamar('createAddress', address=texto)
        if _campo(d, 'addressId'):  # single-shot já criou
            return {'criado': self._endereco(d), 'candidatos': []}
        cands = []
        for c in _lista(d, 'candidates'):
            loc = _campo(c, 'location', padrao={}) or {}
            rua = ' '.join(str(x) for x in (loc.get('street'), loc.get('number')) if x)
            coords = _campo(c, 'coordinates', padrao={}) or {}
            cands.append({'id': _campo(c, 'candidateId'), 'texto': _campo(c, 'formattedAddress', padrao=rua),
                          'titulo': rua or _campo(c, 'formattedAddress', padrao='')[:24],
                          'bairro': loc.get('neighborhood') or '', 'endereco': texto, 'uf': loc.get('state') or '',
                          'lat': coords.get('latitude'), 'lng': coords.get('longitude')})
        # CEP solto confunde o geocode do iFood (01310-100 já deu Canadá, 20040-002 Amsterdã): fora do Brasil não entrega
        return {'criado': None, 'candidatos': [c for c in cands if c['id'] and c['uf'] in UFS_BR]}

    def criar_endereco(self, candidato, complemento='', apelido='Casa', bairro=None):
        """Passo 2: confirma o candidato. A doc pede o mesmo `address` junto do candidateId;
        bairro vai no campo dele (nunca no complemento)."""
        d = self._chamar('createAddress', address=candidato.get('endereco'), candidateId=candidato['id'],
                         complement=complemento or None, alias=apelido,
                         neighborhood=bairro or candidato.get('bairro') or None)
        end = self._endereco(d)
        end['texto'] = end['texto'] or candidato.get('texto', '')
        return end

    # --- busca --------------------------------------------------------------------------

    @staticmethod
    def _local(endereco):
        return {'latitude': endereco['lat'], 'longitude': endereco['lng']}

    @staticmethod
    def _oferta(r):
        loja = _campo(r, 'merchant', padrao={}) or {}
        entrega = _campo(loja, 'deliveryMethod', padrao={}) or {}
        preco = _num(_campo(r, 'promotionalUnitPrice'))
        cheio = _num(_campo(r, 'unitPrice'))
        if preco is None:
            preco, cheio = cheio, None
        elif cheio is not None and cheio <= preco:
            cheio = None
        return {'item_id': _campo(r, 'itemId'), 'loja_id': _campo(loja, 'merchantId'),
                'nome': _campo(r, 'itemName', padrao='Produto'), 'descricao': '',
                'preco': preco, 'preco_antigo': cheio, 'imagem': _campo(r, 'itemImageUrl'),
                'loja': _campo(loja, 'merchantName', padrao=''), 'tempo': _minutos(_campo(entrega, 'estimatedMinutes')),
                'nota': _num(_campo(loja, 'reviewRating')), 'distancia': _num(_campo(loja, 'straightLineDistanceKm')),
                'disponivel': _campo(loja, 'isOpen', padrao=True) is not False}

    def buscar(self, termo, endereco, tipo_loja, loja_id=None, pagina=None):
        """searchOffers só com o termo descritivo; vertical no merchantType e o resto em
        refinements (regra da doc). Devolve (ofertas, token_da_proxima_pagina)."""
        refin = {'onlyOpen': True, 'requiredDeliveryMethod': 'DELIVERY'}
        if loja_id:
            refin['merchantId'] = loja_id
        d = self._chamar('searchOffers', query=termo, resultKind='ITEM', userLocation=self._local(endereco),
                         merchantType=TIPO_LOJA.get(tipo_loja, 'GROCERIES'), refinements=refin,
                         pageSize=TAMANHO_PAGINA, nextPageToken=pagina)
        ofertas = [self._oferta(r) for r in _lista(d, 'results')]
        ofertas = [o for o in ofertas if o['item_id'] and o['loja_id'] and o['preco'] is not None]
        prox = _campo(d, 'nextPageToken') if _campo(d, 'hasMore', padrao=False) else None
        return ofertas, prox

    def item(self, item_id, loja_id, endereco):
        d = self._chamar('getItem', itemId=item_id, merchantId=loja_id, userLocation=self._local(endereco))
        grupos = []
        for g in _lista(d, 'optionGroups'):
            ops = [{'id': _campo(o, 'optionId'), 'nome': _campo(o, 'name', padrao='Opção'),
                    'preco': _num(_campo(o, 'additionalPrice'))} for o in _lista(g, 'options')]
            grupos.append({'id': _campo(g, 'optionGroupId'), 'nome': _campo(g, 'name', padrao=''),
                           'min': int(_campo(g, 'minSelections', padrao=0) or 0),
                           'max': int(_campo(g, 'maxSelections', padrao=1) or 1),
                           'opcoes': [o for o in ops if o['id']]})
        return {'item_id': item_id, 'loja_id': loja_id, 'nome': _campo(d, 'itemName'),
                'descricao': _campo(d, 'itemDescription', padrao=''), 'imagem': _campo(d, 'itemImageUrl'),
                'preco': _num(_campo(d, 'promotionalUnitPrice', 'unitPrice')), 'grupos': grupos}

    # --- carrinho -----------------------------------------------------------------------

    @staticmethod
    def _linha_api(linha, modo=None):
        d = {'itemId': linha['item_id'], 'quantity': int(linha['qtd']),
             'options': opcoes_para_carrinho(linha.get('opcoes'), modo)}
        if linha.get('obs'):
            d['customerNote'] = linha['obs'][:140]
        return d

    @staticmethod
    def _carrinho(d):
        itens = []
        for it in _lista(d, 'items'):
            qtd = int(_campo(it, 'quantity', padrao=1) or 1)
            unit = _num(_campo(it, 'unitPrice'))
            itens.append({'cart_item_id': _campo(it, 'cartItemId'), 'item_id': _campo(it, 'itemId'),
                          'nome': _campo(it, 'name', padrao='Item'), 'qtd': qtd,
                          'preco_total': round(unit * qtd, 2) if unit is not None else None})
        s = _campo(d, 'summary', padrao={}) or {}
        desconto = (_num(s.get('voucherTotalAmount')) or 0) + (_num(s.get('benefitsTotalAmount')) or 0)
        return {'id': _campo(d, 'cartId'), 'loja_id': _campo(d, 'merchant.merchantId'),
                'loja': _campo(d, 'merchant.merchantName'), 'itens': itens,
                'subtotal': _num(s.get('subtotalAmount')), 'taxa_entrega': _num(s.get('deliveryFeeAmount')),
                'taxas': _num(s.get('feeTotalAmount')), 'desconto': round(desconto, 2) or None,
                'total': _num(s.get('totalAmount')), 'minimo': _num(_campo(d, 'merchant.orderMinimumPrice'))}

    def _com_opcoes(self, fazer, linhas):
        """Roda `fazer(modo)`; se o iFood recusar as opções no modo atual, tenta o outro."""
        if not any(lin.get('opcoes') for lin in linhas):
            return fazer(None)
        modo = _MODO_OPCOES[0]
        try:
            return fazer(modo)
        except ErroMCP as e:
            if str(e.codigo) in ('MERCHANT_CLOSED', 'CART_NOT_FOUND', 'ITEM_NOT_AVAILABLE', 'CART_EMPTY',
                                 'TIMEOUT', 'REDE'):
                raise
            outro = 'B' if modo == 'A' else 'A'
            print(f'opções no modo {modo} recusadas ({e.codigo}); tentando modo {outro}')
            r = fazer(outro)
            _MODO_OPCOES[0] = outro
            return r

    def criar_carrinho(self, loja_id, endereco_id, linhas):
        d = self._com_opcoes(lambda modo: self._chamar(
            'createCart', merchantId=loja_id, addressId=endereco_id,
            items=[self._linha_api(lin, modo) for lin in linhas]), linhas)
        car = self._carrinho(d)
        car['loja_id'] = car['loja_id'] or loja_id
        return car

    def repetir_pedido(self, pedido_id):
        d = self._chamar('createCart', orderId=pedido_id)
        car = self._carrinho(d)
        if car['id']:  # doc: depois do reorder, sempre conferir com getCart (preços atuais)
            car = self.carrinho(car['id'])
        return car

    def adicionar(self, carrinho_id, linha):
        d = self._com_opcoes(lambda modo: self._chamar(
            'addItemToCart', cartId=carrinho_id, **self._linha_api(linha, modo)), [linha])
        return self._carrinho(d)

    def remover(self, carrinho_id, cart_item_id):
        d = self._chamar('removeItemFromCart', cartId=carrinho_id, cartItemId=cart_item_id)
        if _campo(d, 'agentHints.cartDeletedAfterLastItemRemoved'):
            return None
        return self._carrinho(d)

    def carrinho(self, carrinho_id):
        return self._carrinho(self._chamar('getCart', cartId=carrinho_id))

    def entregas(self, carrinho_id):
        """Só entrega imediata: o agendamento exige selectedTimeSlotId, mas os timeslots da API
        não têm ID (doc, ambiguidade 18). Retirada fica de fora (público não sai de casa)."""
        d = self._chamar('getCartDeliveryMethods', cartId=carrinho_id)
        saida = []
        for m in _lista(d, 'deliveryMethods'):
            mid = _campo(m, 'deliveryMethodId')
            if not mid or _campo(m, 'deliveryMethodMode') != 'DELIVERY' or _campo(m, 'timeslots'):
                continue
            saida.append({'id': mid, 'nome': _campo(m, 'deliveryMethodName', padrao='Entrega'),
                          'tempo': _minutos(_campo(m, 'estimatedMinutes')), 'preco': _num(_campo(m, 'fee')),
                          'agendada': False, 'padrao': mid == 'DEFAULT'})
        saida.sort(key=lambda e: (not e['padrao'], e['preco'] if e['preco'] is not None else 99))
        return saida

    def definir_entrega(self, carrinho_id, entrega_id):
        return self._carrinho(self._chamar('setCartDelivery', cartId=carrinho_id, deliveryMethodId=entrega_id))

    def pagamentos(self, loja_id):
        d = self._chamar('listPaymentMethods', merchantId=loja_id)
        saida = []
        for p in _lista(d, 'paymentMethods'):
            pid, tipo = _campo(p, 'paymentMethodId'), str(_campo(p, 'kind', padrao='')).upper()
            if not pid:
                continue
            token = _campo(p, 'cardTokenId')
            if tipo not in PAGAVEIS and not token:
                continue
            nome = _campo(p, 'displayName') or NOME_PAGAMENTO.get(tipo, tipo.title())
            if token and _campo(p, 'brand'):
                nome = f'{nome} {_campo(p, "brand")}'
            saida.append({'id': pid, 'nome': nome, 'tipo': tipo, 'cartao': token})
        saida.sort(key=lambda f: PAGAVEIS.index(f['tipo']) if f['tipo'] in PAGAVEIS else 9)
        return saida

    def definir_pagamento(self, carrinho_id, forma):
        return self._carrinho(self._chamar('setCartPayment', cartId=carrinho_id, paymentMethodId=forma['id'],
                                           cardTokenId=forma.get('cartao')))

    def cupons(self, carrinho_id, subtotal=None):
        d = self._chamar('listVouchers', cartId=carrinho_id)
        saida = []
        for v in _lista(d, 'vouchers'):
            cod, camp = _campo(v, 'code'), _campo(v, 'campaignId')
            if not (cod and camp) or _campo(v, 'available', padrao=True) is False:
                continue
            efeito, valor = _campo(v, 'effectType'), _num(_campo(v, 'effectValue')) or 0
            if efeito == 'PERCENTAGE':
                valor = round((subtotal or 0) * valor / 100, 2)
                teto = _num(_campo(v, 'maxDiscountValue'))
                if teto is not None:
                    valor = min(valor, teto)
            saida.append({'codigo': cod, 'campanha': camp, 'descricao': _campo(v, 'description', padrao=''),
                          'valor': valor})
        return saida

    def aplicar_cupom(self, carrinho_id, cupom):
        return self._carrinho(self._chamar('setVoucher', cartId=carrinho_id, code=cupom['codigo'],
                                           campaignId=cupom['campanha']))

    def fechar(self, carrinho_id, cpf=None):
        """submitOrder com userConsent=True: só é chamado depois do toque em Confirmar."""
        doc = f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}' if cpf and len(cpf) == 11 else cpf
        d = self._chamar('submitOrder', cartId=carrinho_id, userConsent=True, document=doc or None)
        return {'id': _campo(d, 'orderId')}

    # --- depois do pedido ---------------------------------------------------------------

    def rastrear(self, pedido_id):
        d = self._chamar('trackOrder', orderId=pedido_id)
        st = _campo(d, 'status', padrao={}) or {}
        dicas = _campo(d, 'agentHints', padrao={}) or {}
        return {'codigo': _campo(st, 'code'), 'descricao': _campo(st, 'description', padrao=''),
                'parar': dicas.get('pollingStop') is True, 'proxima': dicas.get('retryMessage')}

    def pedido(self, pedido_id):
        """getOrder: shortCode e código de entrega (o que a pessoa fala pro entregador)."""
        d = self._chamar('getOrder', orderId=pedido_id)
        return {'codigo': _campo(d, 'shortCode'), 'codigo_entrega': _campo(d, 'delivery.verificationCode'),
                'loja': _campo(d, 'merchant'), 'itens': _lista(d, 'items'), 'pagamento': _campo(d, 'payment')}

    def pedidos_recentes(self, endereco):
        """Itens pedidos recentemente, agrupados pelo pedido de origem (lastOrderId)."""
        d = self._chamar('getRecommendations', contentMode='RECENT_ORDERS', resultKind='ITEM',
                         userLocation=self._local(endereco), pageSize=TAMANHO_PAGINA)
        pedidos = {}
        for r in _lista(d, 'results'):
            oid = _campo(r, 'lastOrderId')
            if not oid:
                continue
            p = pedidos.setdefault(oid, {'id': oid, 'loja': _campo(r, 'merchant.merchantName', padrao='Pedido'),
                                         'nomes': [], 'quando': _campo(r, 'lastOrderedAt', padrao='')})
            p['nomes'].append(_campo(r, 'itemName', padrao=''))
        saida = sorted(pedidos.values(), key=lambda p: p['quando'], reverse=True)
        return [{'id': p['id'], 'loja': p['loja'], 'resumo': ', '.join(n for n in p['nomes'] if n)[:200]}
                for p in saida[:9]]
