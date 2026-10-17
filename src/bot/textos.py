"""Tudo que o bot fala, num lugar só.

Regra de escrita (o público é quem tem dificuldade com o celular):
- frase curta, palavra do dia a dia, nada de "carrinho de compras", "checkout", "método";
- um emoji no começo da linha serve de âncora visual; não enfeitar além disso;
- toda mensagem termina dizendo o que fazer ("toque em...", "pode escrever ou mandar áudio");
- botão com até 20 caracteres (limite da Meta), verbo ou resposta direta.
"""


def reais(v):
    if v is None:
        return ''
    s = f'{float(v):,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')


# --- botões fixos (id, título) --------------------------------------------------------

B_PEDIR = ('pedir', '🛒 Fazer pedido')
B_REPETIR = ('repetir', '🔁 Pedir de novo')
B_MEU_PEDIDO = ('meu_pedido', '📦 Meu pedido')
B_INICIO = ('inicio', '🏠 Início')
B_OUTRA = ('outra', '🔎 Procurar outra')
B_FINALIZAR = ('fim', '✅ Finalizar pedido')
B_MAIS_COISAS = ('add', '➕ Quero mais coisas')
B_TIRAR = ('tirar', '🗑️ Tirar um item')
B_TENTAR = ('tentar', '🔁 Tentar de novo')
B_SIM = 'Sim'
B_NAO = 'Não'

MENU = [B_PEDIR, B_REPETIR, B_MEU_PEDIDO]

# --- boas-vindas e login -----------------------------------------------------------------


def boas_vindas(nome):
    oi = f'Olá, {nome}! 👋' if nome else 'Olá! 👋'
    return (f'{oi}\nEu faço suas compras do iFood aqui pelo WhatsApp: mercado, farmácia, '
            'restaurante...\n\nÉ só me dizer o que você precisa, escrevendo ou mandando um áudio 🎤')


LOGIN = ('🔐 Primeiro, preciso que você entre na sua conta do iFood.\n\n'
         'Toque no botão abaixo. Se você ainda não tem conta, dá pra criar lá mesmo, de graça.')
LOGIN_BOTAO = 'Entrar no iFood'
LOGIN_RODAPE = 'Depois de entrar, volte pra cá'
LOGIN_DE_NOVO = ('🔐 Sua entrada no iFood venceu. Toque no botão pra entrar de novo, '
                 'é rapidinho.')
LOGIN_AINDA = ('Ainda estou esperando você entrar no iFood. 🙂\n'
               'Toque em *Entrar no iFood* aqui embaixo.')


def logou(nome):
    oi = f'Pronto, {nome}! ✅' if nome else 'Pronto! ✅'
    return f'{oi} Você entrou no iFood.'


PERGUNTA_PEDIDO = ('O que você quer pedir? 😊\n\n'
                   'Pode escrever do seu jeito ou mandar um áudio 🎤\n'
                   'Exemplo: _pão, leite e café_')

AJUDA = ('Eu faço pedidos no iFood pra você. 🛒\n\n'
         '1️⃣ Me diga o que quer (escrevendo ou por áudio)\n'
         '2️⃣ Eu mostro as opções com foto\n'
         '3️⃣ Você toca em *Quero esse*\n'
         '4️⃣ No final eu mostro o resumo e você confirma\n\n'
         'Nada é comprado sem você confirmar.')

FORA_DO_ESCOPO = ('Eu só sei fazer pedidos no iFood 🙂\n'
                  'Me diga o que você quer comprar, ou toque num botão.')

NAO_ENTENDI = ('Desculpe, não entendi. 🙏\n'
               'Pode escrever de outro jeito, mandar um áudio, ou tocar num botão.')

AUDIO_RUIM = ('Não consegui ouvir seu áudio direito. 🙉\n'
              'Pode mandar de novo, ou escrever?')

ERRO = ('Ops, deu um probleminha aqui do meu lado. 😕\n'
        'Toque em *Tentar de novo*.')
ERRO_SEM_BOTAO = ('Ops, deu um probleminha aqui do meu lado. 😕\n'
                  'Mande sua mensagem de novo, por favor.')

BOTAO_VELHO = 'Esse botão é de uma conversa antiga. Vamos continuar daqui: 👇'

DE_NADA = 'Por nada! 😊 Quando precisar, é só chamar.'

# --- endereço ---------------------------------------------------------------------------

PEDIR_ENDERECO = ('🏠 Pra onde eu mando suas compras?\n\n'
                  'Escreva o endereço com rua, número e cidade.\n'
                  'Exemplo: _Rua das Flores, 120, São Carlos_')
ENDERECO_NAO_ACHEI = ('Não achei esse endereço. 😕\n'
                      'Confira e escreva de novo, com rua, número e cidade.')
ESCOLHA_ENDERECO = 'Qual destes é o seu endereço? Toque no certo 👇'
PEDIR_COMPLEMENTO = ('Tem apartamento, bloco ou casa nos fundos?\n'
                     'Escreva aqui. Se não tiver, toque em *Não tem*.')
