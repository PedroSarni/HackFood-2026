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
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir']   # sem pedido nem histórico, sem atalho


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


def _salvos(m):
    """Chamadas do createAddress que SALVAM (o passo 2, com candidateId); o passo 1 só geocodifica."""
    return [c for c in m.mcp.chamadas_de('createAddress') if c.get('candidateId')]


def test_ola_no_complemento_nao_salva_e_mostra_nao_tem():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    assert m.estado()['fase'] == 'complemento'
    m.enviar('Olá')
    assert not _salvos(m)
    assert m.estado()['fase'] == 'complemento'
    assert 'compl_nao' in [i for i, _ in m.wpp.ultimos_botoes()]


def test_apto_no_complemento_continua_salvando():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.enviar('apto 12')
    assert _salvos(m)[-1]['complement'] == 'Apto 12'  # padronizado (src/bot/interpretar.py, so_complemento)


def test_ola_no_bairro_nao_salva():
    m = Mundo()
    m.enviar('quero leite')
    m.enviar('Rua Sem Bairro, 55, São Carlos')
    assert m.estado()['fase'] == 'bairro'
    m.enviar('Olá')
    assert m.estado()['fase'] == 'bairro'
    assert (m.estado().get('novo_endereco') or {}).get('bairro') is None
    assert not _salvos(m)


def _ate_o_complemento(m):
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    assert m.estado()['fase'] == 'complemento'


def test_cancelar_no_complemento_cancela_e_nao_salva():
    m = Mundo()
    _ate_o_complemento(m)
    m.enviar('cancelar')
    assert not _salvos(m)
    assert m.estado()['fase'] == 'pedido' and m.estado()['pendente'] is None


def test_menu_no_complemento_vai_pro_menu():
    m = Mundo()
    _ate_o_complemento(m)
    m.enviar('menu')
    assert not _salvos(m)
    assert m.estado()['fase'] == 'pedido'
    assert 'pedir' in [i for i, _ in m.wpp.ultimos_botoes()]


def test_cancelar_no_bairro_nao_salva():
    m = Mundo()
    m.enviar('quero leite')
    m.enviar('Rua Sem Bairro, 55, São Carlos')
    assert m.estado()['fase'] == 'bairro'
    m.enviar('cancelar')
    assert not _salvos(m)
    assert m.estado()['fase'] == 'pedido'
    assert (m.estado().get('novo_endereco') or {}).get('bairro') is None


def test_nao_tem_no_complemento_continua_sem_complemento():
    m = Mundo()
    _ate_o_complemento(m)
    m.enviar('não tem')
    assert _salvos(m) and not _salvos(m)[-1].get('complement')  # salvou, sem complemento


def test_novo_pedido_no_complemento_nao_salva():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.enviar('Quero fazer um novo pedido')
    assert not _salvos(m)
    assert m.estado()['fase'] == 'complemento'
    assert 'compl_nao' in [i for i, _ in m.wpp.ultimos_botoes()]


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
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir']
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


# --- follow-up de quem calou -------------------------------------------------------------

def _followup(m):
    """O que o src/app.py faz: pega a marca no fim da rodada, dorme FOLLOWUP_SEG e chama o follow-up."""
    from src.bot.fluxo import FOLLOWUP_SEG
    bot = m.Bot(m.ctx)
    bot.wa, bot.u = m.wa, bot._carregar(m.wa)
    marca = bot.marca_followup()
    m.agora += FOLLOWUP_SEG
    return marca, (m.Bot(m.ctx).followup(m.wa, marca) if marca else False)


def test_calou_3_min_no_endereco_recebe_followup_com_a_pergunta():
    m = Mundo()
    m.enviar('quero pao')
    m.wpp.limpar()
    marca, mandou = _followup(m)
    assert marca and mandou
    texto = m.wpp.textos()[-1]
    assert 'Ainda está por aí?' in texto and 'Pra onde eu mando' in texto
    assert m.wpp.ultimos_botoes()  # pergunta com botão, não texto solto


def test_respondeu_antes_do_followup_nada_sai():
    m = Mundo()
    m.enviar('quero pao')
    bot = m.Bot(m.ctx)
    bot.wa, bot.u = m.wa, bot._carregar(m.wa)
    marca = bot.marca_followup()
    m.agora += 60
    m.enviar('Rua das Flores, 120, São Carlos')  # respondeu: ultima_msg mudou
    m.wpp.limpar()
    assert m.Bot(m.ctx).followup(m.wa, marca) is False
    assert not m.wpp.saida


def test_segundo_followup_pra_mesma_mensagem_nao_sai():
    m = Mundo()
    m.enviar('quero pao')
    marca, mandou = _followup(m)
    assert mandou
    m.wpp.limpar()
    assert m.Bot(m.ctx).followup(m.wa, marca) is False
    assert not m.wpp.saida


def test_fases_sem_pergunta_de_etapa_nao_recebem_followup():
    for fase in ('pedido', 'login', 'cpf', 'acompanhando'):
        m = Mundo()
        m.enviar('bom dia')  # menu: fase pedido, com botões e ultima_msg
        m.estado()['fase'] = fase
        m.wpp.limpar()
        marca, mandou = _followup(m)
        assert marca is None and mandou is False, fase
        assert not m.wpp.saida, fase


