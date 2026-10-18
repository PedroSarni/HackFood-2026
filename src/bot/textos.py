"""Tudo que o bot fala, num lugar só.

Regra de escrita (o público é quem tem dificuldade com o celular):
- frase curta, palavra do dia a dia, nada de "carrinho de compras", "checkout", "método";
- um emoji no começo da linha serve de âncora visual; não enfeitar além disso;
- toda mensagem termina dizendo o que fazer ("toque em...", "pode escrever"); áudio fica fora das dicas por enquanto;
- botão com até 20 caracteres (limite da Meta), verbo ou resposta direta.
"""
import re

from src.bot.grupo import MAX_PESSOAS, por_pessoa
from src.shared.whatsapp import tamanho


def reais(v):
    if v is None:
        return ''
    s = f'{float(v):,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')


def somar_iguais(itens):
    """'4x Leite integral' + '1x Leite integral' viram '5x Leite integral' (preço da linha somado).
    O carrinho continua com as duas linhas; isto é só como o pedido aparece pra pessoa."""
    juntos = {}
    for it in itens or []:
        j = juntos.get(it['nome'])
        if j is None:
            juntos[it['nome']] = dict(it)
            continue
        j['qtd'] += it['qtd']
        if j.get('preco_total') is not None and it.get('preco_total') is not None:
            j['preco_total'] = round(j['preco_total'] + it['preco_total'], 2)
        else:
            j['preco_total'] = None
    return list(juntos.values())


def lista_itens(itens):
    """'5x Leite integral, 1x Pão francês': o que vai no lembrete e no "Combinado!" do automático."""
    return ', '.join(f'{i["qtd"]}x {i["nome"]}' for i in somar_iguais(itens))


# --- botões fixos (id, título) --------------------------------------------------------

B_PEDIR = ('pedir', '🛒 Fazer pedido')
B_NOVO_PEDIDO = ('pedir', '🛒 Fazer novo pedido')   # o perguntar troca sozinho quando já tem pedido feito
B_ATUALIZAR = ('meu_pedido', '🔄 Atualizar status')
B_REPETIR = ('repetir', '🔁 Pedir de novo')
B_MEU_PEDIDO = ('meu_pedido', '📦 Meu pedido')
B_INICIO = ('inicio', '🏠 Início')
B_OUTRA = ('outra', '🔎 Procurar outra')
B_TROCAR_LOJA = ('loja', '🏪 Trocar de loja')     # lista com plano (src/bot/melhor_loja.py)
B_FICAR_NA_LOJA = ('loja_fica', '↩️ Continuar aqui')
B_FINALIZAR = ('fim', '✅ Finalizar pedido')
B_MAIS_COISAS = ('add', '➕ Quero mais coisas')
B_SUGERIR = ('sugerir', '💡 Me sugere algo')


def falta_minimo(falta, loja=None):
    return f'Faltam *{reais(falta)}* pro pedido mínimo' + (f' do *{loja}*.' if loja else '.')


def sugestao(termo, de_onde, falta=None, loja=None):
    """de_onde: 'combina' (acompanha o carrinho), 'costuma' (histórico nosso), 'parecido' (carrinho) ou
    'hora' (sem carrinho nem histórico: algo da hora do dia)."""
    topo = falta_minimo(falta, loja) + ' 🙂\n' if falta else ''
    if de_onde == 'combina':
        return f'{topo}Que tal *{termo}* pra acompanhar? Olha as opções 👇'
    if de_onde == 'hora':
        return f'{topo}Que tal *{termo}*? Separei umas opções 👇'
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
    """Bem simplesinha (17/10, pedido do Fabio): as ideias vêm logo embaixo, na vitrine."""
    oi = f'Oi, {nome}! 😊' if nome else 'Oi! 😊'
    return f'{oi}\nO que você quer pedir hoje? Pode escrever ou mandar áudio.'


VITRINE_TOPO = 'Separei umas ideias pra você 👇'


