"""Conversas inteiras contra o MCP falso, do jeito que um idoso usaria."""
from tests.fakes import Mundo


def endereco_pronto(m):
    """Cadastra um endereço passando pelo fluxo de verdade."""
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.tocar('compl_nao')


def ids(m):
    return m.wpp.todos_ids()


# --- login e começo ----------------------------------------------------------------------

def test_primeira_mensagem_sem_login_pede_login_com_link():
    m = Mundo(logado=False)
    m.enviar('oi')
    tipo, d = m.wpp.saida[-1]
    assert tipo == 'link' and 'login' in d['url']
    assert m.estado()['fase'] == 'login'


def test_pedido_antes_do_login_e_retomado_depois_de_entrar():
    m = Mundo(logado=False)
    m.enviar('quero pão')
    assert m.wpp.saida[-1][0] == 'link'
    m.estado()['pendente']  # guardou o pedido
    m.wpp.limpar()
    m.logar()  # OAuth terminou
    textos = ' '.join(m.wpp.textos())
    assert 'Você entrou no iFood' in textos
    assert 'Pra onde eu mando' in textos  # retomou: agora pede o endereço pra buscar o pão


def test_saudacao_logado_mostra_menu():
    m = Mundo()
    m.enviar('bom dia')
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir', 'repetir', 'meu_pedido']


# --- endereço ----------------------------------------------------------------------------

def test_cadastro_de_endereco_e_busca_continua_sozinha():
    m = Mundo()
    endereco_pronto(m)
    e = m.estado()
    assert e['endereco']['id'] and e['endereco']['lat'] is not None
    assert [t for t, _ in m.wpp.saida].count('carrossel') == 1 and len(m.wpp.cards()) >= 2  # já buscou o pão
    criar = m.mcp.chamadas_de('createAddress')
    assert criar[-1]['candidateId'] and criar[-1]['address']  # doc: mandar os dois


def test_endereco_sem_bairro_pergunta_o_bairro():
    m = Mundo()
    m.enviar('quero leite')
    m.enviar('Rua Sem Bairro, 55, São Carlos')
    assert m.estado()['fase'] == 'bairro'
    m.enviar('Vila Prado')
    m.tocar('compl_nao')
    assert m.mcp.chamadas_de('createAddress')[-1]['neighborhood'] == 'Vila Prado'
    assert m.wpp.cards()


def test_endereco_sem_virgula_com_candidatos_iguais_nao_quebra():
    """Bug real de 17/10 16h43: dois candidatos com a mesma rua e número viraram dois botões
    com o mesmo título e a Meta recusou a mensagem (131009 Duplicate button title)."""
    m = Mundo()
    m.enviar('quero pao de queijo')
    m.enviar('adolfo cattani 676 sao carlos')
    tipo, d = m.wpp.saida[-1]
    assert tipo == 'botoes' and m.estado()['fase'] == 'endereco_escolha'
    titulos = [t for _, t in d['botoes']]
    assert len(set(titulos)) == len(titulos)
    assert 'Centro' in d['texto'] and 'Jardim' in d['texto']  # endereço completo no texto
    m.enviar('2')  # digitou o número em vez de tocar
    assert m.estado()['fase'] == 'complemento'


def test_mensagem_recusada_pela_meta_vira_texto_numerado():
    m = Mundo()
    m.wpp.esperar_recusa = True
    m.armazem[f'u:{m.wa}'] = {'fase': 'pedido'}
    bot = m.Bot(m.ctx)
    bot.wa, bot.u = m.wa, bot._carregar(m.wa)
    bot.perguntar('Escolha:', [('a', 'x' * 30), ('b', 'y')])  # título que não cabe em botão...
    assert m.wpp.saida[-1][0] == 'lista'  # ...vira lista, com o texto inteiro na descrição
    original = m.wpp._real.botoes

    def recusa(*a, **kw):
        from src.shared.whatsapp import ErroWhatsApp
        raise ErroWhatsApp(400, 'Parameter value is not valid')
    m.wpp._real.botoes = recusa
    bot.perguntar('Escolha:', [('a', 'Opção A'), ('b', 'Opção B')])
    m.wpp._real.botoes = original
    tipo, d = m.wpp.saida[-1]
    assert tipo == 'texto' and '1️⃣ Opção A' in d['texto'] and 'número' in d['texto']
    assert bot.u['pergunta']['botoes'][1][0] == 'b'  # o "2" ainda funciona


def test_titulos_unicos_e_limite_utf16():
    from src.shared.whatsapp import tamanho, titulos_unicos
    t = titulos_unicos(['🔎 Buscar outra coisa', 'Casa', 'casa', 'Casa'], 20)
    assert all(tamanho(x) <= 20 for x in t)
    assert len({x.lower() for x in t}) == 4