def test_followup_no_resumo_so_repete_o_resumo_e_nao_confirma():
    m = pedido_ate_o_resumo(Mundo())
    car_id = m.estado()['carrinho']['id']
    m.wpp.limpar()
    marca, mandou = _followup(m)
    assert mandou
    tipo, d = m.wpp.saida[-1]
    assert 'Ainda está por aí?' in d['texto'] and 'Confira seu pedido' in d['texto']
    assert any(i.startswith('ok:') for i, _ in d['botoes'])
    assert not m.mcp.chamadas_de('submitOrder')
    assert m.estado()['fase'] == 'confirmar' and m.estado()['carrinho']['id'] == car_id


def test_followup_nao_mexe_em_ultima_msg_fase_nem_pergunta():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('2')  # quantidade: pergunta com botões
    antes = {k: m.estado()[k] for k in ('ultima_msg', 'fase', 'pergunta')}
    marca, mandou = _followup(m)
    assert mandou
    depois = {k: m.estado()[k] for k in ('ultima_msg', 'fase', 'pergunta')}
    assert depois == antes and m.estado()['followup_de'] == marca


# --- carrinho abandonado (5 min calada) --------------------------------------------------

def _carrinho_no_o_que_mais(m):
    """Item no carrinho e a pergunta aberta "O que mais você quer?" (fase pedido)."""
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.tocar('add')
    assert m.estado()['fase'] == 'pedido' and m.estado()['carrinho']['itens']


def _abandono(m, marca=None):
    """O que o src/app.py faz aos ABANDONO_SEG."""
    from src.bot.fluxo import ABANDONO_SEG
    marca = marca or m.estado()['ultima_msg']
    m.agora += ABANDONO_SEG
    return m.Bot(m.ctx).abandonar_carrinho(m.wa, marca)


def test_calada_5_min_com_carrinho_esquece_e_volta_pro_menu():
    m = Mundo()
    _carrinho_no_o_que_mais(m)
    m.wpp.limpar()
    assert _abandono(m) is True
    e = m.estado()
    assert e['carrinho'] is None and e['fase'] == 'pedido'
    assert 'Esvaziei seu carrinho' in m.wpp.textos()[-1]
    assert 'pedir' in [i for i, _ in m.wpp.ultimos_botoes()]


def test_falou_antes_do_abandono_nada_acontece():
    m = Mundo()
    _carrinho_no_o_que_mais(m)
    marca = m.estado()['ultima_msg']
    m.agora += 60
    m.enviar('quero leite')  # falou: ultima_msg mudou
    m.wpp.limpar()
    assert _abandono(m, marca) is False
    assert m.estado()['carrinho']['itens'] and not m.wpp.saida


def test_sem_itens_no_carrinho_nao_abandona():
    m = Mundo()
    m.enviar('quero pao')
    m.wpp.limpar()
    assert _abandono(m) is False
    assert not m.wpp.saida


def test_resumo_calado_esquece_e_sim_depois_nao_confirma():
    m = pedido_ate_o_resumo(Mundo())
    assert m.estado()['fase'] == 'confirmar'
    assert _abandono(m) is True
    assert m.estado()['carrinho'] is None and m.estado()['fase'] == 'pedido'
    m.enviar('sim')
    assert not m.mcp.chamadas_de('submitOrder')


def test_segundo_abandono_com_a_mesma_marca_nao_faz_nada():
    m = Mundo()
    _carrinho_no_o_que_mais(m)
    marca = m.estado()['ultima_msg']
    assert _abandono(m, marca) is True
    m.wpp.limpar()
    assert m.Bot(m.ctx).abandonar_carrinho(m.wa, marca) is False
    assert not m.wpp.saida


def test_abandono_nao_chama_o_ifood_e_nao_mexe_em_ultima_msg():
    m = Mundo()
    _carrinho_no_o_que_mais(m)
    marca = m.estado()['ultima_msg']
    chamadas = len(m.mcp.chamadas)
    assert _abandono(m, marca) is True
    assert len(m.mcp.chamadas) == chamadas  # só esquece o carrinho local
    assert m.estado()['ultima_msg'] == marca


def test_marca_followup_vale_no_pedido_so_com_itens():
    m = Mundo()
    _carrinho_no_o_que_mais(m)
    bot = m.Bot(m.ctx)
    bot.wa, bot.u = m.wa, bot._carregar(m.wa)
    assert bot.marca_followup() == m.estado()['ultima_msg']
    m2 = Mundo()
    m2.enviar('bom dia')  # menu: fase pedido, sem carrinho
    bot2 = m2.Bot(m2.ctx)
    bot2.wa, bot2.u = m2.wa, bot2._carregar(m2.wa)
    assert bot2.u['fase'] == 'pedido' and bot2.marca_followup() is None


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