def card_vitrine(card):
    """Card da vitrine (src/bot/vitrine.py): título em negrito e uma linha; 160 caracteres, 2 quebras."""
    return f'*{card["titulo"]}*\n{card["texto"]}'


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
FOTO_RUIM = ('Não consegui ver sua foto direito. 🙈\n'
             'Pode mandar de novo, ou me escrever o que você quer?')
MIDIA_RUIM = ('Não consegui entender o que você mandou. 😕\n'
              'Pode mandar de novo, ou escrever?')


def midia_ruim(tipos):
    """O aviso certo pro que chegou: foto não é "não consegui ouvir seu áudio" (17/10 23h)."""
    tipos = set(tipos)
    return FOTO_RUIM if tipos == {'imagem'} else AUDIO_RUIM if tipos == {'audio'} else MIDIA_RUIM

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
def sim_ou_acompanhamento(sugestao):
    return f'Só pra eu não errar: faço o pedido assim ou coloco *{sugestao}* antes? 🙂'


NADA_PRA_MUDAR = 'Ainda não tem nada no carrinho pra mudar. 🙂'
CARRINHO_ABANDONADO = 'Esvaziei seu carrinho pra não ficar parado. 🙂 Quando quiser, é só pedir de novo.'
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


def mais_alguma(total, pessoas=None, falta=None, loja=None):
    aviso = f'\n{falta_minimo(falta, loja)}' if falta and falta > 0.005 else ''
    return (f'🧺 Seu pedido até agora: *{reais(total)}*{dividido(total, pessoas, linha=True)}{aviso}'
            '\n\nQuer mais alguma coisa?')


def minimo_da_loja(carrinho):
    """Resposta pro "qual o pedido mínimo?": o mínimo da loja, nunca o valor do carrinho."""
    loja, minimo, sub = carrinho.get('loja'), carrinho.get('minimo'), carrinho.get('subtotal') or 0
    if not carrinho.get('itens') or not loja:
        return 'O pedido mínimo muda de loja pra loja. 🙂 Quando você escolher algo, eu te aviso se faltar.'
    if not minimo:
        return f'O *{loja}* não tem pedido mínimo. 🙂'
    texto = f'O pedido mínimo do *{loja}* é *{reais(minimo)}*.'
    if sub < minimo - 0.005:
        return texto + f' Seu pedido está em {reais(sub)}: faltam *{reais(minimo - sub)}*. 🙂'
    return texto + f' Seu pedido ({reais(sub)}) já passou do mínimo. ✅'


# --- fechamento -------------------------------------------------------------------------

CARRINHO_VAZIO = '🧺 Seu pedido está vazio agora, não tem nenhum item nele.'

FECHANDO ='⏳ Fechando com a loja (entrega, pagamento e cupom). Já te mando o resumo!'

CPF_OBRIGATORIO = ('🧾 Essa loja exige *CPF na nota* pra fazer o pedido.\n'
                   'Escreva seu CPF aqui (só os números), por favor. 🙂')

PEDIR_CPF = ('🧾 Pra nota fiscal, me mande seu *CPF* (só os números).\n'
             'Se não quiser, toque em *Sem CPF*.')
B_SEM_CPF = ('cpf_nao', 'Sem CPF')
CPF_INVALIDO = 'Esse CPF não parece certo. 🤔 Confira os números e mande de novo.'
CPF_ANOTADO = '✅ Anotei seu CPF pra nota fiscal.'


def sobre_pedido(sobre, pedido, endereco=None):
    """Resposta pra pergunta sobre o pedido feito; None = é o status (vem do rastreio)."""
    if sobre == 'codigo_entrega':
        if not pedido.get('codigo_entrega'):
            return 'Ainda não tenho o código de entrega desse pedido. 😕 Ele aparece no app do iFood, em *Pedidos*.'
        return f'🔑 O código de entrega é *{pedido["codigo_entrega"]}*. Fale ele pro entregador quando ele chegar. 🛵'
    if sobre == 'total':
        pago = f' ({pedido["pagamento"]})' if pedido.get('pagamento') else ''
        return f'🧾 Seu último pedido deu *{reais(pedido.get("total"))}*{pago}.'
    if sobre == 'itens':
        loja = f'\n🏪 {pedido["loja"]}' if pedido.get('loja') else ''
        return f'🧾 Você pediu: {pedido.get("resumo") or "—"}{loja}'
    if sobre == 'pagamento':
        if not pedido.get('pagamento'):
            return 'A forma de pagamento desse pedido aparece no app do iFood, em *Pedidos*. 🙂'
        return f'💳 Pagamento: *{pedido["pagamento"]}*.'
    if sobre == 'endereco':
        return f'🏠 Vai pra: {pedido.get("endereco") or endereco or "o endereço salvo"}'
    return None
