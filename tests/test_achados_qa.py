"""Achados do QA da madrugada de 18/10: a quantidade dita fora da pergunta "quantas unidades?" (U20), o "até
agora" que somava entrega e taxas sem avisar (M2), o pedido que só fechava com toque, nunca por áudio, e o
"o pagamento não passou" que o rastreio mandou depois do "saiu pra entrega", e o pedido que atravessa a troca
do iFood real pro de reserva (e a volta) sem a pessoa perceber."""
import pytest

from src.bot import interpretar
from src.bot import textos as T
from src.bot.contexto import presa_ao_pedido
from src.bot.ifood import IfoodTrocou
from src.bot.rastreio import acompanhar
from src.shared import mcp_fake
from tests.fakes import Mundo, WhatsAppFake
from tests.test_fluxo import endereco_pronto, pedido_ate_o_resumo

LEITE = {'termo': 'leite', 'busca': 'leite', 'quantidade': 10, 'tipo_loja': 'MERCADO'}


def _rastreio(*codigos):
    """O que o rastreio avisa pra uma sequência de status do iFood (o último encerra)."""
    fila = iter(codigos)

    class Api:
        def rastrear(self, _pid):
            c = next(fila)
            return {'codigo': c, 'descricao': '', 'parar': c == codigos[-1], 'proxima': None}

    class Ctx:
        wpp = WhatsAppFake()

        def ifood(self, _wa):
            return Api()
    ctx = Ctx()
    acompanhar(ctx, 'wa', 'p1', dormir=lambda s: None)
    return [d['texto'] for _, d in ctx.wpp.saida]


def test_pagamento_recusado_depois_de_sair_pra_entrega_nao_assusta():
    # a sequência real do pedido 7483, das 06:10 às 06:18
    avisos = _rastreio('PIX_CREATED', 'CONFIRMED', 'DISPATCHED', 'PAYMENT_DECLINED', 'DISPATCHED', 'DELIVERED')
    assert avisos == [T.STATUS['CONFIRMED'], T.STATUS['DISPATCHED'], T.STATUS['DELIVERED']]


def test_pagamento_recusado_antes_da_loja_confirmar_avisa():
    avisos = _rastreio('PIX_CREATED', 'PAYMENT_DECLINED', 'CANCELLED')
    assert avisos == [T.STATUS['PAYMENT_DECLINED'], T.STATUS['CANCELLED']]


def _lia_diz(m, intencao):
    """Daqui em diante a Lia (interpretar) devolve `intencao`; o resto (relevância, foto...) segue o fake."""
    llm = m.llm

    def gerar(sistema, partes, esquema, **kw):
        if sistema == interpretar.SISTEMA:
            return dict(intencao), 'fake', 0.01
        return llm(sistema, partes, esquema, **kw)
    m.ctx._gerar_json = gerar


def _com_dois_paes():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:2')          # "Seu pedido até agora" + Finalizar / Quero mais coisas / Tirar um item
    return m


def test_mais_10_leites_fora_da_pergunta_de_quantidade_vai_buscar_o_leite_e_nao_finge():
    m = _com_dois_paes()
    buscas = len(m.mcp.chamadas_de('searchOffers'))
    _lia_diz(m, {'acao': 'quantidade', 'numero': 10, 'itens': [LEITE],
                 'resposta': 'Pode deixar, adicionei mais 10 leites! 🥛'})
    m.wpp.limpar()
    m.enviar('pode colocar mais 10 leites')
    assert len(m.mcp.chamadas_de('searchOffers')) > buscas           # foi atrás do leite
    assert 'adicionei' not in ' '.join(m.wpp.textos()).lower()        # e não disse que já tinha colocado


def test_mais_2_leites_nao_vira_o_segundo_botao():
    m = _com_dois_paes()
    _lia_diz(m, {'acao': 'quantidade', 'numero': 2, 'itens': [{**LEITE, 'quantidade': 2}], 'resposta': 'Já vejo! 🥛'})
    m.wpp.limpar()
    m.enviar('coloca mais 2 leites')
    assert m.wpp.cards() and 'O que mais você quer' not in ' '.join(m.wpp.textos())   # buscou, não tocou "Quero mais"


def test_faz_o_pedido_falado_com_o_resumo_na_tela_fecha_sem_pedir_toque():
    m = pedido_ate_o_resumo(Mundo())
    _lia_diz(m, {'acao': 'finalizar', 'resposta': 'Bora! 🎉'})
    m.enviar(('audio', 'faz-o-pedido'))
    assert len(m.mcp.chamadas_de('submitOrder')) == 1
    assert 'Toque em' not in ' '.join(m.wpp.textos()[-3:])