def test_endereco_invalido_pede_de_novo():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('perto da igreja')
    assert 'Não achei esse endereço' in m.wpp.textos()[-1]
    assert m.estado()['fase'] == 'endereco'


def test_ola_no_endereco_nao_vai_pro_geocoder_e_mostra_botoes():
    m = Mundo()
    m.enviar('quero pao')
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.enviar('Olá')
    assert len(m.mcp.chamadas_de('createAddress')) == antes
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['tentar', 'inicio']
    assert 'endereço' in m.wpp.textos()[-1] and m.estado()['fase'] == 'endereco'


def test_novo_pedido_no_endereco_nao_vai_pro_geocoder_e_mostra_botoes():
    m = Mundo()
    m.enviar('quero pao')
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.enviar('Quero fazer um novo pedido')
    assert len(m.mcp.chamadas_de('createAddress')) == antes
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['tentar', 'inicio']
    assert m.estado()['fase'] == 'endereco'


def test_texto_sem_cara_de_endereco_nao_vai_pro_geocoder():
    m = Mundo()
    m.enviar('quero pao')
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.enviar('não sei')
    assert len(m.mcp.chamadas_de('createAddress')) == antes
    assert 'CEP' in m.wpp.textos()[-1]
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['tentar', 'inicio']
    assert m.estado()['ultima_acao'][0] != 'endereco'  # "Tentar de novo" não reusa o que não foi pro geocoder


def test_endereco_de_verdade_continua_indo_pro_geocoder():
    m = Mundo()
    m.enviar('quero pao')
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.enviar('Rua das Flores, 120, São Carlos')
    assert len(m.mcp.chamadas_de('createAddress')) > antes
    assert m.estado()['ultima_acao'] == ['endereco', 'Rua das Flores, 120, São Carlos']
    assert m.estado().get('falhas_endereco') == 0


def test_duas_falhas_seguidas_no_endereco_mostram_botoes():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('perto da igreja')
    assert m.wpp.saida[-1][0] == 'texto'  # 1ª falha: só o texto, como antes
    m.enviar('perto da padaria')
    tipo, d = m.wpp.saida[-1]
    assert tipo == 'botoes' and 'Não achei esse endereço' in d['texto']
    assert [i for i, _ in d['botoes']] == ['tentar', 'inicio']
    assert m.estado()['fase'] == 'endereco'


# --- sessão ociosa -----------------------------------------------------------------------

def test_sumiu_31_min_no_endereco_e_disse_oi_volta_pro_menu():
    m = Mundo()
    m.enviar('quero pao')
    assert m.estado()['fase'] == 'endereco'
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.wpp.limpar()
    m.agora += 31 * 60
    m.enviar('oi')
    assert len(m.mcp.chamadas_de('createAddress')) == antes
    assert len(m.wpp.saida) == 1  # só o menu, sem resposta dobrada
    assert 'sumiu' in m.wpp.textos()[-1]
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir', 'repetir', 'meu_pedido']
    assert m.estado()['fase'] == 'pedido' and m.estado()['pendente'] is None


def test_sumiu_5_min_no_endereco_continua_sendo_endereco():
    m = Mundo()
    m.enviar('quero pao')
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.agora += 5 * 60
    m.enviar('Rua das Flores, 120, São Carlos')
    assert len(m.mcp.chamadas_de('createAddress')) > antes
    assert 'sumiu' not in ' '.join(m.wpp.textos())


def test_sumiu_2h_no_resumo_nao_apaga_o_carrinho():
    m = pedido_ate_o_resumo(Mundo())
    car_id = m.estado()['carrinho']['id']
    m.wpp.limpar()
    m.agora += 2 * 3600
    m.enviar('oi')
    e = m.estado()
    assert e['fase'] == 'confirmar' and e['carrinho']['id'] == car_id
    assert 'Confira seu pedido' in m.wpp.saida[-1][1]['texto']
    assert not m.mcp.chamadas_de('submitOrder')


def test_estado_antigo_sem_ultima_msg_nao_expira():
    m = Mundo()
    m.enviar('quero pao')
    m.estado()['ultima_msg'] = 0  # salvo antes de existir o campo
    m.agora += 3 * 3600
    antes = len(m.mcp.chamadas_de('createAddress'))
    m.enviar('Rua das Flores, 120, São Carlos')
    assert len(m.mcp.chamadas_de('createAddress')) > antes
    assert 'sumiu' not in ' '.join(m.wpp.textos())