QUAL_PAGAMENTO = 'Como você quer pagar? 💳'
QUAL_ENTREGA = 'Quando você quer receber? 🛵'
LOJA_FECHADA = 'Essa loja não está entregando agora. 😕'


def resumo(carrinho, endereco, entrega, pagamento, cupom=None, pessoas=None, sugestao=None):
    linhas = ['🧾 *Confira seu pedido:*', '']
    for it in somar_iguais(carrinho['itens']):
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
    linhas += ['', f'*Total: {reais(carrinho.get("total"))}*' + dividido(carrinho.get('total'), pessoas, linha=True)]
    if sugestao:  # uma sugestão do que acompanha, sem passo a mais: é só falar
        linhas += ['', f'💡 Quer *{sugestao}* pra acompanhar? É só falar que eu coloco.']
    linhas += ['', 'Posso fazer o pedido?']
    return '\n'.join(linhas)


B_CONFIRMAR = '✅ Confirmar pedido'
B_MUDAR = ('mudar', '✏️ Mudar algo')
B_FAZER_ASSIM = '✅ Fazer pedido assim'   # na pergunta de volta do "sim" ambíguo (resumo com sugestão)
B_MUDAR_CURTO = ('mudar', '✏️ Mudar')
B_CANCELAR = ('cancelar', '❌ Cancelar')
O_QUE_MUDAR = 'O que você quer mudar? 👇'
CANCELADO = 'Tudo bem, cancelei. Nada foi comprado. 🙂'
ENVIANDO = 'Já estou fazendo seu pedido, só um instante... ⏳'


def pedido_feito(numero=None, tempo=None, codigo_entrega=None, tipo_pagamento=None, total=None, pessoas=None):
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
    if pessoas and por_pessoa(total, pessoas):
        linhas.append(f'👥 Dá {reais(por_pessoa(total, pessoas))} pra cada um ({pessoas} pessoas). Bom apetite, galera! 😋')
    linhas.append('\nEu te aviso aqui quando sair pra entrega.')
    return '\n'.join(linhas)


OFERECER_REPETIR = 'Quer que eu te lembre de pedir isso de novo? 🔁'


def oferecer_repetir(oque):
    """Oferta na 2ª compra do item/categoria (só nela, pra não virar chatice). Deixa claro o combinado: no dia eu pergunto,
    e só peço com o "sim" da pessoa."""
    if not oque:
        return OFERECER_REPETIR
    return (f'Opa, segunda vez de *{oque}* por aqui! 😋\n\n'
            '🔁 Quer deixar no automático? No dia combinado eu te chamo com tudo pronto (mesmo pedido, '
            'endereço e pagamento) e só peço com o seu *sim*. Dá pra parar quando quiser.')


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


# "Tá com fome de quê?" só cabe em comida: na Drogaria Saúde, com dipirona e paracetamol, soava estranho (18/10)
_FARMACIA = re.compile(r'drogaria|farm[aá]cia|droga|\bmg\b|dipirona|paracetamol|rem[eé]dio|comprimido', re.I)
_COMPRAS = re.compile(r'mercad|atacad|hortifruti|sacol[aã]o|empor|\bpet\b|ra[cç][aã]o|adega|bebida|dep[oó]sito', re.I)