def test_ate_agora_separa_os_itens_da_entrega_e_das_taxas():
    assert T.ate_agora(47.97, subtotal=36.99) == '🧺 Seu pedido até agora: *R$ 36,99*\n🛵 Com entrega e taxas: *R$ 47,97*'
    assert T.ate_agora(10.58, subtotal=10.58) == '🧺 Seu pedido até agora: *R$ 10,58*'   # o falso, antes da entrega
    assert T.ate_agora(10.58) == '🧺 Seu pedido até agora: *R$ 10,58*'
    assert 'R$ 8,00 por pessoa' in T.ate_agora(48.0, pessoas=6, subtotal=40.0)          # cada um paga a entrega também
    assert T.mais_alguma(47.97, None, 0, 'BK', subtotal=36.99).startswith('🧺 Seu pedido até agora: *R$ 36,99*\n🛵')


def _lista_de_leite_na_tela():
    """2 pães no carrinho e os cards do leite na tela (com os botões "Quero esse" da lista nova)."""
    m = _com_dois_paes()
    m.enviar('quero leite')
    assert any(i.startswith('pick:') for i in m.wpp.todos_ids())
    return m


@pytest.fixture
def outro_ifood():
    """Liga "o outro iFood": o mock desligou (ou ligou) com o pedido montado, 18/10 01h43 (QA B3/U4). É o catálogo
    embutido com outros ids, menos os itens com `sem` no nome: as lojas de antes deixam de existir aqui e os
    produtos de mesmo nome estão do lado de cá, como o iFood real e o de reserva."""
    guardado = {k: getattr(mcp_fake, k) for k in ('LOJAS', 'CATALOGO', 'SINONIMOS', 'VERSAO', '_ITEM_POR_ID',
                                                   '_LOJA_POR_ID')}
    fotos = dict(mcp_fake._FOTOS)

    def trocar(*sem, vazio=False):
        lojas = {k: {'nome': n, 'tipo': t, 'eta': eta, 'taxa': taxa, 'nota': nota, 'km': km, 'minimo': minimo}
                 for k, (n, t, eta, taxa, nota, km, minimo) in mcp_fake.LOJAS.items()}
        itens = [{'loja': lj, 'nome': nome, 'desc': desc, 'preco': preco, 'promo': promo,
                  'grupos': [[g[0], g[1], g[2], [list(o) for o in g[3]]] for g in grupos] if grupos else None}
                 for lj, nome, desc, preco, promo, grupos in mcp_fake.CATALOGO
                 if not vazio and not any(s in nome for s in sem)]
        mcp_fake.usar_catalogo({'versao': f'outro:{sem}:{vazio}', 'lojas': lojas, 'itens': itens})
    yield trocar
    # volta o catálogo embutido sem recarregar o módulo: um reload cria outro McpFake, e o monkeypatch dos testes
    # seguintes (test_fluxo, a loja que exige CPF) iria pra classe nova enquanto o Mundo usa a velha
    for k, v in guardado.items():
        setattr(mcp_fake, k, v)
    mcp_fake._FOTOS.clear()
    mcp_fake._FOTOS.update(fotos)


def _nomes(car):
    return [(i['nome'], i['qtd']) for i in (car or {}).get('itens') or []]


def test_troca_de_ifood_leva_o_carrinho_junto_e_ninguem_percebe(outro_ifood):
    m = _com_dois_paes()
    antes = m.estado()['carrinho']
    outro_ifood()
    m.wpp.limpar()
    m.enviar('quero leite')
    car = m.estado()['carrinho']
    assert m.ctx.carrinho_valido(car) and car['id'] != antes['id'] and car['loja'] == antes['loja']
    assert _nomes(car) == _nomes(antes)                      # os 2 pães, na mesma loja, do lado de cá
    texto = ' '.join(m.wpp.textos())
    assert not any(t in texto for t in (T.PEDIDO_RECOMECADO, T.BOTAO_VELHO, 'disponíve', 'no lugar'))
    assert m.wpp.cards()                                     # e foi buscar o leite, como se nada fosse


def test_card_de_antes_da_troca_vale_o_mesmo_produto_do_lado_de_ca(outro_ifood):
    m = _lista_de_leite_na_tela()
    pick = next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('pick:'))
    _, lid, idx = pick.split(':')
    leite = m.estado()['listas'][lid]['ofertas'][int(idx)]['nome']
    outro_ifood()
    m.wpp.limpar()
    m.enviar(('botao', pick))
    esc = m.estado()['escolha']
    assert esc['oferta']['nome'] == leite and m.ctx.carrinho_valido({'loja_id': esc['oferta']['loja_id']})
    assert f'*{leite}*' in m.wpp.textos()[-1] and T.BOTAO_VELHO not in ' '.join(m.wpp.textos())   # "Quantas...?"
    m.tocar('qtd:1')
    assert [n for n, _ in _nomes(m.estado()['carrinho'])][1:] == [leite]   # os pães vieram junto e o leite entrou