B_SEM_COMPLEMENTO = ('compl_nao', 'Não tem')
QUAL_ENDERECO = 'Pra qual endereço eu mando? Toque no certo 👇'
B_ENDERECO_NOVO = ('end_novo', '📍 Outro endereço')


def endereco_salvo(apelido, texto):
    return f'✅ Endereço salvo: *{apelido}*\n{texto}'


def entregando_em(apelido, texto):
    return f'🏠 Entregando em: *{apelido}*' + (f' ({texto})' if texto else '')


# --- busca e escolha --------------------------------------------------------------------


def procurando(termo):
    return f'🔎 Procurando *{termo}*...'


def lista_de_compras(termos):
    linhas = '\n'.join(f'{i}. {t}' for i, t in enumerate(termos, 1))
    return f'📝 Anotei sua lista:\n{linhas}\n\nVou te mostrar um de cada vez. Começando por *{termos[0]}*:'


def card(oferta):
    linhas = [f'*{oferta["nome"]}*']
    if oferta.get('descricao'):
        linhas.append(oferta['descricao'])
    preco = reais(oferta.get('preco'))
    if oferta.get('preco_antigo'):
        preco += f'  ~{reais(oferta["preco_antigo"])}~'
    linhas.append(f'💰 {preco}')
    if oferta.get('loja'):
        linhas.append(f'🏪 {oferta["loja"]}')
    extras = []
    if oferta.get('nota'):
        extras.append(f'⭐ {str(oferta["nota"]).replace(".", ",")}')
    if oferta.get('tempo'):
        extras.append(f'🛵 {oferta["tempo"]}')
    if extras:
        linhas.append(' · '.join(extras))
    return '\n'.join(linhas)


B_QUERO = 'Quero esse'


def rodape_opcoes(tem_mais):
    if tem_mais:
        return 'Gostou de algum? Toque em *Quero esse* 👆\nSe não, peça mais opções:'
    return 'Gostou de algum? Toque em *Quero esse* 👆'


B_MAIS = '➕ Mais opções'
FIM_DAS_OPCOES = 'Essas eram todas as opções que achei. 🙂\nQuer procurar outra coisa?'


def nao_achei(termo, loja=None):
    if loja:
        return f'Não achei *{termo}* no {loja}. 😕'
    return f'Não achei *{termo}* perto de você. 😕\nTente escrever de outro jeito.'


B_PULAR = ('pular', '⏭️ Pular esse item')
B_ESCREVER = ('outra', '✏️ Escrever de novo')


def quantos(nome):
    # "unidades" concorda sempre com "Quantas"; "de <nome>" serve pra qualquer produto, sem
    # risco de gênero errado ("Quantos Picanha" ficava torto)
    return f'Quantas unidades de *{nome}* você quer?\nToque no número, ou escreva.'


def escolha_opcao(grupo, n, total):
    if total > 1:
        return f'Escolha o {n}º de {total}: *{grupo}* 👇'
    return f'Escolha: *{grupo}* 👇'


def colocado(qtd, nome):
    return f'✅ Coloquei *{qtd}x {nome}* no seu pedido.'


def proximo_da_lista(termo):
    return f'Agora vamos procurar *{termo}*: 👇'


def mais_alguma(total):
    return f'🧺 Seu pedido até agora: *{reais(total)}*\n\nQuer mais alguma coisa?'


# --- fechamento -------------------------------------------------------------------------

PEDIR_CPF = ('🧾 Pra nota fiscal, me mande seu *CPF* (só os números).\n'
             'Se não quiser, toque em *Sem CPF*.')
B_SEM_CPF = ('cpf_nao', 'Sem CPF')
CPF_INVALIDO = 'Esse CPF não parece certo. 🤔 Confira os números e mande de novo.'
QUAL_PAGAMENTO = 'Como você quer pagar? 💳'
QUAL_ENTREGA = 'Quando você quer receber? 🛵'
LOJA_FECHADA = 'Essa loja não está entregando agora. 😕'


def resumo(carrinho, endereco, entrega, pagamento, cupom=None):
    linhas = ['🧾 *Confira seu pedido:*', '']
    for it in carrinho['itens']:
        linhas.append(f'• {it["qtd"]}x {it["nome"]} — {reais(it.get("preco_total"))}')
    linhas.append('')
    taxa_valor = carrinho.get('taxa_entrega')
    if taxa_valor is None and entrega:
        taxa_valor = entrega.get('preco')
    if taxa_valor is not None or entrega:
        taxa = 'grátis' if not taxa_valor else reais(taxa_valor)
        linhas.append(f'🛵 Entrega: {taxa}' + (f' · chega em {entrega["tempo"]}' if entrega and entrega.get('tempo') else ''))
    if carrinho.get('taxas'):
        linhas.append(f'🧾 Taxas: {reais(carrinho["taxas"])}')
    desconto = carrinho.get('desconto') or (cupom or {}).get('valor')
    if desconto:
        linhas.append(f'🎁 Desconto: -{reais(desconto)}')
    if endereco:
        linhas.append(f'🏠 {endereco.get("apelido") or "Endereço"}: {endereco.get("texto") or ""}'.rstrip(': '))
    if pagamento:
        linhas.append(f'💳 {pagamento["nome"]}')
    linhas += ['', f'*Total: {reais(carrinho.get("total"))}*', '', 'Posso fazer o pedido?']
    return '\n'.join(linhas)