def _abertura_lembrete(rec):
    onde = f'{rec.get("loja") or ""} {rec.get("resumo") or ""}'
    if _FARMACIA.search(onde):
        return 'Hora de repor seus itens da farmácia. 💊'
    if _COMPRAS.search(rec.get('loja') or ''):
        return 'Hora de repor as compras. 🛒'
    return 'Tá com fome de quê? A gente já sabe. 😋'


def lembrete(rec, endereco=None):
    """No dia: pergunta se pode pedir, mostrando tudo que vai ser cobrado. O "sim" é a confirmação."""
    if isinstance(rec, str):
        rec = {'resumo': rec}
    linhas = [f'🔔 Chegou o dia! {_abertura_lembrete(rec)}', '', f'🧾 {rec.get("resumo") or ""}']
    if rec.get('loja'):
        linhas.append(f'🏪 {rec["loja"]}')
    if endereco:
        linhas.append(f'🏠 {endereco.get("apelido") or "Endereço"}: {endereco.get("texto") or ""}'.rstrip(': '))
    if rec.get('pagamento'):
        linhas.append(f'💳 {rec["pagamento"]}')
    from src.bot.recorrencia import preco_da_ultima_vez
    campo, valor = preco_da_ultima_vez(rec)
    if valor and campo == 'total':
        linhas.append(f'💰 Da última vez: {reais(valor)} (pode variar um pouquinho)')
    elif valor:  # automático que ainda não saiu: a entrega só se sabe no dia
        linhas.append(f'💰 Itens: {reais(valor)} + entrega (pode variar um pouquinho)')
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


# --- foto vira pedido (src/bot/foto.py) -------------------------------------------------

B_FOTO_SIM = ('foto:sim', '😋 Sim, quero!')
B_FOTO_NAO = ('foto:nao', 'Não, obrigado')
FOTO_RUIM = ('Não consegui ver sua foto direito. 🙈\n'
             'Pode mandar de novo, mais de perto, ou escrever o que você quer?')
FOTO_ILEGIVEL = ('Recebi sua foto, mas não consegui ler o que está escrito. 🙈\n'
                 'Pode mandar outra mais de perto, ou escrever a lista aqui?')
FOTO_NO_CPF = ('Por segurança, nessa etapa eu não abro fotos. 🔒\n'
               'Escreva o CPF com os números, por favor. 🙂')


def foto_parecido(descricao, fala=None):
    topo = fala or ('Que delícia! 😋' + (f' Vi aqui: *{descricao}*.' if descricao else ''))
    return f'{topo}\n\nQuer que eu procure algo parecido pra você pedir? 👇'


def foto_outro(fala=None):
    return ((fala or 'Recebi sua foto! 🙂') + '\n\nMe manda a foto de uma comida, de um produto ou da sua '
            'lista de compras, ou escreva o que você quer. ✍️')


def parecidos(descricao):
    return f'🔎 Procurei coisas parecidas com *{descricao}*:' if descricao else '🔎 Procurei coisas parecidas:'


def sem_parecido(descricao, loja=None):
    onde = f'no {loja}' if loja else 'perto de você'
    return (f'Não achei nada parecido com *{descricao or "isso"}* {onde}. 😕\n'
            'Me escreve o que você quer que eu procuro ✍️')


def li_a_foto(itens):
    return '📸 Li sua foto! ' + anotei(itens)


# --- dividir com os amigos (src/bot/grupo.py) -------------------------------------------

B_KIT_OK = ('kit:ok', '✅ Quero esse kit')
B_KIT_OUTRA = ('kit:outra', '🔄 Outra loja')
B_KIT_NAO = ('kit:nao', '❌ Não quero')
B_PESSOAS = [('grupo_n:2', '2 pessoas'), ('grupo_n:4', '4 pessoas'), ('grupo_n:6', '6 pessoas')]
GRUPO_QUANTAS = '👥 Pra quantas pessoas é, contando com você?\nToque ou escreva o número.'
GRUPO_DEMAIS = (f'Pra mais de {MAX_PESSOAS} pessoas é melhor combinar direto com a loja. 😅\n'
                f'Me diz um número de 2 a {MAX_PESSOAS}.')