def test_sim_digitado_no_resumo_com_sugestao_pergunta_de_novo_e_so_o_toque_fecha():
    m = pedido_ate_o_resumo(Mundo())
    assert 'pra acompanhar' in m.estado()['pergunta']['texto']   # o resumo também oferece a manteiga
    m.enviar('pode sim')
    assert not m.mcp.chamadas_de('submitOrder')
    assert [t for _, t in m.wpp.ultimos_botoes()] == ['✅ Fazer pedido assim', '➕ Colocar manteiga', '✏️ Mudar']
    m.tocar('ok:')
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


def test_cancelar_pedido_sem_carrinho_volta_pro_menu():
    m = Mundo()
    m.enviar('bom dia')
    assert m.estado()['fase'] == 'pedido'
    m.wpp.limpar()
    antes = m.llm.chamadas
    m.enviar('cancelar pedido')
    assert m.llm.chamadas == antes  # comando resolvido sem o Gemini (o real buscava como produto)
    assert m.estado()['fase'] == 'pedido' and m.estado()['carrinho'] is None
    assert 'pedir' in [i for i, _ in m.wpp.ultimos_botoes()]
    assert 'Não achei' not in ' '.join(m.wpp.textos())  # não buscou "cancelar pedido" como produto


def test_quero_cancelar_com_carrinho_cancela_o_carrinho():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    assert (m.estado()['carrinho'] or {}).get('itens')
    m.enviar('quero cancelar')
    assert m.estado()['carrinho'] is None
    assert not m.mcp.chamadas_de('submitOrder')


def test_quero_leite_continua_sendo_compra():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar('quero leite')
    assert m.wpp.cards()  # buscou o leite


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


def test_pedido_minimo_sugere_o_que_acompanha_na_mesma_loja():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')            # pão sírio do Supermercado Central, que no mock pede R$ 25
    m.tocar('qtd:1')
    m.tocar('fim')
    assert 'sugerir' in m.wpp.todos_ids()   # 💡 junto do aviso de pedido mínimo
    m.wpp.limpar()
    m.enviar(('botao', 'sugerir'))
    textos = ' '.join(m.wpp.textos())
    assert 'pedido mínimo' in textos and 'manteiga' in textos and 'pra acompanhar' in textos
    busca = m.mcp.chamadas_de('searchOffers')[-1]
    assert busca['query'] == 'manteiga'
    assert busca['refinements']['merchantId'] == m.estado()['carrinho']['loja_id']
    assert m.wpp.cards()


def test_lanche_ganha_sugestao_de_refri_e_o_que_fecha_o_minimo_vem_primeiro():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('quero um x burger')
    xburger = next(c for c in m.wpp.cards() if c['texto'].startswith('*X-Burger*'))  # a Burger House também tem burger
    m.enviar(('botao', xburger['botoes'][0][0]))
    m.tocar('qtd:1')
    m.tocar('fim')              # X-Burger R$ 22,90 e a lanchonete pede R$ 30: faltam R$ 7,10
    m.wpp.limpar()
    m.enviar(('botao', 'sugerir'))
    textos = ' '.join(m.wpp.textos())
    assert 'refrigerante' in textos and 'pra acompanhar' in textos
    est = m.estado()
    assert est['listas'][est['lista_atual']]['ofertas'][0]['nome'] == 'Refrigerante 600 ml'


def test_farmacia_nao_empurra_remedio_e_sugere_o_que_a_pessoa_costuma_levar():
    m = Mundo()
    m.armazem[f'hist:{m.wa}'] = {'fralda geriatrica g': {'nome': 'Fralda geriátrica G', 'vezes': 2, 'ultima': 1.0}}
    endereco_pronto(m)
    m.enviar('quero dipirona')
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.wpp.limpar()
    m.enviar('me sugere algo')
    busca = m.mcp.chamadas_de('searchOffers')[-1]
    assert busca['query'].lower() == 'fralda geriátrica' and 'costuma' in ' '.join(m.wpp.textos())


def test_completar_o_valor_sugere_algo_parecido_mesmo_com_o_gemini_fora():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.llm.falhar = True
    m.wpp.limpar()
    m.enviar('sla algo que complete esse valor')
    textos = ' '.join(m.wpp.textos())
    assert 'Não achei' not in textos and ('pra acompanhar' in textos or 'Separei' in textos)
    assert m.wpp.cards()
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
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar('me sugere algo')
    meio = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar('me sugere algo')
    buscas = [c['query'].lower() for c in m.mcp.chamadas_de('searchOffers')]
    primeira, segunda = set(buscas[antes:meio]), set(buscas[meio:])
    assert primeira and segunda and not primeira & segunda   # cada toque traz outra coisa


def test_carrinho_do_ifood_real_e_largado_quando_o_mock_liga():
    m = Mundo()
    endereco_pronto(m)
    u = m.armazem[f'u:{m.wa}']
    u['carrinho'] = {'id': 'cart-real', 'loja_id': 'loja-do-ifood-real', 'loja': 'Nissei Mercado - 431',
                     'itens': [{'item_id': 'x', 'nome': 'Leite', 'qtd': 1}], 'subtotal': 5.0}
    m.armazem[f'u:{m.wa}'] = u
    m.enviar('quero leite')
    busca = m.mcp.chamadas_de('searchOffers')[-1]
    assert 'merchantId' not in (busca.get('refinements') or {})   # não fica preso no Nissei
    assert m.wpp.cards() and not m.estado()['carrinho']