def test_expirar_preserva_login_e_endereco_salvo():
    m = Mundo()
    endereco_pronto(m)
    end = m.estado()['endereco']
    m.enviar('2')  # escolheu o card: agora pergunta a quantidade
    assert m.estado()['fase'] == 'quantidade'
    m.agora += 31 * 60
    m.enviar('oi')
    e = m.estado()
    assert e['fase'] == 'pedido' and e['escolha'] is None
    assert e['endereco'] == end and m.armazem.get(f'tok:{m.wa}')


# --- busca, cards e "mais opções" --------------------------------------------------------

def test_mais_opcoes_reaproveita_a_lista_sem_buscar_de_novo(monkeypatch):
    from src.bot import fluxo
    monkeypatch.setattr(fluxo, 'POR_PAGINA', 3)  # carrossel de 3 pra a lista falsa ter página 2
    m = Mundo()
    endereco_pronto(m)
    buscas = len(m.mcp.chamadas_de('searchOffers'))
    primeiros = [c['botoes'][0][0] for c in m.wpp.cards()]
    m.wpp.limpar()
    m.tocar_lista = None
    m.enviar(('botao', f'mais:{m.estado()["lista_atual"]}'))
    novos = [c['botoes'][0][0] for c in m.wpp.cards()]
    assert len(m.mcp.chamadas_de('searchOffers')) == buscas  # NÃO buscou de novo
    assert [p.split(':')[2] for p in novos] == ['3', '4', '5']  # do índice 3 em diante
    assert not set(primeiros) & set(novos)


def test_busca_manda_vertical_e_localizacao_como_a_doc_pede():
    m = Mundo()
    endereco_pronto(m)
    args = m.mcp.chamadas_de('searchOffers')[0]
    assert args['resultKind'] == 'ITEM' and args['merchantType'] == 'GROCERIES'
    assert set(args['userLocation']) == {'latitude', 'longitude'}
    assert args['query'] == 'pao'


def test_digitar_o_numero_escolhe_o_card():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('2')
    assert m.estado()['fase'] == 'quantidade'
    escolha = m.estado()['escolha']
    assert escolha['oferta']['item_id'] == m.estado()['listas'][m.estado()['lista_atual']]['ofertas'][1]['item_id']


def test_toque_em_varios_cards_vale_o_ultimo():
    m = Mundo()
    endereco_pronto(m)
    lid = m.estado()['lista_atual']
    m.enviar(('botao', f'pick:{lid}:0'), ('botao', f'pick:{lid}:2'))
    of = m.estado()['listas'][lid]['ofertas'][2]
    assert m.estado()['escolha']['oferta']['item_id'] == of['item_id']


def test_botao_de_lista_antiga_responde_sem_quebrar():
    m = Mundo()
    endereco_pronto(m)
    m.enviar(('botao', 'pick:L999:0'))
    assert 'conversa antiga' in ' '.join(m.wpp.textos()[-2:])


# --- rajada de mensagens -----------------------------------------------------------------

def test_rajada_vira_uma_interpretacao_so():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    antes = m.llm.chamadas
    m.enviar('oi', 'quero', 'leite', 'por favor')
    assert m.llm.chamadas == antes + 2  # 1 interpretação pra rajada toda + 1 filtro de relevância da busca
    assert [t for t, _ in m.wpp.saida].count('carrossel') == 1  # uma resposta só: um carrossel do leite


def test_lista_de_compras_faz_um_item_de_cada_vez_na_mesma_loja():
    m = Mundo()
    endereco_pronto(m)  # já mostrou os cards do pão
    m.wpp.limpar()
    m.enviar('quero pao e leite')
    assert 'Anotei sua lista' in ' '.join(m.wpp.textos())
    m.enviar('1')         # escolhe o primeiro pão
    m.tocar('qtd:2')      # 2 pacotes
    # agora busca o leite NA MESMA loja do pão
    ultima = m.mcp.chamadas_de('searchOffers')[-1]
    assert ultima['query'] == 'leite'
    assert ultima['refinements']['merchantId'] == m.estado()['carrinho']['loja_id']


# --- carrinho até o pedido ---------------------------------------------------------------

def pedido_ate_o_resumo(m, cpf='529.982.247-25'):
    endereco_pronto(m)
    m.tocar('pick:')        # "Quero esse" no último card
    m.tocar('qtd:3')
    m.tocar('fim')
    m.tocar('pag:0')        # PIX (vem primeiro; cartão sem token nem aparece)
    m.enviar(cpf)
    return m


