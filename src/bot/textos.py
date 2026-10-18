"""Tudo que o bot fala, num lugar só.

Regra de escrita (o público é quem tem dificuldade com o celular):
- frase curta, palavra do dia a dia, nada de "carrinho de compras", "checkout", "método";
- um emoji no começo da linha serve de âncora visual; não enfeitar além disso;
- toda mensagem termina dizendo o que fazer ("toque em...", "pode escrever"); áudio fica fora das dicas por enquanto;
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
B_SUGERIR = ('sugerir', '💡 Me sugere algo')


def falta_minimo(falta, loja=None):
    return f'Faltam *{reais(falta)}* pro pedido mínimo' + (f' do *{loja}*.' if loja else '.')


def sugestao(termo, de_onde, falta=None, loja=None):
    """de_onde: 'combina' (acompanha o carrinho), 'costuma' (histórico nosso) ou 'parecido' (carrinho)."""
    topo = falta_minimo(falta, loja) + ' 🙂\n' if falta else ''
    if de_onde == 'combina':
        return f'{topo}Que tal *{termo}* pra acompanhar? Olha as opções 👇'
    motivo = 'que você costuma levar' if de_onde == 'costuma' else 'parecido com o que você já pegou'
    return f'{topo}Separei *{termo}*, {motivo}. Olha as opções 👇'


SEM_SUGESTAO = ('Não achei uma sugestão boa nessa loja. 😕\n'
                'Me diz o que você quer que eu procuro ✍️')
B_TIRAR = ('tirar', '🗑️ Tirar um item')
B_TENTAR = ('tentar', '🔁 Tentar de novo')
B_SIM = 'Sim'
B_NAO = 'Não'

MENU = [B_PEDIR, B_REPETIR, B_MEU_PEDIDO]

# --- boas-vindas e login -----------------------------------------------------------------


def boas_vindas(nome):
    oi = f'Olá, {nome}! 👋' if nome else 'Olá! 👋'
    return (f'{oi}\nEu faço suas compras do iFood aqui pelo WhatsApp: mercado, farmácia, '
            'restaurante...\n\nÉ só me escrever o que você precisa. ✍️')


LOGIN = ('🔐 Primeiro, preciso que você entre na sua conta do iFood.\n\n'
         'Toque no botão abaixo. Se você ainda não tem conta, dá pra criar lá mesmo, de graça.')
LOGIN_BOTAO = 'Entrar no iFood'
LOGIN_RODAPE = 'Depois de entrar, volte pra cá'
LOGIN_DE_NOVO = ('🔐 Sua entrada no iFood venceu. Toque no botão pra entrar de novo, '
                 'é rapidinho.')
LOGIN_AINDA = ('Ainda estou esperando você entrar no iFood. 🙂\n'
               'Toque em *Entrar no iFood* aqui embaixo.')


def logou(nome, conta=None):
    oi = f'Pronto, {nome}! ✅' if nome else 'Pronto! ✅'
    if not conta:
        return f'{oi} Você entrou no iFood.'
    # mostra de quem é a conta: 3 celulares já entraram na MESMA conta sem perceber (17/10)
    return f'{oi} Você entrou no iFood na conta de *{conta}*.\nNão é a sua conta? Escreva *sair* e entre de novo.'


PERGUNTA_PEDIDO = ('O que você quer pedir? 😊\n\n'
                   'Pode escrever do seu jeito ✍️\n'
                   'Exemplo: _pão, leite e café_')

AJUDA = ('Eu faço pedidos no iFood pra você. 🛒\n\n'
         '1️⃣ Me escreva o que você quer\n'
         '2️⃣ Eu mostro as opções com foto\n'
         '3️⃣ Você toca em *Quero esse*\n'
         '4️⃣ No final eu mostro o resumo e você confirma\n\n'
         'Nada é comprado sem você confirmar.')

FORA_DO_ESCOPO = ('Eu só sei fazer pedidos no iFood 🙂\n'
                  'Me diga o que você quer comprar, ou toque num botão.')

NAO_ENTENDI = ('Desculpe, não entendi. 🙏\n'
               'Pode escrever de outro jeito ou tocar num botão.')

AUDIO_RUIM = ('Não consegui ouvir seu áudio direito. 🙉\n'
              'Pode mandar de novo, ou escrever?')

ERRO = ('Ops, deu um probleminha aqui do meu lado. 😕\n'
        'Toque em *Tentar de novo*.')
ERRO_SEM_BOTAO = ('Ops, deu um probleminha aqui do meu lado. 😕\n'
                  'Mande sua mensagem de novo, por favor.')

BOTAO_VELHO = 'Esse botão é de uma conversa antiga. Vamos continuar daqui: 👇'

DE_NADA = 'Por nada! 😊 Quando precisar, é só chamar.'

# --- modo áudio (src/bot/voz.py): só pra quem pede ---------------------------------------

VOZ_LIGADA = 'Pode deixar! 🎤 A partir de agora eu te respondo por áudio.'
VOZ_DESLIGADA = 'Combinado! ✍️ Voltei a responder por escrito.'
VOZ_INDISPONIVEL = ('Ainda não consigo mandar áudio por aqui. 😕\n'
                    'Mas pode me mandar os seus, que eu escuto e respondo por escrito.')

# --- endereço ---------------------------------------------------------------------------

PEDIR_ENDERECO = ('🏠 Pra onde eu mando suas compras?\n\n'
                  'Escreva o endereço com rua, número e cidade.\n'
                  'Exemplo: _Rua das Flores, 120, São Carlos_')
ENDERECO_NAO_ACHEI = ('Não achei esse endereço. 😕\n'
                      'Confira e escreva de novo, com rua, número e cidade.')
ENDERECO_DICA = 'Escreva *rua, número e cidade*, ou só o *CEP*. 🙂'
ENDERECO_AINDA = '😊 Pra montar o pedido, primeiro preciso do endereço de entrega.\n' + ENDERECO_DICA
ENDERECO_NAO_PARECE = 'Hmm, isso não parece um endereço. 🤔\n' + ENDERECO_DICA
AINDA_AI = 'Ainda está por aí? 😊'
ENDERECO_FALTA_POUCO = '😊 Falta só isso pra eu salvar o seu endereço:'
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


def _item_dito(i):
    """'*2x pão francês*', '*pizza* (frango catupiry)': quantidade e observação só se a pessoa disse."""
    qtd = f"{i['quantidade']}x " if i.get('quantidade') else ''
    return f"*{qtd}{i['termo']}*" + (f" ({i['observacao']})" if i.get('observacao') else '')


def anotei(itens):
    """'Anotei: *pizza de calabresa*, *pizza* (frango catupiry) e *coca-cola* (2 litros) ✅'; sem itens, só
    'Anotei ✅'. O que veio na observação (sabor, tamanho) aparece entre parênteses."""
    nomes = [_item_dito(i) for i in itens]
    if not nomes:
        return 'Anotei ✅'
    return 'Anotei: ' + (nomes[0] if len(nomes) == 1 else ', '.join(nomes[:-1]) + ' e ' + nomes[-1]) + ' ✅'


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


def card_curto(oferta):
    """Card do carrossel: 160 caracteres e 3 linhas no máximo (limite da Meta)."""
    nome = oferta['nome'] if len(oferta['nome']) <= 70 else oferta['nome'][:69].rstrip() + '…'
    preco = f'💰 {reais(oferta.get("preco"))}'
    if oferta.get('preco_antigo'):
        preco += f' ~{reais(oferta["preco_antigo"])}~'
    extras = [x for x in (f'⭐ {str(oferta["nota"]).replace(".", ",")}' if oferta.get('nota') else '',
                          f'🛵 {oferta["tempo"]}' if oferta.get('tempo') else '') if x]
    loja = (oferta.get('loja') or '')[:40]
    return '\n'.join([f'*{nome}*', preco + (f' · {loja}' if loja else ''), ' · '.join(extras)]).strip()


def topo_carrossel(termo):
    return f'Achei *{termo}* pra você 👇\nArraste pro lado pra ver todas e toque em *{B_QUERO}*.'

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

CPF_OBRIGATORIO = ('🧾 Essa loja exige *CPF na nota* pra fazer o pedido.\n'
                   'Escreva seu CPF aqui (só os números), por favor. 🙂')

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


def oferecer_repetir(oque):
    """Oferta a partir da 2ª compra do item/categoria. Deixa claro o combinado: no dia eu pergunto,
    e só peço com o "sim" da pessoa."""
    if not oque:
        return OFERECER_REPETIR
    return (f'Opa, segunda vez de *{oque}* por aqui! 😋 Bateu fome, já sabe: é só chamar.\n\n'
            '🔁 Quer deixar no automático? No dia combinado eu te chamo aqui com tudo pronto: '
            'mesmo pedido, mesmo endereço, mesma forma de pagamento. '
            'Você só responde *sim* e eu peço pra entregar na sua casa. '
            'Sem precisar procurar de novo, é pra facilitar sua vida. 💜\n\n'
            'Nada é pedido nem cobrado sem o seu sim, e dá pra parar quando quiser.')


B_REC_SEMANA = ('rec:7', 'Toda semana')
B_REC_MES = ('rec:30', 'Todo mês')
B_REC_NAO = ('rec:0', 'Não precisa')


def frequencia(dias):
    return {1: 'todo dia', 7: 'toda semana', 15: 'a cada 15 dias', 30: 'todo mês'}.get(dias, f'a cada {dias} dias')


def quando(dias, hora=None):
    """'todo dia', 'toda semana às 18h'."""
    if not hora:
        return frequencia(dias)
    h, _, m = str(hora).partition(':')
    return f'{frequencia(dias)} às {int(h)}h' + (f'{m}' if m and m != '00' else '')


def agendar_depois(dias, hora=None):
    return (f'Fechado! 🔁 Assim que esse pedido sair, eu deixo ele no automático *{quando(dias, hora)}*: '
            'no dia eu te chamo aqui e só peço com o seu *sim*. 😉\nVamos terminar o de hoje?')


AGENDAR_SEM_PEDIDO = ('Bora deixar no automático! 🔁 Me diga o que e quando, do seu jeito '
                      '(ex.: _todo dia às 7h, dois pães_), que eu monto com você. 😋')


def agendar_itens(itens, dias, hora=None):
    """Começo do automático com itens: o que entra, quando, e que hoje nada é pedido."""
    return (f'{anotei(itens)} 🔁 Vou deixar no automático *{quando(dias, hora)}*.\n'
            'Agora a gente escolhe uma vez a loja e o produto, e *nada é pedido hoje*. No dia eu te chamo '
            'e só peço com o seu *sim*. 😉')


def modelo_ok(resumo, loja, dias, hora=None):
    return (f'Combinado! ✅ *{quando(dias, hora).capitalize()}* eu te chamo aqui pra pedir *{resumo}*'
            + (f' do *{loja}*' if loja else '') + '. Nada foi pedido agora: no dia, com o seu *sim*, '
            'o pedido sai. 🛵\nPra parar, é só escrever *parar lembrete*.')


def confirmar_agendar(resumo, dias, hora=None):
    """Pediu automático sem dizer o quê: oferece o último pedido (sem o papo de "segunda vez")."""
    return (f'Quer deixar *{resumo}* no automático *{quando(dias, hora)}*? 🔁\n'
            'No dia eu te chamo aqui com tudo pronto e só peço com o seu *sim*. Dá pra parar quando quiser.')


def recorrencia_ok(dias, hora=None):
    return (f'Combinado! ✅ Agendado *{quando(dias, hora)}*: no dia eu te chamo aqui e, com o seu *sim*, '
            f'o pedido sai na hora. 🛵\nPra parar, é só escrever *parar lembrete*.')


def lembrete(rec, endereco=None):
    """No dia: pergunta se pode pedir, mostrando tudo que vai ser cobrado. O "sim" é a confirmação."""
    if isinstance(rec, str):
        rec = {'resumo': rec}
    linhas = ['🔔 Chegou o dia! Tá com fome de quê? A gente já sabe. 😋', '', f'🧾 {rec.get("resumo") or ""}']
    if rec.get('loja'):
        linhas.append(f'🏪 {rec["loja"]}')
    if endereco:
        linhas.append(f'🏠 {endereco.get("apelido") or "Endereço"}: {endereco.get("texto") or ""}'.rstrip(': '))
    if rec.get('pagamento'):
        linhas.append(f'💳 {rec["pagamento"]}')
    if rec.get('total'):
        linhas.append(f'💰 Da última vez: {reais(rec["total"])} (pode variar um pouquinho)')
    linhas += ['', '*Podemos pedir aqui pra enviar na sua casa?*',
               'Se tocar em *Sim, pode pedir*, eu faço o pedido agora nessa forma de pagamento.']
    return '\n'.join(linhas)


PRECO_SUBIU = '⚠️ O preço mudou desde a última vez, então confere antes de eu pedir:'
B_LEMBRETE_PEDIR = 'Sim, pode pedir'
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
    'CANCELED': '❌ Seu pedido foi cancelado. Confira no app do iFood.',
    'CONCLUDED': '✅ Pedido concluído. Bom proveito! 😋',
}


def status_pedido(codigo, descricao=''):
    """Código novo do iFood (a lista da doc não é fechada) cai aqui: a descrição vem em inglês,
    então nunca mostra ela crua ("Order was completed.")."""
    if codigo in STATUS:
        return STATUS[codigo]
    d = f'{codigo or ""} {descricao or ""}'.lower()
    if any(k in d for k in ('complet', 'conclu', 'deliver', 'finish')):
        return STATUS['CONCLUDED']
    if 'cancel' in d:
        return STATUS['CANCELLED']
    if 'prepar' in d:
        return STATUS['PREPARING']
    if any(k in d for k in ('confirm', 'accept')):
        return STATUS['CONFIRMED']
    if any(k in d for k in ('dispatch', 'way', 'route', 'picked')):
        return STATUS['ON_THE_WAY']
    return '📦 Seu pedido teve uma atualização. Os detalhes estão no app do iFood.'


# --- conta ------------------------------------------------------------------------------

SAIU = 'Pronto, desconectei sua conta do iFood. 👋 Quando quiser voltar, é só mandar um oi.'
APAGAR_CONFIRMA = ('Quer mesmo apagar seus dados? 🗑️\n'
                   'Vou desconectar sua conta do iFood e apagar nossa conversa, endereço e lembretes.')
B_APAGAR_SIM = ('apagar_sim', 'Sim, apagar')
B_APAGAR_NAO = ('apagar_nao', 'Não, voltar')
APAGADO = '✅ Pronto, apaguei tudo. Seu número agora é tratado como novo. 👋'