def test_pedido_no_meio_do_endereco_muda_de_funcao_e_vira_o_pendente():
    m = Mundo()
    m.enviar('quero pao')                                    # sem endereço: o bot pede o endereço
    m.wpp.limpar()
    m.enviar('oi eu quero comer uma pizza e uma coca de 2')  # tem número, mas é pedido, não endereço
    assert not m.mcp.chamadas_de('createAddress')
    textos = ' '.join(m.wpp.textos())
    assert 'Anotei' in textos and 'pizza' in textos and 'Pra onde eu mando' in textos
    assert m.estado()['fase'] == 'endereco' and m.estado()['pendente']['itens'][0]['termo'] == 'pizza'
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.tocar('compl_nao')
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'pizza'   # retomou o pedido novo, não o pão


def test_nao_tem_escrito_no_complemento_e_sem_complemento():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.enviar('não tem')
    assert not m.mcp.chamadas_de('createAddress')[-1].get('complement')


def test_pedido_no_complemento_anota_e_pergunta_o_complemento_de_novo():
    m = Mundo()
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.wpp.limpar()
    m.enviar('quero uma pizza tambem')
    assert m.estado()['fase'] == 'complemento' and m.estado()['pendente']['itens'][0]['termo'] == 'pizza'
    assert 'Anotei' in ' '.join(m.wpp.textos())


def test_sem_numero_no_cpf_nao_e_cpf_invalido_e_segue_o_fluxo():
    from src.bot import textos as T
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    m.tocar('pag:0')                # PIX: agora o bot pede o CPF
    assert m.estado()['fase'] == 'cpf'
    m.wpp.limpar()
    m.enviar('cancelar')
    assert T.CPF_INVALIDO not in ' '.join(m.wpp.textos()) and not m.estado()['carrinho']


def test_meu_pedido_e_pedir_de_novo_so_aparecem_quando_levam_a_algo():
    m = Mundo()
    m.enviar('bom dia')
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir']
    u = m.armazem[f'u:{m.wa}']
    u['pedidos'] = [{'id': 'p1', 'resumo': '1x Pão francês'}]
    m.armazem[f'u:{m.wa}'] = u
    m.enviar('bom dia')
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir', 'repetir', 'meu_pedido']


def test_pedido_que_este_ifood_nao_conhece_sai_da_lista_sem_ingles_na_tela():
    m = Mundo()
    u = m.armazem.get(f'u:{m.wa}') or {}
    u['pedidos'] = [{'id': 'pedido-do-ifood-real', 'resumo': '1x Pizza'}]
    m.armazem[f'u:{m.wa}'] = u
    m.enviar(('botao', 'meu_pedido'))
    textos = ' '.join(m.wpp.textos())
    assert 'Do not' not in textos and 'Order' not in textos
    assert not m.estado()['pedidos'] and 'meu_pedido' not in [i for i, _ in m.wpp.ultimos_botoes()]


def test_papo_no_endereco_sem_endereco_nenhum_responde_e_pede_de_novo():
    m = Mundo()
    m.enviar('quero pao')
    m.llm.resposta = {'acao': 'endereco', 'texto': None, 'resposta': 'Nem me fale, tá quente! 🥵'}
    m.wpp.limpar()
    m.enviar('nossa que calor que ta fazendo hoje')
    m.llm.resposta = None
    assert not m.mcp.chamadas_de('createAddress')
    textos = ' '.join(m.wpp.textos())
    assert 'quente' in textos and 'Pra onde eu mando' in textos and m.estado()['fase'] == 'endereco'


def test_todo_dia_com_itens_monta_o_modelo_do_que_foi_dito_e_nao_pede_agora():
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar('todo dia as 7h quero pao')
    textos = ' '.join(m.wpp.textos())
    assert 'automático' in textos and 'nada é pedido hoje' in textos and m.wpp.cards()  # buscou o pão dito
    m.tocar('pick:')
    m.tocar('qtd:3')               # 3 pacotes passam do mínimo da loja
    m.tocar('fim')
    assert not m.mcp.chamadas_de('submitOrder')                         # nada foi pedido agora
    rec = m.recs_dic[m.wa][0]
    assert rec['itens'] and rec['hora'] == '07:00' and rec['dias'] == 1 and not rec['pedido_id']
    assert 'Combinado' in m.wpp.textos()[-1] and not m.estado()['carrinho']


def test_lembrete_do_modelo_monta_o_carrinho_com_os_itens_guardados():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('todo dia as 7h quero pao')
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    rec = m.recs_dic[m.wa][0]
    m.enviar(('botao', f'lem:pedir:{rec["id"]}'))
    cria = m.mcp.chamadas_de('createCart')[-1]
    assert cria.get('merchantId') and cria['items'][0]['quantity'] == 3 and 'orderId' not in cria