def test_pedido_completo_com_resumo_e_confirmacao():
    m = pedido_ate_o_resumo(Mundo())
    e = m.estado()
    assert e['fase'] == 'confirmar'
    resumo = m.wpp.saida[-1][1]['texto']
    assert 'Confira seu pedido' in resumo and 'Total' in resumo and 'PIX' in resumo
    car_id = e['carrinho']['id']
    m.tocar('ok:')
    sub = m.mcp.chamadas_de('submitOrder')
    assert len(sub) == 1 and sub[0]['userConsent'] is True and sub[0]['cartId'] == car_id
    assert sub[0]['document'] == '529.982.247-25'
    assert 'Pedido feito' in ' '.join(m.wpp.textos())
    assert m.rastreios  # começou a acompanhar
    assert m.estado()['carrinho'] is None


def test_toque_duplo_em_confirmar_nao_faz_dois_pedidos():
    m = pedido_ate_o_resumo(Mundo())
    bid = next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('ok:'))
    m.enviar(('botao', bid), ('botao', bid))
    m.enviar(('botao', bid))  # e mais um toque numa rodada depois
    assert len(m.mcp.chamadas_de('submitOrder')) == 1


def test_sim_digitado_no_resumo_confirma():
    m = pedido_ate_o_resumo(Mundo())
    m.enviar('pode sim')
    assert len(m.mcp.chamadas_de('submitOrder')) == 1


def test_sim_fora_do_resumo_nunca_compra():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('sim')
    m.enviar('confirmo')
    assert not m.mcp.chamadas_de('submitOrder')


def test_entrega_padrao_e_pix_escolhidos_sozinhos():
    m = pedido_ate_o_resumo(Mundo())
    assert m.mcp.chamadas_de('setCartDelivery')[0]['deliveryMethodId'] == 'DEFAULT'
    pag = m.mcp.chamadas_de('setCartPayment')[0]
    assert 'cardTokenId' not in pag  # cartão sem token não é oferecido
    # getCartDeliveryMethods veio antes do setCartDelivery (exigência da doc)
    ordem = [t for t, _ in m.mcp.chamadas]
    assert ordem.index('getCartDeliveryMethods') < ordem.index('setCartDelivery') < ordem.index('setCartPayment')


def test_cupom_aplicado_quando_existe():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    m.tocar('pag:0')
    m.tocar('cpf_nao')
    if m.mcp.chamadas_de('setVoucher'):
        assert 'Desconto' in m.wpp.saida[-1][1]['texto']


def test_cpf_errado_pede_de_novo_e_nao_vai_pra_ia():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    m.tocar('pag:0')
    antes = m.llm.chamadas
    m.enviar('123')
    assert 'CPF não parece certo' in m.wpp.saida[-1][1]['texto']
    m.enviar('529 982 247 25')
    assert m.llm.chamadas == antes
    assert m.estado()['fase'] == 'confirmar'


def test_cancelar_limpa_o_pedido():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('cancelar')
    assert m.estado()['carrinho'] is None
    assert not m.mcp.chamadas_de('submitOrder')


def test_tirar_o_unico_item_esvazia_sem_quebrar():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.tocar('tirar')
    m.tocar('rem:0')
    assert m.estado()['carrinho'] is None
    assert 'ficou vazio' in ' '.join(m.wpp.textos())


# --- opções obrigatórias (pizza) ---------------------------------------------------------

def test_pizza_pergunta_o_tamanho_e_monta_options_no_formato_do_carrinho():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('quero uma pizza')
    m.tocar('pick:')
    assert m.estado()['fase'] == 'opcao'
    m.tocar('opt:1')            # grande
    m.tocar('qtd:1')
    criar = m.mcp.chamadas_de('createCart')[-1]
    opts = criar['items'][0]['options']
    assert opts and opts[0]['customizations'] and opts[0]['quantity'] == 1
    assert m.estado()['carrinho']['itens']


# --- depois do pedido --------------------------------------------------------------------

def _ja_pediu_isso_antes(m):
    from src.bot.interpretar import normalizar
    nome = m.estado()['carrinho']['itens'][0]['nome']
    m.armazem[f'hist:{m.wa}'] = {normalizar(nome): {'nome': nome, 'vezes': 1, 'ultima': 0}}


def test_historico_conta_as_compras_e_oferece_lembrete_na_segunda():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    hist = m.armazem[f'hist:{m.wa}']
    assert [h['vezes'] for k, h in hist.items() if not k.startswith('cat:')] == [1]  # 1ª compra: registrou, sem lembrete
    m.wpp.limpar()
    m.enviar('quero pao')  # mesma compra de novo (endereço e CPF já guardados)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    if m.estado()['fase'] == 'pagamento':
        m.tocar('pag:0')
    if m.estado()['fase'] == 'cpf':
        m.enviar('529.982.247-25')
    m.tocar('ok:')
    assert [h['vezes'] for k, h in m.armazem[f'hist:{m.wa}'].items() if not k.startswith('cat:')] == [2]
    assert any(i.startswith('rec:') for i in m.wpp.todos_ids())