B_CONFIRMAR = '✅ Confirmar pedido'
B_MUDAR = ('mudar', '✏️ Mudar algo')
B_CANCELAR = ('cancelar', '❌ Cancelar')
O_QUE_MUDAR = 'O que você quer mudar? 👇'
CANCELADO = 'Tudo bem, cancelei. Nada foi comprado. 🙂'
ENVIANDO = 'Já estou fazendo seu pedido, só um instante... ⏳'


def pedido_feito(numero=None, tempo=None, codigo_entrega=None, tipo_pagamento=None):
    linhas = ['🎉 *Pedido feito!*']
    if numero:
        linhas.append(f'Número do pedido: *{numero}*')
    if tempo:
        linhas.append(f'🛵 Chega em {tempo}.')
    if codigo_entrega:
        linhas.append(f'🔑 Código de entrega: *{codigo_entrega}* (fale pro entregador)')
    if tipo_pagamento == 'PIX':
        # o submitOrder não devolve o código PIX (nem QR): o pagamento segue pelo app do iFood
        linhas.append('💠 Pagamento por PIX: se o iFood pedir, o código aparece no app do iFood, no seu pedido.')
    linhas.append('\nEu te aviso aqui quando sair pra entrega.')
    return '\n'.join(linhas)


OFERECER_REPETIR = 'Quer que eu te lembre de pedir isso de novo? 🔁'
B_REC_SEMANA = ('rec:7', 'Toda semana')
B_REC_MES = ('rec:30', 'Todo mês')
B_REC_NAO = ('rec:0', 'Não precisa')


def recorrencia_ok(dias):
    quando = 'toda semana' if dias == 7 else 'todo mês' if dias == 30 else f'a cada {dias} dias'
    return f'Combinado! ✅ Eu te lembro {quando}. Pra parar, é só escrever *parar lembrete*.'


def lembrete(resumo_pedido):
    return f'🔔 Hora de pedir de novo?\n\n{resumo_pedido}\n\nToque em *Pedir de novo* que eu monto tudo igual.'


B_LEMBRETE_PEDIR = 'Pedir de novo'
B_LEMBRETE_HOJE_NAO = 'Hoje não'
B_LEMBRETE_PARAR = 'Parar lembretes'
LEMBRETE_PARADO = 'Pronto, não vou mais lembrar desse pedido. 🙂'
LEMBRETE_ADIADO = 'Tudo bem! Te lembro na próxima vez. 🙂'

# --- pós-pedido -------------------------------------------------------------------------

SEM_PEDIDO = 'Você ainda não fez nenhum pedido por aqui. 🙂'
QUAL_REPETIR = 'Qual pedido você quer repetir? 👇'
NADA_PRA_REPETIR = 'Não achei pedidos antigos pra repetir. 🙂\nMe diga o que você quer pedir.'

STATUS = {  # códigos do trackOrder (doc do portal); o código em si nunca é mostrado
    'ORDER_CREATED': '🧾 Seu pedido foi registrado.',
    'PAYMENT_DECLINED': '❌ O pagamento não passou. Confira no app do iFood ou faça o pedido de novo.',
    'CONFIRMED': '✅ A loja confirmou seu pedido.',
    'PREPARING': '👨‍🍳 Seu pedido está sendo preparado.',
    'DISPATCHED': '🛵 Seu pedido saiu pra entrega!',
    'ON_THE_WAY': '🛵 O entregador está a caminho!',
    'ORDER_LATE': '⏰ Seu pedido está um pouco atrasado, mas continua a caminho.',
    'DELIVERY_ARRIVED_AT_DESTINATION': '📍 O entregador chegou! Pode ir receber.',
    'DELIVERED': '✅ Pedido entregue. Bom proveito! 😋',
    'CANCELLED': '❌ Seu pedido foi cancelado. Confira no app do iFood.',
}


def status_pedido(codigo, descricao=''):
    return STATUS.get(codigo) or f'📦 {descricao or codigo}'


# --- conta ------------------------------------------------------------------------------

SAIU = 'Pronto, desconectei sua conta do iFood. 👋 Quando quiser voltar, é só mandar um oi.'
APAGAR_CONFIRMA = ('Quer mesmo apagar seus dados? 🗑️\n'
                   'Vou desconectar sua conta do iFood e apagar nossa conversa, endereço e lembretes.')
B_APAGAR_SIM = ('apagar_sim', 'Sim, apagar')
B_APAGAR_NAO = ('apagar_nao', 'Não, voltar')
APAGADO = '✅ Pronto, apaguei tudo. Seu número agora é tratado como novo. 👋'