def test_automatico_sem_dizer_o_que_oferece_o_ultimo_pedido_sem_o_papo_de_segunda_vez():
    m = Mundo()
    u = m.armazem.get(f'u:{m.wa}') or {}
    u['pedidos'] = [{'id': 'p1', 'resumo': '1x X-Salada'}]
    m.armazem[f'u:{m.wa}'] = u
    m.enviar('deixa no automatico todo dia as 9h')
    texto = m.wpp.textos()[-1]
    assert 'segunda vez' not in texto and 'X-Salada' in texto and 'todo dia às 9h' in texto


def test_terceira_compra_do_mesmo_item_nao_insiste_no_automatico():
    from src.bot.interpretar import normalizar
    m = pedido_ate_o_resumo(Mundo())
    nome = m.estado()['carrinho']['itens'][0]['nome']
    m.armazem[f'hist:{m.wa}'] = {normalizar(nome): {'nome': nome, 'vezes': 2, 'ultima': 0}}
    m.tocar('ok:')                 # 3ª compra: já ofereceu na 2ª
    assert not any(i.startswith('rec:') for i in m.wpp.todos_ids())


def test_nao_precisa_segura_a_oferta_por_uma_semana():
    m = pedido_ate_o_resumo(Mundo())
    _ja_pediu_isso_antes(m)
    m.tocar('ok:')                 # 2ª compra: oferece
    assert any(i.startswith('rec:') for i in m.wpp.todos_ids())
    m.tocar('rec:0')               # "Não precisa"
    assert m.estado()['rec_pausa_ate'] > m.agora


def test_com_pausa_a_segunda_compra_nao_oferece():
    m = pedido_ate_o_resumo(Mundo())
    _ja_pediu_isso_antes(m)
    u = m.armazem[f'u:{m.wa}']
    u['rec_pausa_ate'] = m.agora + 3600
    m.armazem[f'u:{m.wa}'] = u
    m.tocar('ok:')
    assert not any(i.startswith('rec:') for i in m.wpp.todos_ids())


def test_cancelar_o_pedido_cancela_mesmo_com_o_gemini_fora():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')
    m.llm.falhar = True
    m.wpp.limpar()
    m.enviar('cancelar o pediod')
    assert 'Não achei' not in ' '.join(m.wpp.textos()) and not m.estado()['carrinho']


def test_sem_gemini_tira_o_quero_jantar_hj_e_busca_pizza_no_restaurante():
    m = Mundo()
    endereco_pronto(m)
    m.llm.falhar = True
    m.enviar('quero jantar pizza hj')
    busca = m.mcp.chamadas_de('searchOffers')[-1]
    assert busca['query'] == 'pizza' and busca['merchantType'] == 'RESTAURANT'


def test_quero_esse_e_pode_fechar_adiciona_sem_perguntar_e_vai_pro_checkout():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('quero um x burger')                          # 1 card só: X-Burger da lanchonete
    m.wpp.limpar()
    m.llm.resposta = {'acao': 'escolher', 'fechar': True, 'itens': [
        {'termo': 'x-burger', 'busca': 'x-burger', 'tipo_loja': 'RESTAURANTE', 'quantidade': 2}]}
    m.enviar('eu quero dois desse ja pode adicionar ao carrinho e fechar')
    m.llm.resposta = None
    ids = m.wpp.todos_ids()
    assert not any(i.startswith('qtd:') for i in ids)                  # não perguntou quantidade
    assert m.estado()['carrinho']['itens'][0]['qtd'] == 2
    assert 'Quer mais alguma coisa' not in ' '.join(m.wpp.textos())    # foi direto pro checkout
    assert any(i.startswith(('pag:', 'ok:')) for i in ids)


def test_pagamento_dito_pula_a_pergunta_e_o_resumo_sugere_o_que_acompanha():
    m = Mundo()
    endereco_pronto(m)
    u = m.armazem[f'u:{m.wa}']
    u['cpf'] = '52998224725'
    m.armazem[f'u:{m.wa}'] = u
    m.enviar('quero um x burger')
    m.wpp.limpar()
    m.llm.resposta = {'acao': 'escolher', 'fechar': True, 'pagamento': 'PIX', 'itens': [
        {'termo': 'x-burger', 'busca': 'x-burger', 'tipo_loja': 'RESTAURANTE', 'quantidade': 2}]}
    m.enviar('quero dois desse, pode fechar, vou pagar no pix')
    m.llm.resposta = None
    ids = m.wpp.todos_ids()
    assert not any(i.startswith('pag:') for i in ids) and any(i.startswith('ok:') for i in ids)
    assert 'pra acompanhar' in ' '.join(m.wpp.textos())


def test_a_de_calabresa_grande_escolhe_pelo_nome_e_pelo_tamanho_falados():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('quero pizza')
    m.llm.resposta = {'acao': 'escolher'}
    m.enviar('a de calabresa grande ta boa')
    m.llm.resposta = None
    linha = m.estado()['carrinho']['itens'][0]
    assert 'calabresa' in linha['nome'].lower() and any('Grande' in o['nome'] for o in linha.get('opcoes') or [])


def test_recomendacao_sem_carrinho_nao_quebra_e_sugere_algo_da_hora():
    m = Mundo()
    endereco_pronto(m)                     # carrinho vazio e sem histórico (às 22h44 isso deu KeyError)
    m.wpp.limpar()
    m.enviar('o que voce me recomenda?')
    textos = ' '.join(m.wpp.textos())
    assert 'travadinha' not in textos and 'Que tal' in textos and m.wpp.cards()