def test_apagar_dados_apaga_o_historico():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    m.enviar('apagar meus dados')
    m.tocar('apagar_sim')
    assert f'hist:{m.wa}' not in m.armazem


def test_primeiro_pedido_de_um_item_nao_oferece_lembrete():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    assert not any(i.startswith('rec:') for i in m.wpp.todos_ids())
    assert m.estado()['fase'] == 'acompanhando'


def test_recorrencia_e_pedir_de_novo():
    m = pedido_ate_o_resumo(Mundo())
    _ja_pediu_isso_antes(m)  # lembrete só aparece quando a compra se repete
    m.tocar('ok:')
    m.tocar('rec:7')
    recs = m.ctx.recorrencias._todas(m.wa)
    assert recs and recs[0]['dias'] == 7
    # uma semana depois a pessoa volta e o lembrete aparece
    m.agora += 7 * 86400 + 60
    m.enviar('oi')
    assert any(i.startswith('lem:pedir:') for i in m.wpp.todos_ids()[-3:])
    texto = m.wpp.saida[-1][1]['texto']
    assert 'Podemos pedir aqui pra enviar na sua casa?' in texto and 'PIX' in texto
    origem = m.estado()['pedidos'][0]['id']
    m.tocar('lem:pedir:')  # o "sim" do lembrete é a confirmação: pede na hora, sem resumo de novo
    assert m.mcp.chamadas_de('createCart')[-1] == {'orderId': origem}
    assert len(m.mcp.chamadas_de('submitOrder')) == 2
    assert m.estado()['fase'] == 'acompanhando'
    assert not any(i.startswith('rec:') for i in m.wpp.todos_ids()[-3:])  # já é recorrente


def test_lembrete_com_preco_mais_alto_mostra_resumo_antes():
    m = pedido_ate_o_resumo(Mundo())
    _ja_pediu_isso_antes(m)
    m.tocar('ok:')
    m.tocar('rec:7')
    rec = m.ctx.recorrencias._todas(m.wa)[0]
    m.ctx.recorrencias._mudar(m.wa, rec['id'], total=1.0)  # "da última vez" bem mais barato
    m.agora += 7 * 86400 + 60
    m.enviar('oi')
    m.tocar('lem:pedir:')
    assert len(m.mcp.chamadas_de('submitOrder')) == 1
    assert m.estado()['fase'] == 'confirmar'
    assert 'preço mudou' in m.wpp.saida[-1][1]['texto']


def test_segunda_vez_da_mesma_categoria_oferece_recorrencia():
    m = pedido_ate_o_resumo(Mundo())
    m.armazem[f'hist:{m.wa}'] = {'cat:pão': {'nome': 'pão', 'vezes': 1, 'ultima': 0}}  # outro pão, outra loja
    m.tocar('ok:')
    assert any(i.startswith('rec:') for i in m.wpp.todos_ids())
    assert 'segunda vez de *pão*' in m.wpp.saida[-1][1]['texto']


def test_agendar_no_meio_do_pedido_oferece_depois_que_sai():
    m = pedido_ate_o_resumo(Mundo())
    m.llm.resposta = {'acao': 'agendar', 'numero': 1, 'hora': '18:00', 'resposta': 'não consigo agendar'}
    m.enviar('quero isso todo dia as 18h')
    m.llm.resposta = None
    assert 'todo dia às 18h' in m.wpp.saida[-1][1]['texto']
    assert m.estado()['fase'] == 'confirmar'  # continua no resumo
    m.tocar('ok:')
    assert 'rec:1' in m.wpp.todos_ids()
    m.tocar('rec:1')
    rec = m.ctx.recorrencias._todas(m.wa)[0]
    assert rec['dias'] == 1 and rec['hora'] == '18:00'
    assert (rec['proximo'] - 3 * 3600) % 86400 == 18 * 3600  # amanhã às 18h de Brasília
    assert 'todo dia às 18h' in m.wpp.saida[-1][1]['texto']


def test_modo_demo_lembrete_vence_em_1_minuto():
    m = pedido_ate_o_resumo(Mundo())
    _ja_pediu_isso_antes(m)
    m.armazem['cfg:demo_rapido'] = True
    agendados = []
    m.ctx._agendar_lembrete = lambda wid, quando: agendados.append(quando)
    m.tocar('ok:')
    m.tocar('rec:30')
    assert agendados == [m.agora + 60]
    ok = m.wpp.saida[-1][1]['texto']
    assert 'todo mês' in ok and 'minuto' not in ok and 'demonstra' not in ok  # finge o tempo normal
    m.agora += 61
    m.enviar('oi')
    assert any(i.startswith('lem:pedir:') for i in m.wpp.todos_ids()[-3:])


