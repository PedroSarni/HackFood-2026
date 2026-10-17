"""Diário do painel: conversa de verdade (Bot + fakes) vira sessão do dash."""
from src.shared import painel
from tests.fakes import Armazem, Mundo
from tests.test_fluxo import pedido_ate_o_resumo


class MundoAnotado(Mundo):
    """Mundo com os mesmos espiões da produção (src/bot/contexto.py e src/app.py)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.painel = Armazem()
        self.diario = painel.Diario(self.painel, agora=lambda: self.agora, intervalo=None)
        self.ctx.wpp = painel.EspiaoWhatsApp(self.wpp, self.diario)
        mcp = self.mcp
        self.ctx._chamador = lambda wid: painel.espiar_mcp(mcp.chamar, self.diario, wid)
        Bot, diario = self.Bot, self.diario

        class BotAnotado(Bot):
            def processar(self, wa_id, msgs):
                painel.anotar_entrada(diario, wa_id, msgs)
                return super().processar(wa_id, msgs)
        self.Bot = BotAnotado

    def eventos(self):
        return [v for k, v in self.painel.items() if k.startswith('ev:')]

    def sessoes(self, depois=0):
        return painel.montar_sessoes(self.eventos(), agora=self.agora + depois)


def test_compra_completa_vira_sessao_concluida_com_valor_e_historico():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    [s] = m.sessoes()
    assert s['status'] == 'completed' and s['stage'] == 9
    assert s['amountCents'] > 0 and s['restaurant'] != 'Sem restaurante'
    assert s['city'] == 'São Carlos'
    tipos = [e['type'] for e in s['entries'] if e['kind'] == 'event']
    for t in ('conversation_started', 'recommendations_shown', 'cart_created', 'payment_selected', 'order_confirmed'):
        assert t in tipos
    falas = [e for e in s['entries'] if e['kind'] == 'message']
    assert falas[0]['role'] == 'customer' and any(e['role'] == 'agent' for e in falas)


def test_cpf_digitado_nunca_vai_pro_diario():
    m = pedido_ate_o_resumo(MundoAnotado())
    tudo = repr(m.eventos())
    assert '529.982.247-25' not in tudo and '52998224725' not in tudo


def test_link_de_login_nao_vai_pro_diario():
    m = MundoAnotado(logado=False)
    m.enviar('oi')
    assert 'exemplo.test/login' not in repr(m.eventos())


def test_carrinho_parado_vira_abandono_e_depois_recuperacao():
    m = MundoAnotado()
    from tests.test_fluxo import endereco_pronto
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    assert m.sessoes()[0]['status'] == 'active'
    assert m.sessoes(depois=31 * 60)[0]['status'] == 'abandoned'
    m.agora += 40 * 60  # volta 40 min depois e fecha
    m.tocar('fim')
    m.tocar('pag:0')
    m.enviar('529.982.247-25')
    m.tocar('ok:')
    [s] = m.sessoes()
    assert s['status'] == 'recovered'
    assert 'cart_recovered' in [e['type'] for e in s['entries']]


def test_mensagem_depois_do_pedido_abre_outra_sessao_mas_lembrete_fica_na_mesma():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    m.enviar(('botao', 'rec:0'))   # "Não precisa": ainda é sobre o pedido
    assert len(m.sessoes()) == 1
    m.agora += 60
    m.enviar('quero leite')
    assert len(m.sessoes()) == 2
    assert m.sessoes()[0]['status'] == 'active'


def test_cancelar_com_carrinho_vira_cancelada():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('cancelar')
    assert m.sessoes()[0]['status'] == 'cancelled'


def test_rastreio_entregue_vai_pra_sessao_do_pedido():
    m = pedido_ate_o_resumo(MundoAnotado())
    m.tocar('ok:')
    pedido = m.mcp.chamadas_de('submitOrder') and m.rastreios[-1]
    m.agora += 60
    m.enviar('quero leite')   # puxou outra conversa antes da entrega
    m.diario.anotar(m.wa, 'mcp', tool='trackOrder', ok=True, pedido=pedido, status='DELIVERED')
    antiga = next(s for s in m.sessoes() if s['status'] == 'completed')
    assert antiga['stage'] == 10


def test_erro_do_ifood_aparece_e_diario_quebrado_nao_derruba_o_bot():
    class DictQuebrado(dict):
        def update(self, *a, **kw):
            raise RuntimeError('modal fora do ar')
    m = MundoAnotado()
    m.diario.dic = DictQuebrado()
    m.enviar('bom dia')                      # nada estoura
    assert m.wpp.saida
    eventos = [{'ts': 1, 'wa': '1', 'tipo': 'entrada', 'texto': 'oi'},
               {'ts': 2, 'wa': '1', 'tipo': 'mcp', 'tool': 'searchOffers', 'ok': False, 'erro': 'TIMEOUT'}]
    [s] = painel.montar_sessoes(eventos, agora=10)
    assert s['status'] == 'failed' and 'agent_error' in [e['type'] for e in s['entries']]


def test_lembrete_abre_sessao_de_follow_up():
    eventos = [{'ts': 1, 'wa': '1', 'tipo': 'saida', 'texto': 'Podemos pedir?', 'origem': 'lembrete'},
               {'ts': 2, 'wa': '1', 'tipo': 'entrada', 'texto': 'Sim, pode pedir', 'botao': 'lem:pedir:a'},
               {'ts': 3, 'wa': '1', 'tipo': 'mcp', 'tool': 'createCart', 'ok': True, 'total': 30.5, 'loja': 'X'},
               {'ts': 4, 'wa': '1', 'tipo': 'mcp', 'tool': 'submitOrder', 'ok': True, 'pedido': 'p1'}]
    [s] = painel.montar_sessoes(eventos, agora=10)
    assert s['origin'] == 'Follow-up' and s['status'] == 'completed' and s['amountCents'] == 3050