def test_codigo_de_entrega_perguntado_depois_responde_o_codigo_e_nao_o_status():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')                         # pedido feito
    codigo = m.estado()['pedidos'][0]['codigo_entrega']
    assert codigo
    m.wpp.limpar()
    m.enviar('qual é o código de entrega?')
    texto = ' '.join(m.wpp.textos())
    assert 'código de entrega' in texto and codigo in texto


def test_codigo_de_entrega_de_pedido_antigo_busca_no_ifood():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    u = m.armazem[f'u:{m.wa}']
    codigo = u['pedidos'][0].pop('codigo_entrega')   # pedido feito antes de o campo existir
    m.armazem[f'u:{m.wa}'] = u
    m.wpp.limpar()
    m.enviar('qual a senha do entregador?')
    assert codigo in ' '.join(m.wpp.textos())


def test_codigo_de_entrega_no_meio_de_outro_pedido_responde_e_volta_pros_cards():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    codigo = m.estado()['pedidos'][0]['codigo_entrega']
    m.enviar('quero pao')                  # pedido novo, cards na tela
    assert m.estado()['fase'] == 'escolhendo'
    m.wpp.limpar()
    m.enviar('qual o codigo de entrega?')
    assert codigo in ' '.join(m.wpp.textos())
    assert m.estado()['fase'] == 'escolhendo'   # não perdeu o lugar


def test_quanto_deu_responde_o_total_do_pedido():
    from src.bot import textos as T
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    total = m.estado()['pedidos'][0]['total']
    m.llm.resposta = {'acao': 'acompanhar', 'sobre': 'total'}
    m.enviar('quanto deu meu pedido?')
    m.llm.resposta = None
    assert T.reais(total) in ' '.join(m.wpp.textos())


def test_ta_chegando_responde_status_inteiro_com_previsao_e_codigo():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    ped = m.estado()['pedidos'][0]
    m.wpp.limpar()
    m.llm.resposta = {'acao': 'acompanhar', 'sobre': 'previsao'}
    m.enviar('ta chegando?')
    m.llm.resposta = None
    texto = ' '.join(m.wpp.textos())
    assert '🕒 Chega' in texto and ped['codigo_entrega'] in texto and ped['codigo'] in texto
    assert 'meu_pedido' in m.wpp.todos_ids()                  # Atualizar status
    assert 'Fazer novo pedido' in str(m.wpp.saida[-1])        # não "Fazer pedido": já tem pedido feito


def test_a_segunda_foto_escolhe_pela_posicao():
    m = Mundo()
    endereco_pronto(m)
    est = m.estado()
    assert len(est['visiveis']) >= 2
    _, lid, idx = est['visiveis'][1].split(':')
    nome = est['listas'][lid]['ofertas'][int(idx)]['nome']
    m.llm.resposta = {'acao': 'escolher'}
    m.enviar('quero a segunda foto que voce mandou')
    m.llm.resposta = None
    assert m.estado()['carrinho']['itens'][0]['nome'] == nome


def test_segunda_feira_nao_e_a_segunda_opcao():
    m = Mundo()
    endereco_pronto(m)
    assert len(m.estado()['visiveis']) >= 2
    m.llm.resposta = {'acao': 'escolher'}
    m.enviar('quero pra segunda-feira')
    m.llm.resposta = None
    assert not (m.estado().get('carrinho') or {}).get('itens')
    assert 'Qual deles' in ' '.join(m.wpp.textos())


def test_cpf_dito_antes_da_hora_fica_guardado_e_nao_vai_pro_gemini():
    m = Mundo()
    endereco_pronto(m)
    antes = m.llm.chamadas
    m.enviar('meu cpf é 529.982.247-25')
    assert m.estado()['cpf'] == '52998224725' and m.llm.chamadas == antes
    assert 'Anotei seu CPF' in ' '.join(m.wpp.textos())


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
    assert not ouvidos and m.estado().get('cpf') == ''  # nem ouviu: áudio no CPF vale "sem CPF"


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


# --- "mudar" digitado (B1) ---------------------------------------------------------------

def _no_pagamento(m):
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    assert m.estado()['fase'] == 'pagamento'
    return m


def test_mudar_digitado_no_pagamento_abre_o_mudar():
    from src.bot import textos as T
    m = _no_pagamento(Mundo())
    antes = m.llm.chamadas
    m.wpp.limpar()
    m.enviar('Mudar')
    assert m.estado()['fase'] == 'mudar'
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['mud:itens', 'mud:endereco', 'mud:pagamento']
    assert T.FIM_DAS_OPCOES not in ' '.join(m.wpp.textos())
    assert m.llm.chamadas == antes          # não precisou da IA
    assert m.estado()['carrinho']['itens']  # o carrinho continua lá


def test_mudar_o_pedido_digitado_no_resumo_abre_o_mudar():
    m = pedido_ate_o_resumo(Mundo())
    m.enviar('mudar o pedido')
    assert m.estado()['fase'] == 'mudar' and not m.mcp.chamadas_de('submitOrder')