def test_quantas_unidades_respondido_depois_da_troca_entra_o_produto_daqui(outro_ifood):
    m = _lista_de_leite_na_tela()
    m.tocar('pick:')                                         # "Quantas unidades de *Leite...*?"
    leite = m.estado()['escolha']['oferta']['nome']
    outro_ifood()
    m.wpp.limpar()
    m.enviar(('botao', 'qtd:2'))
    car = m.estado()['carrinho']
    assert m.ctx.carrinho_valido(car) and _nomes(car)[-1] == (leite, 2)


def test_produto_da_vez_que_nao_tem_do_outro_lado_vira_as_opcoes_de_agora(outro_ifood):
    m = _lista_de_leite_na_tela()
    m.tocar('pick:')
    leite = m.estado()['escolha']['oferta']['nome']
    outro_ifood(leite)
    m.wpp.limpar()
    m.enviar(('botao', 'qtd:2'))
    assert T.indisponiveis([leite], do_pedido=False) in m.wpp.textos() and m.wpp.cards()
    assert not m.estado().get('escolha') and leite not in [n for n, _ in _nomes(m.estado()['carrinho'])]


def test_resumo_de_antes_da_troca_nao_fecha_e_vem_o_resumo_novo(outro_ifood):
    m = pedido_ate_o_resumo(Mundo())
    ok = next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('ok:'))
    outro_ifood()
    m.wpp.limpar()
    m.enviar(('botao', ok))                                  # o "Confirmar" do resumo com o valor de antes
    assert not m.rastreios and not m.mcp.chamadas_de('submitOrder')
    assert T.PEDIDO_ATUALIZADO in m.wpp.textos() and m.estado()['fase'] == 'confirmar'
    m.tocar('ok:')                                           # o do resumo novo fecha
    assert m.rastreios


def test_o_que_nao_tem_do_outro_lado_sai_como_produto_que_acabou(outro_ifood):
    m = _lista_de_leite_na_tela()
    m.tocar('pick:')
    m.tocar('qtd:1')
    (pao, _), (leite, _) = _nomes(m.estado()['carrinho'])
    outro_ifood('Leite')                                     # do lado de cá não tem leite nenhum
    m.wpp.limpar()
    m.enviar(('botao', 'fim'))
    assert T.indisponiveis([leite]) in m.wpp.textos()
    car = m.estado()['carrinho']
    assert m.ctx.carrinho_valido(car) and _nomes(car) == [(pao, 2)]


def test_sem_o_mesmo_produto_vai_o_parecido_e_a_pessoa_fica_sabendo(outro_ifood):
    m = _com_dois_paes()
    (pao, qtd), = _nomes(m.estado()['carrinho'])
    outro_ifood(pao)                                         # esse pão não tem do lado de cá; outros pães, sim
    m.wpp.limpar()
    m.enviar('quero leite')
    (novo, qtd_nova), = _nomes(m.estado()['carrinho'])
    assert novo != pao and qtd_nova == qtd
    assert T.no_lugar([(pao, novo)]) in m.wpp.textos()


def test_sem_nada_do_pedido_do_outro_lado_recomeca_falando_como_loja(outro_ifood):
    escreveu, tocou = _com_dois_paes(), _com_dois_paes()
    outro_ifood(vazio=True)
    for m in (escreveu, tocou):
        m.wpp.limpar()
    escreveu.enviar('quero leite')
    assert escreveu.wpp.textos()[0] == T.PEDIDO_RECOMECADO and not escreveu.estado().get('carrinho')
    tocou.enviar(('botao', 'fim'))                           # o toque era no pedido que sumiu: volta pro menu
    assert tocou.wpp.textos()[0].startswith(T.PEDIDO_RECOMECADO) and tocou.estado()['fase'] == 'pedido'
    assert 'iFood' not in T.PEDIDO_RECOMECADO