def test_meu_pedido_mostra_status():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    m.enviar(('botao', 'meu_pedido'))
    assert m.mcp.chamadas_de('trackOrder')


# --- falhas ------------------------------------------------------------------------------

def test_gemini_fora_do_ar_ainda_busca_pelo_texto():
    m = Mundo()
    endereco_pronto(m)
    m.llm.falhar = True
    m.wpp.limpar()
    m.enviar('quero leite integral')
    assert m.wpp.cards()


def test_gemini_fora_do_ar_nao_busca_frase_ao_pe_da_letra():
    m = Mundo()
    endereco_pronto(m)
    m.llm.falhar = True
    m.wpp.limpar()
    m.enviar('nossa hoje ta muito calor aqui viu')
    textos = ' '.join(m.wpp.textos())
    assert 'Não achei' not in textos and 'não entendi' in textos


def test_pedido_minimo_sugere_o_que_a_pessoa_costuma_levar_na_mesma_loja():
    m = Mundo()
    m.armazem[f'hist:{m.wa}'] = {'leite integral': {'nome': 'Leite integral', 'vezes': 3, 'ultima': 1.0}}
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    u = m.armazem[f'u:{m.wa}']
    u['carrinho']['minimo'] = 60.0      # loja com mínimo alto: o pão sozinho não fecha
    m.armazem[f'u:{m.wa}'] = u
    m.tocar('fim')
    assert 'sugerir' in m.wpp.todos_ids()   # 💡 junto do aviso de pedido mínimo
    m.wpp.limpar()
    m.enviar(('botao', 'sugerir'))
    textos = ' '.join(m.wpp.textos())
    assert 'pedido mínimo' in textos and 'Leite integral' in textos and 'costuma' in textos
    busca = m.mcp.chamadas_de('searchOffers')[-1]
    assert busca['query'].lower() == 'leite integral'
    assert busca['refinements']['merchantId'] == m.estado()['carrinho']['loja_id']
    assert m.wpp.cards()


def test_completar_o_valor_sugere_algo_parecido_mesmo_com_o_gemini_fora():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.llm.falhar = True
    m.wpp.limpar()
    m.enviar('sla algo que complete esse valor')
    textos = ' '.join(m.wpp.textos())
    assert 'Não achei' not in textos and 'Separei' in textos and m.wpp.cards()
    est = m.estado()
    no_carrinho = {i['item_id'] for i in est['carrinho']['itens']}
    sugeridas = {o['item_id'] for o in est['listas'][est['lista_atual']]['ofertas']}
    assert sugeridas and not sugeridas & no_carrinho   # parecido, mas não o mesmo pão de novo


def test_pedir_sugestao_de_novo_traz_outra_coisa():
    m = Mundo()
    m.armazem[f'hist:{m.wa}'] = {'leite integral': {'nome': 'Leite integral', 'vezes': 3, 'ultima': 1.0}}
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.enviar('me sugere algo')
    m.enviar('me sugere algo')
    consultas = [c['query'].lower() for c in m.mcp.chamadas_de('searchOffers')[-2:]]
    assert consultas[0] == 'leite integral' and consultas[1] != 'leite integral'


def test_audio_vira_pedido():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar(('audio', 'midia1'))
    assert m.wpp.cards()


def test_audio_transcrito_pelo_scribe_segue_igual_texto():
    ouvidos = []
    m = Mundo(transcritor=lambda mime, dados: ouvidos.append(mime) or 'quero leite integral')
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar(('audio', 'midia1'))
    assert ouvidos == ['audio/ogg']                                    # baixou e mandou pro Scribe
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'leite'   # buscou o que foi dito
    assert m.wpp.cards()


def test_scribe_fora_do_ar_o_gemini_ouve_o_audio():
    def surdo(mime, dados):
        raise RuntimeError('scribe fora do ar')
    m = Mundo(transcritor=surdo)
    endereco_pronto(m)
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.wpp.limpar()
    m.enviar(('audio', 'midia1'))
    buscas = m.mcp.chamadas_de('searchOffers')
    assert len(buscas) == antes + 1 and buscas[-1]['query'] == 'pao'  # o "áudio" do fake fala pão
    assert m.wpp.cards()