KIT_SEM_OUTRA_LOJA = 'Só achei essa loja perto de você pra esse kit. 🙂'
KIT_DICA = 'Pode ser? Toque em *Quero esse kit* ou me diga o que mudar (ex.: _sem refri_, _mais barato_).'


def dividido(total, pessoas, linha=False):
    """'👥 *R$ 36,42 por pessoa* (5 pessoas)'; vazio se não é pedido em grupo."""
    cada = por_pessoa(total, pessoas) if pessoas and pessoas > 1 else None
    if not cada:
        return ''
    return ('\n' if linha else '') + f'👥 *{reais(cada)} por pessoa* ({pessoas} pessoas)'


def grupo_o_que(pessoas=None):
    quem = f' pra {pessoas} pessoas' if pessoas else ''
    return (f'😋 Bora montar um kit{quem}! O que vocês querem comer?\n'
            'Exemplo: _hambúrguer_, _pizza_, _esfiha_')


def montando_kit(pessoas, termo):
    return f'👥 Montando um kit de *{termo}* pra *{pessoas} pessoas*... ⏳'


def kit(k, troca=None, _nome=60, _fala=True):
    """O kit na tela: o que vai, quanto custa e quanto dá pra cada. Os números são do código.
    Vai com botões, então cabe em 1024 caracteres: se passar, sai a fala e os nomes encurtam."""
    linhas = [f'👥 *Kit pra {k["pessoas"]} pessoas* · {k["loja"]}']
    if k.get('explicacao') and _fala:
        linhas.append(f'_{k["explicacao"]}_')
    linhas.append('')
    for lin in k['linhas']:
        nome = lin['nome'] if len(lin['nome']) <= _nome else lin['nome'][:_nome - 1].rstrip() + '…'
        linhas.append(f'• {lin["qtd"]}x {nome} — {reais(lin["total"])}')
    linhas.append('')
    if k.get('taxa') is not None:
        linhas.append(f'🛵 Entrega: {reais(k["taxa"]) if k["taxa"] else "grátis"}')
    linhas.append(f'💰 *Total: {reais(k["total"])}*' + ('' if k.get('taxa') is not None else ' + entrega'))
    linhas.append(dividido(k['total'], k['pessoas']))
    if k.get('faltou'):
        linhas.append(f'⚠️ Não achei {", ".join(k["faltou"])} nessa loja.')
    if troca:
        linhas.append(f'⚠️ Esse kit troca o pedido que você estava montando no *{troca}*.')
    linhas += ['', KIT_DICA]
    texto = '\n'.join(linhas)
    if tamanho(texto) > 1000 and _nome > 30:
        return kit(k, troca, _nome=30, _fala=False)
    return texto


def kit_sem_principal(termo):
    return f'Não achei *{termo}* perto de você pra montar o kit. 😕\nQuer tentar outra comida? É só escrever ✍️'


def kit_no_pedido(loja):
    return f'✅ Coloquei o kit no seu pedido do *{loja}*.'


FINAIS = {'DELIVERED', 'CONCLUDED', 'CANCELLED', 'CANCELED', 'PAYMENT_DECLINED'}


def como_esta(codigo, descricao, pedido, previsao=None, sobre=None):
    """Status do pedido com o que a pessoa quer saber: onde está, quando chega, de onde vem, o código de
    entrega e o que vem. Entregue ou cancelado: o status e o que veio, sem previsão nem código."""
    status = status_pedido(codigo, descricao)
    final = codigo in FINAIS or status in (STATUS['CONCLUDED'], STATUS['CANCELLED'])
    linhas = [status]
    if previsao and not final:  # "Tá chegando?" (sobre=previsao): a previsão vem primeiro
        linhas.insert(0 if sobre == 'previsao' else 1, f'🕒 Chega {previsao}.')
    numero = f'pedido *{pedido["codigo"]}*' if pedido.get('codigo') else None
    if pedido.get('loja') or numero:
        linhas.append('🏪 ' + ' · '.join(x for x in (pedido.get('loja'), numero) if x))
    if pedido.get('codigo_entrega') and not final:
        linhas.append(f'🔑 Código de entrega: *{pedido["codigo_entrega"]}* (fale pro entregador)')
    if pedido.get('resumo'):
        linhas.append(f'🧾 {pedido["resumo"]}' + (f' — {reais(pedido["total"])}' if pedido.get('total') else ''))
    return '\n'.join(linhas)