def test_ifood_cai_no_meio_da_rodada_e_o_pedido_vai_junto_sem_expirou(outro_ifood):
    m = _com_dois_paes()
    antes = m.estado()['carrinho']
    caiu = []

    def chamar(ferramenta, **args):  # o real caiu nesta chamada e o modo palco ligou o de reserva (contexto.py)
        if not caiu and presa_ao_pedido(ferramenta, args):
            caiu.append(ferramenta)
            outro_ifood()
            raise IfoodTrocou(f'{ferramenta}: TIMEOUT')
        return m.mcp.chamar(ferramenta, **args)
    m.ctx._chamador = lambda wid: chamar
    m.wpp.limpar()
    m.enviar('quero leite')                                  # a busca na loja do carrinho é a que cai
    assert caiu == ['searchOffers']
    texto = ' '.join(m.wpp.textos())
    assert 'expirou' not in texto and T.ERRO not in texto and m.wpp.cards()
    car = m.estado()['carrinho']
    assert m.ctx.carrinho_valido(car) and _nomes(car) == _nomes(antes)


def test_agendar_abaixo_do_minimo_agenda_e_no_dia_pede_pra_completar():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('todo dia as 7h quero pao')
    m.tocar('pick:')
    m.tocar('qtd:1')               # 1 pacote não chega no mínimo da loja (3 chegam)
    m.tocar('fim')
    assert not m.mcp.chamadas_de('submitOrder')
    [rec] = m.recs_dic[m.wa]                                   # QA U24: o mínimo barrava o agendamento
    ultimo = m.wpp.textos()[-1]
    assert 'Combinado' in ultimo and 'pedido mínimo' in ultimo
    m.wpp.limpar()
    m.enviar(('botao', f'lem:pedir:{rec["id"]}'))              # o dia chegou: o mínimo vale agora
    assert not m.mcp.chamadas_de('submitOrder') and 'mínimo' in ' '.join(m.wpp.textos())


def test_quero_esse_de_antes_do_cancelar_e_botao_velho():
    m = Mundo()
    endereco_pronto(m)
    pick = next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('pick:'))
    m.enviar('cancelar')
    m.wpp.limpar()
    m.enviar(('botao', pick))
    assert T.BOTAO_VELHO in m.wpp.textos()[-1] and m.estado()['fase'] == 'pedido'   # QA U7: reabria a compra


def test_sim_quero_da_foto_de_antes_nao_refaz_a_busca_depois_de_outro_pedido():
    m = Mundo()
    endereco_pronto(m)
    m.enviar(('foto', 'f1'))
    sim = next(i for i in m.wpp.todos_ids() if i.startswith('foto:sim:'))
    m.enviar('quero leite')
    buscas = len(m.mcp.chamadas_de('searchOffers'))
    m.wpp.limpar()
    m.enviar(('botao', sim))
    assert T.BOTAO_VELHO in m.wpp.textos()[-1]                                  # QA U10
    assert len(m.mcp.chamadas_de('searchOffers')) == buscas


def test_fazer_pedido_embaixo_da_mesma_pergunta_ensina_em_vez_de_repetir():
    m = Mundo()
    endereco_pronto(m)
    m.enviar('cancelar')                              # menu: "O que você quer pedir?" + atalhos
    m.wpp.limpar()
    m.enviar(('botao', 'pedir'))
    assert m.wpp.textos()[0] == T.COMO_PEDIR and T.PERGUNTA_PEDIDO not in m.wpp.textos()   # QA U1


def test_foto_sozinha_sempre_pergunta_mesmo_se_a_iris_acha_que_ja_pediu():
    m = Mundo()
    endereco_pronto(m)
    m.llm.foto = {'tipo': 'comida', 'descricao': 'pizza', 'itens': [], 'ja_pediu': True, 'resposta': 'Que pizza! 🍕',
                  'parecidos': [{'termo': 'pizza', 'busca': 'pizza', 'tipo_loja': 'RESTAURANTE'}]}
    buscas = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar(('foto', 'f1'))                          # sem legenda nem texto: um "sim" de antes não é pedido (U9)
    assert m.estado()['fase'] == 'foto' and len(m.mcp.chamadas_de('searchOffers')) == buscas
    m.enviar(('foto', 'f2', 'quero essa'))            # com o pedido escrito, vai direto
    assert len(m.mcp.chamadas_de('searchOffers')) > buscas


def test_pagamento_e_cpf_tem_como_mudar():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    assert 'mudar' in [i for i, _ in m.wpp.ultimos_botoes()]                        # pagamento (QA U3)
    m.tocar('pag:0')
    assert m.estado()['fase'] == 'cpf' and 'mudar' in [i for i, _ in m.wpp.ultimos_botoes()]
    m.tocar('mudar')
    assert m.estado()['fase'] != 'cpf'