def test_cpf_falado_nao_vai_pro_scribe():
    ouvidos = []
    m = Mundo(transcritor=lambda mime, dados: ouvidos.append(mime) or '529.982.247-25')
    m.armazem[f'u:{m.wa}'] = {**(m.armazem.get(f'u:{m.wa}') or {}), 'fase': 'cpf'}
    m.enviar(('audio', 'midia1'))
    assert not ouvidos and 'escreva o CPF' in ' '.join(m.wpp.textos())


def test_fora_do_escopo_volta_pro_pedido():
    m = Mundo()
    m.enviar('me conta uma piada')
    textos = ' '.join(m.wpp.textos())
    assert '[fala]' in textos and 'O que você quer pedir' in textos  # responde como gente e volta pro pedido


def test_palavra_secreta_desloga_e_reseta_em_qualquer_etapa(monkeypatch):
    monkeypatch.setenv('DEBUG_RESET', 'deslogarnoifood6767')
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')              # no meio de um pedido (etapa 'quantidade')
    assert m.armazem.get(f'tok:{m.wa}')
    antes = m.llm.chamadas
    m.enviar('DeslogarNoIfood6767')   # com maiúsculas, pra testar a normalização
    assert f'tok:{m.wa}' not in m.armazem          # deslogou do iFood
    assert m.estado().get('fase') == 'inicio'       # conversa zerada
    assert m.estado().get('carrinho') is None
    assert m.llm.chamadas == antes                  # nem passou pela IA
    assert '[debug]' in ' '.join(m.wpp.textos())


def test_sem_a_env_a_palavra_e_mensagem_normal():
    m = Mundo()  # DEBUG_RESET não está no ambiente
    endereco_pronto(m)
    m.enviar('deslogarnoifood6767')
    assert m.armazem.get(f'tok:{m.wa}')             # não deslogou
    assert '[debug]' not in ' '.join(m.wpp.textos())


def test_apagar_dados():
    m = pedido_ate_o_resumo(Mundo())
    m.enviar('apagar meus dados')
    m.tocar('apagar_sim')
    assert f'u:{m.wa}' not in m.armazem and f'tok:{m.wa}' not in m.armazem


# --- botões que não cabem e nomes sujos da loja (bug real de 17/10 18h08) ------------------

def test_limpar_tira_hashtag_e_marcacao_do_whatsapp():
    from src.shared.whatsapp import limpar
    assert limpar('Não desejo sachês #######') == 'Não desejo sachês'
    assert limpar('**Pão** de _queijo_ ~~top~~') == 'Pão de queijo top'
    assert limpar('Molho (###)') == 'Molho'
    assert limpar('X-Burguer #1') == 'X-Burguer #1'  # # com número é nome de verdade


def test_partir_manda_o_parentese_pro_detalhe_e_corta_na_palavra():
    from src.shared.whatsapp import partir
    assert partir('Sim, desejo sachês (maionese, kethchup e mostarda)', 20) == \
        ('Sim, desejo sachês', 'maionese, kethchup e mostarda', False)
    curto, resto, cortou = partir('Refrigerante lata trezentos e cinquenta', 20)
    assert cortou and curto == 'Refrigerante lata…' and resto.startswith('Refrigerante lata trezentos')
    assert partir('Curto', 20) == ('Curto', '', False)


def test_opcoes_dos_saches_viram_botoes_inteiros_com_detalhe_no_texto():
    m = Mundo()
    m.armazem[f'u:{m.wa}'] = {'fase': 'pedido'}
    bot = m.Bot(m.ctx)
    bot.wa, bot.u = m.wa, bot._carregar(m.wa)
    bot.perguntar('Escolha: *Deseja sachês?* 👇',
                  [('opt:0', 'Sim, desejo sachês (maionese, kethchup e mostarda)'), ('opt:1', 'Não desejo sachês')])
    tipo, d = m.wpp.saida[-1]
    assert tipo == 'botoes'
    assert [t for _, t in d['botoes']] == ['Sim, desejo sachês', 'Não desejo sachês']
    assert 'maionese, kethchup e mostarda' in d['texto']
    assert bot.u['pergunta']['titulos'][0].startswith('Sim, desejo sachês (')  # digitar o nome inteiro ainda vale


# --- carrossel ------------------------------------------------------------------------------

def test_ofertas_vao_num_carrossel_com_foto_e_quero_esse_em_todo_card():
    m = Mundo()
    endereco_pronto(m)
    (tipo, d), = [(t, x) for t, x in m.wpp.saida if t == 'carrossel']
    assert 'Arraste' in d['texto']
    assert all(c['imagem'].startswith('https://') and c['botoes'][0][1] == 'Quero esse' for c in d['cards'])
    m.tocar(d['cards'][1]['botoes'][0][0])  # tocar no 2º card escolhe o 2º produto
    assert m.estado()['fase'] in ('quantidade', 'opcao', 'mais')


