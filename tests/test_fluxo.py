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
    assert len(m.wpp.cards()) == 3  # já buscou o pão depois de salvar o endereço
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
    bot.perguntar('Escolha:', [('a', 'x' * 30), ('b', 'y')])  # força: título enorme passa pelo corte...
    assert m.wpp.saida[-1][0] == 'botoes'  # ...e o corte resolve sozinho
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


# --- busca, cards e "mais opções" --------------------------------------------------------

def test_mais_opcoes_reaproveita_a_lista_sem_buscar_de_novo():
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
    assert m.llm.chamadas == antes + 1
    assert sum(1 for c in m.wpp.cards()) == 3  # uma resposta só: os 3 cards do leite


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

def test_recorrencia_e_pedir_de_novo():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    m.tocar('rec:7')
    recs = m.ctx.recorrencias._todas(m.wa)
    assert recs and recs[0]['dias'] == 7
    # uma semana depois a pessoa volta e o lembrete aparece
    m.agora += 7 * 86400 + 60
    m.enviar('oi')
    assert any(i.startswith('lem:pedir:') for i in m.wpp.todos_ids()[-3:])
    m.tocar('lem:pedir:')
    assert m.mcp.chamadas_de('createCart')[-1] == {'orderId': m.estado()['pedidos'][0]['id']}
    assert m.estado()['fase'] == 'confirmar'


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


def test_audio_vira_pedido():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar(('audio', 'midia1'))
    assert m.wpp.cards()


def test_fora_do_escopo_volta_pro_pedido():
    m = Mundo()
    m.enviar('me conta uma piada')
    assert 'só sei fazer pedidos' in ' '.join(m.wpp.textos())


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