def test_rastreio_para_quando_a_pessoa_apaga_os_dados():
    m = pedido_ate_o_resumo(Mundo())
    m.tocar('ok:')
    m.armazem.pop(f'u:{m.wa}')                        # "apagar meus dados" com o pedido a caminho (QA H4)
    m.ctx.armazem = m.armazem
    assert acompanhar(m.ctx, m.wa, m.rastreios[-1], dormir=lambda s: None) == 'apagou'


def test_saudacao_usa_o_nome_de_quem_esta_falando():
    m = Mundo()
    m.armazem[f'u:{m.wa}'] = {**(m.armazem.get(f'u:{m.wa}') or {}), 'nome': 'Davi Lima', 'nome_ifood': 'Fabio Kauê'}
    m.wpp.limpar()
    m.enviar('oi')
    assert 'Davi' in m.wpp.textos()[0] and 'Fabio' not in m.wpp.textos()[0]          # QA M3
    m.armazem[f'u:{m.wa}']['nome'] = '🌸~'
    m.wpp.limpar()
    m.enviar('oi')
    assert 'Fabio' in m.wpp.textos()[0]                                              # sem nome no WhatsApp


def test_meu_pedido_com_carrinho_montando_mostra_o_carrinho_e_cade_e_do_que_ja_saiu():
    m = _com_dois_paes()
    m.wpp.limpar()
    m.enviar('meu pedido')
    assert 'Seu pedido:*' in m.wpp.textos()[-1] and '2 pacotes de' in m.wpp.textos()[-1]   # U21: era o pedido antigo
    assert interpretar.regra_rapida('cadê meu pedido') == {'acao': 'acompanhar', 'sobre': 'status'}


def test_aviso_do_rastreio_diz_qual_pedido_e():
    """18/10: "saiu pra entrega" solto no meio de outro pedido parecia o bot chapando. Com o registro do pedido no
    armazém, cada aviso vem com loja, itens e valor; sem registro (ctx sem armazém), fica só o status."""
    from tests.fakes import Armazem
    fila = iter(['CONFIRMED', 'DISPATCHED', 'DELIVERED'])

    class Api:
        def rastrear(self, _pid):
            c = next(fila)
            return {'codigo': c, 'descricao': '', 'parar': c == 'DELIVERED', 'proxima': None}

    class Ctx:
        wpp = WhatsAppFake()
        armazem = Armazem()

        def ifood(self, _wa):
            return Api()
    ctx = Ctx()
    ctx.armazem['u:wa'] = {'pedidos': [{'id': 'outro', 'loja': 'Pizzaria'}, {'id': 'p1', 'codigo': 'B1013',
                           'loja': 'Supermercado Dona Lurdes', 'resumo': '2x Picanha bovina Seara, 1x Carvão vegetal',
                           'total': 157.7}]}
    acompanhar(ctx, 'wa', 'p1', dormir=lambda s: None)
    avisos = [d['texto'] for _, d in ctx.wpp.saida]
    assert len(avisos) == 3 and all(a.startswith(T.STATUS[c]) for a, c in zip(avisos, ('CONFIRMED', 'DISPATCHED', 'DELIVERED')))
    assert all('Pedido *B1013* · *Supermercado Dona Lurdes*' in a and 'Picanha' in a and 'R$ 157,70' in a for a in avisos), avisos
    assert 'Pizzaria' not in avisos[1]


def test_ja_pode_passar_no_pix_fecha_direto_sem_resumo_nem_cpf():
    """18/10: quem manda é a pessoa. "Já pode passar no pix" = PIX escolhido, sem pedir CPF, sem "Confira seu
    pedido": o pedido sai na hora e o "Pedido feito" diz o que foi e quanto deu."""
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:2')
    m.wpp.limpar()
    m.enviar('já pode passar no pix')
    textos = ' '.join(m.wpp.textos())
    assert len(m.mcp.chamadas_de('submitOrder')) == 1
    assert 'Confira seu pedido' not in textos and 'CPF' not in textos and 'Como você quer pagar' not in textos
    assert 'Pedido feito' in textos and 'PIX' in textos
    pag = m.mcp.chamadas_de('setCartPayment')[-1]['paymentMethodId']
    assert 'PIX' in str(m.mcp.armazem[f'mock:{m.wa}']['carrinhos'][next(iter(m.mcp.armazem[f'mock:{m.wa}']['carrinhos']))]['paymentMethod']['kind']) and pag
    assert m.estado()['pedidos'][0]['total'] and m.estado()['carrinho'] is None
    assert interpretar.regra_rapida('já pode passar no pix') == {'acao': 'finalizar', 'pagamento': 'PIX'}