# --- a loja da lista (src/bot/melhor_loja.py) -------------------------------------------------------

LOJA_DO_TIPO = {'MERCADO': 'mercado', 'RESTAURANTE': 'restaurante', 'FARMACIA': 'farmácia'}
NENHUMA_DO_TIPO = {'MERCADO': 'Nenhum mercado', 'RESTAURANTE': 'Nenhum restaurante', 'FARMACIA': 'Nenhuma farmácia'}
SEM_OUTRA_LOJA = 'Não achei outra loja perto que tenha esses itens. 😕'
SEM_LISTA_PRA_TROCAR = 'Ainda não tem pedido pra trocar de loja. Me diga o que você quer pedir. 🙂'
PROCURANDO_OUTRAS = '🔎 Vendo quais outras lojas têm tudo isso... ⏳'


def procurando_loja(termos, tipo_loja):
    linhas = '\n'.join(f'{i}. {t}' for i, t in enumerate(termos, 1))
    return (f'📝 Anotei sua lista:\n{linhas}\n\n'
            f'🔎 Vendo qual {LOJA_DO_TIPO.get(tipo_loja, "loja")} tem tudo e sai mais em conta... ⏳')


def loja_da_lista(loja, termos, tipo_loja, outras, primeiro):
    """A loja que vai levar a lista: tem tudo (ou o máximo), é a mais em conta, e o que fica de fora."""
    conta = f'a partir de *{reais(loja["custo"])}* com a entrega' + (f', chega em {loja["tempo"]}'
                                                                     if loja.get('tempo') else '')
    faltam = [t for i, t in enumerate(termos) if i not in loja['tem']]
    if not faltam:
        linhas = [f'🛒 *{loja["loja"]}* tem tudo da sua lista e é onde sai mais em conta: {conta}.']
    else:
        linhas = [f'🛒 {NENHUMA_DO_TIPO.get(tipo_loja, "Nenhuma loja")} perto tem tudo junto. *{loja["loja"]}* '
                  f'tem {len(termos) - len(faltam)} dos {len(termos)} itens e sai {conta}.',
                  'Fica de fora: ' + ', '.join(f'*{t}*' for t in faltam) + '.']
    linhas.append(f'\nVou te mostrar item por item, começando por *{primeiro}*. 👇')
    if outras:
        linhas.append('Prefere outra loja? Toque em *Trocar de loja* quando quiser.')
    return '\n'.join(linhas)


def linha_loja(loja, n):
    """'tem tudo · a partir de R$ 91,20 · 40-55 min' (cabe na descrição da lista: 72)."""
    tem = 'tem tudo' if len(loja['tem']) == n else f'tem {len(loja["tem"])} de {n}'
    return ' · '.join(x for x in (tem, f'a partir de {reais(loja["custo"])}', loja.get('tempo')) if x)


def qual_loja(lojas, n):
    linhas = [f'• *{lj["loja"]}*: {linha_loja(lj, n)}' for lj in lojas]
    return '🏪 Qual loja você prefere? Já com a entrega, pelos mais baratos de cada item:\n\n' + '\n'.join(linhas)


def troquei_de_loja(loja, levados, ficaram):
    linhas = [f'🔁 Pronto, agora é no *{loja}*.']
    if levados:
        linhas.append('O que você já tinha escolhido veio junto:')
        linhas += [f'• {i["qtd"]}x {i["nome"]}' + (f' — {reais(i["preco_total"])}' if i.get('preco_total') else '')
                   for i in levados]
    if ficaram:
        linhas.append('Não tem lá: ' + ', '.join(f'*{n}*' for n in ficaram) + '.')
    return '\n'.join(linhas)