def test_mudar_sem_carrinho_repete_a_pergunta_e_nao_quebra():
    from src.bot import textos as T
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    assert m.estado()['fase'] == 'quantidade'   # escolheu, mas o carrinho ainda está vazio
    m.wpp.limpar()
    m.enviar('alterar')
    assert m.estado()['fase'] == 'quantidade'
    assert T.NADA_PRA_MUDAR in ' '.join(m.wpp.textos()) and m.wpp.ultimos_botoes()
    m = Mundo()
    m.enviar('mudar')                            # sem nada na conversa: cai no menu
    assert m.wpp.saida


def test_mudar_no_complemento_nao_vira_complemento():
    m = Mundo()
    _ate_o_complemento(m)
    m.enviar('mudar')
    assert m.estado()['fase'] == 'complemento'
    assert not _salvos(m)


# --- "sim"/"não" com sugestão no resumo (B2) ----------------------------------------------

def _resumo_sem_sugestao(m, monkeypatch):
    monkeypatch.setattr('src.bot.fluxo.complementos', lambda *a, **kw: [])
    pedido_ate_o_resumo(m)
    assert 'pra acompanhar' not in m.estado()['pergunta']['texto']
    return m


def test_sim_com_sugestao_nao_fecha_e_mostra_os_3_botoes():
    m = pedido_ate_o_resumo(Mundo())
    m.wpp.limpar()
    m.enviar('sim')
    assert not m.mcp.chamadas_de('submitOrder')
    assert m.estado()['fase'] == 'confirmar'
    botoes = m.wpp.ultimos_botoes()
    assert [i for i, _ in botoes][1:] == ['acomp', 'mudar'] and botoes[0][0].startswith('ok:')
    assert all(len(t) <= 20 for _, t in botoes)
    m.enviar('sim')                              # insistir no "sim" continua sem fechar
    assert not m.mcp.chamadas_de('submitOrder')


def test_nao_com_sugestao_nao_abre_o_mudar_direto():
    m = pedido_ate_o_resumo(Mundo())
    m.enviar('não')
    assert m.estado()['fase'] == 'confirmar'
    assert 'mud:itens' not in [i for i, _ in m.wpp.ultimos_botoes()]
    assert [i for i, _ in m.wpp.ultimos_botoes()][1:] == ['acomp', 'mudar']
    assert not m.mcp.chamadas_de('submitOrder')


def test_sim_sem_sugestao_continua_confirmando(monkeypatch):
    m = _resumo_sem_sugestao(Mundo(), monkeypatch)
    m.enviar('sim')
    assert len(m.mcp.chamadas_de('submitOrder')) == 1


def test_nao_sem_sugestao_continua_abrindo_o_mudar(monkeypatch):
    m = _resumo_sem_sugestao(Mundo(), monkeypatch)
    m.enviar('não')
    assert m.estado()['fase'] == 'mudar'


def test_colocar_sugestao_adiciona_o_item_e_mostra_o_resumo_de_novo():
    m = pedido_ate_o_resumo(Mundo())
    m.enviar('sim')
    antes = len(m.estado()['carrinho']['itens'])
    m.tocar('acomp')
    car = m.estado()['carrinho']
    assert len(car['itens']) == antes + 1 and any('Manteiga' in i['nome'] for i in car['itens'])
    assert m.mcp.chamadas_de('addItemToCart')
    assert m.estado()['fase'] == 'confirmar' and 'Confira seu pedido' in m.estado()['pergunta']['texto']
    assert car.get('entrega') and car.get('pagamento')   # entrega e pagamento refeitos pro resumo novo
    assert not m.mcp.chamadas_de('submitOrder')
    m.tocar('ok:')
    assert len(m.mcp.chamadas_de('submitOrder')) == 1


def test_sugestao_que_a_loja_nao_tem_volta_pro_resumo_sem_ela(monkeypatch):
    m = pedido_ate_o_resumo(Mundo())
    m.enviar('sim')
    monkeypatch.setattr('src.bot.fluxo.Bot._coletar', lambda self, pedido, loja_id: ([], None))
    m.tocar('acomp')
    assert m.estado()['fase'] == 'confirmar' and not m.mcp.chamadas_de('submitOrder')
    assert 'manteiga' not in m.estado()['pergunta']['texto'].split('Total')[-1]   # não oferece de novo


def test_aviso_de_botao_velho_nao_empilha_a_cada_toque():
    from src.bot import textos as T
    m = pedido_ate_o_resumo(Mundo())
    original = m.estado()['pergunta']['texto']
    for _ in range(3):
        m.enviar(('botao', 'xyz:velho'))
    assert m.wpp.saida[-1][1]['texto'].count(T.BOTAO_VELHO) == 1
    assert m.estado()['pergunta']['texto'] == original and m.estado()['fase'] == 'confirmar'