def test_meta_recusou_carrossel_volta_pros_3_cards_soltos():
    m = Mundo()
    original = m.wpp._real.carrossel

    def recusa(*a, **kw):
        from src.shared.whatsapp import ErroWhatsApp
        raise ErroWhatsApp(400, 'carousel not supported')
    m.wpp._real.carrossel = recusa
    endereco_pronto(m)
    m.wpp._real.carrossel = original
    assert len(m.wpp.cards()) == 3 and all(t != 'carrossel' for t, _ in m.wpp.saida)

# --- atendente que explica (Gemini) ---------------------------------------------------------

def _ifood_cai(m):
    from src.shared.ifood_mcp import ErroMCP
    original = m.mcp.chamar

    def chamar(tool, **a):
        if tool == 'searchOffers':
            raise ErroMCP('HTTP_403', 'Access Denied')
        return original(tool, **a)
    m.mcp.chamar = chamar


def test_ifood_fora_do_ar_vira_explicacao_do_tutor_e_marca_instavel():
    m = Mundo()
    endereco_pronto(m)
    _ifood_cai(m)
    m.wpp.limpar()
    m.enviar('quero leite')
    tipo, d = m.wpp.saida[-1]
    assert '[tutor]' in d['texto'] and [i for i, _ in d['botoes']] == ['tentar', 'inicio']
    assert m.armazem.get('ifood_instavel')


def test_vc_ta_ai_com_ifood_instavel_responde_como_gente():
    m = Mundo()
    endereco_pronto(m)
    m.armazem['ifood_instavel'] = m.agora
    m.wpp.limpar()
    m.enviar('oi vc ta ai?')
    assert '[fala] Tô aqui sim' in m.wpp.textos()[-1]


def test_fora_do_assunto_usa_a_fala_do_gemini_e_volta_pro_pedido():
    m = Mundo()
    m.enviar('me conta uma piada')
    assert '[fala] Haha' in m.wpp.textos()[-1]


def test_tutor_fora_do_ar_volta_pro_texto_fixo():
    from src.bot import textos as T
    m = Mundo()
    endereco_pronto(m)
    _ifood_cai(m)
    m.llm.resposta = None
    original = m.llm.__call__

    def so_interpreta(s, p, e):
        if 'acao' not in e['properties']:
            from src.shared.llm import ErroLLM
            raise ErroLLM('fora')
        return original(s, p, e)
    m.ctx._gerar_json = so_interpreta
    m.wpp.limpar()
    m.enviar('quero leite')
    assert T.ERRO.split('\n')[0] in m.wpp.textos()[-1]


# --- busca precisa (cebola não é salgadinho de cebola) ---------------------------------------

def test_busca_vai_pro_ifood_desambiguada_e_cai_pro_termo_se_nao_achar():
    m = Mundo()
    endereco_pronto(m)
    m.llm.resposta = {'acao': 'comprar', 'itens': [{'termo': 'leite', 'busca': 'leite in natura xyz',
                                                    'tipo_loja': 'MERCADO'}]}
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar('quero leite')
    consultas = [c['query'] for c in m.mcp.chamadas_de('searchOffers')[antes:]]
    assert consultas[0] == 'leite in natura xyz'  # 1º a busca precisa do Gemini
    if len(consultas) > 1:
        assert consultas[1] == 'leite'           # nada? tenta o termo puro
    assert m.wpp.cards()


def test_loja_que_exige_cpf_pede_o_cpf_sem_opcao_de_pular():
    """Bug real 17/10 19h: MERCH-007 virava "Tentar de novo" e a pessoa batia 3x no mesmo erro."""
    from src.shared.ifood_mcp import ErroMCP
    m = pedido_ate_o_resumo(Mundo(), cpf='nao')
    original, vezes = m.mcp.chamar, []

    def chamar(tool, **a):
        if tool == 'submitOrder' and not vezes:
            vezes.append(1)
            raise ErroMCP('MERCH-007', 'MERCH-007: Este restaurante obriga a digitação do CPF.')
        return original(tool, **a)
    m.mcp.chamar = chamar
    m.tocar('ok:')
    assert m.estado()['fase'] == 'cpf' and 'CPF na nota' in m.wpp.textos()[-1]
    assert 'cpf_nao' not in [i for i, _ in m.wpp.ultimos_botoes()]
    m.enviar('nao')  # insistir em "sem CPF" não volta pro erro
    assert m.estado()['fase'] == 'cpf'
    m.enviar('529.982.247-25')
    assert m.estado()['cpf'] == '52998224725'