def test_pergunta_do_minimo_responde_o_minimo_e_nao_o_carrinho():
    # 18/10: "qual o valor minimo de pedido na drogaria?" respondia "Seu pedido até agora: R$ 18,89" duas vezes
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')            # pão sírio do Supermercado Central, que no mock pede R$ 25
    m.tocar('qtd:1')
    assert 'Faltam' in m.wpp.textos()[-1]   # o "Quer mais alguma coisa?" já avisa que falta pro mínimo
    m.wpp.limpar()
    m.enviar('qual o valor minimo de pedido no mercado?')
    textos = ' '.join(m.wpp.textos())
    assert 'pedido mínimo do *Supermercado Central* é *R$ 25,00*' in textos and 'faltam' in textos
    assert textos.count('Seu pedido até agora') == 1


def test_pergunta_do_minimo_nao_e_sugestao_e_completar_o_minimo_continua_sendo():
    from src.bot.interpretar import pede_sugestao, pergunta_minimo
    assert pergunta_minimo('qual o valor minimo de pedido na drogaria?')
    assert pergunta_minimo('quanto é o pedido mínimo')
    assert not pergunta_minimo('me sugere algo pra completar o minimo')
    assert pede_sugestao('me sugere algo pra completar o minimo')
    assert not pergunta_minimo('quero 2 dipironas')


def test_finalizar_avisa_na_hora_e_toque_repetido_nao_refaz_o_resumo():
    # 18/10 03h33: fechamento lento, Finalizar tocado 3x, 3 resumos chegaram de uma vez
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    assert '⏳ Fechando com a loja' in ' '.join(m.wpp.textos())   # avisa antes das chamadas lentas
    m.tocar('pag:0')
    m.enviar('529.982.247-25')
    assert m.estado()['fase'] == 'confirmar'
    getcart, antes = len(m.mcp.chamadas_de('getCart')), len(m.wpp.textos())
    m.tocar('fim')              # o Finalizar da mensagem de antes, tocado de novo
    m.tocar('fim')
    textos = ' '.join(m.wpp.textos()[antes:])
    assert 'resumo do pedido está aí em cima' in textos and 'Confira seu pedido' not in textos
    assert len(m.mcp.chamadas_de('getCart')) == getcart and m.estado()['fase'] == 'confirmar'


def test_ver_carrinho_vazio_diz_que_esta_vazio():
    # 18/10: esvaziou o carrinho, "mostra o meu carrinho" só respondeu "O que você quer pedir?"
    m = Mundo()
    endereco_pronto(m)
    m.wpp.limpar()
    m.llm.resposta = {'acao': 'ver_pedido'}
    m.enviar('mostra o meu carrinho')
    assert 'está vazio' in ' '.join(m.wpp.textos())


# --- lembrete do automático: "da última vez" compara a mesma grandeza --------------------------

def _lembrete_do_modelo_com_entrega(m, monkeypatch):
    from src.shared import mcp_fake
    endereco_pronto(m)
    m.enviar('todo dia as 7h quero pao')
    m.tocar('pick:')
    m.tocar('qtd:3')
    lj = mcp_fake._LOJA_POR_ID[m.estado()['carrinho']['loja_id']]
    monkeypatch.setitem(mcp_fake.LOJAS, lj, mcp_fake.LOJAS[lj][:3] + (4.99,) + mcp_fake.LOJAS[lj][4:])
    sub = m.estado()['carrinho']['subtotal']
    m.tocar('fim')
    return m.recs_dic[m.wa][0], sub


def _pedir_pelo_lembrete(m, rec):
    u = m.estado()  # já pediu antes: pagamento e CPF guardados, o "sim" do lembrete fecha sem perguntar nada
    u.update(pagamento_preferido={'tipo': 'PIX', 'nome': 'PIX'}, cpf='529.982.247-25')
    m.armazem[f'u:{m.wa}'] = u
    m.enviar(('botao', f'lem:pedir:{rec["id"]}'))


def test_lembrete_com_itens_iguais_e_entrega_nao_diz_que_o_preco_mudou(monkeypatch):
    from src.bot import textos as T
    m = Mundo()
    rec, sub = _lembrete_do_modelo_com_entrega(m, monkeypatch)
    assert 'Itens:' in T.lembrete(rec) and '+ entrega' in T.lembrete(rec)  # não chama subtotal de "última vez"
    _pedir_pelo_lembrete(m, rec)
    assert not any('preço mudou' in t for t in m.wpp.textos())
    assert len(m.mcp.chamadas_de('submitOrder')) == 1  # o "sim" do lembrete fechou o pedido
    rec = m.recs_dic[m.wa][0]
    assert rec['total'] == round(sub + 4.99, 2)  # o próximo lembrete já mostra o que a pessoa pagou
    assert f'Da última vez: {T.reais(sub + 4.99)}' in T.lembrete(rec)


def test_lembrete_com_itens_mais_caros_diz_que_o_preco_mudou(monkeypatch):
    m = Mundo()
    rec, _ = _lembrete_do_modelo_com_entrega(m, monkeypatch)
    m.ctx.recorrencias._mudar(m.wa, rec['id'], subtotal=1.0)  # os itens custavam bem menos da última vez
    _pedir_pelo_lembrete(m, rec)
    assert not m.mcp.chamadas_de('submitOrder')
    assert m.estado()['fase'] == 'confirmar'
    assert 'preço mudou' in m.wpp.saida[-1][1]['texto']
