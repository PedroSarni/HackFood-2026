"""Clientes de mentira conversando com o Bot DE VERDADE (fluxo, textos, MCP falso), só nesta máquina.

Serve pra ver o dash mexer sem WhatsApp e sem gastar o MCP real. Usa os fakes dos testes
(tests/fakes.py: WhatsApp que valida as regras da Meta, Gemini de regras fixas, McpFake) e os
mesmos espiões da produção (src/shared/painel.py), então o caminho até o dash é o mesmo.

Primeiro preenche os últimos 7 dias num relógio adiantado (o gráfico já nasce com histórico),
depois segue ao vivo, um cliente novo a cada poucos segundos.
Nada disso vai pro modal.Dict do bot: o diário simulado fica num dict em memória.
"""
import copy
import random
import threading
import time

from src.shared import painel
from tests.fakes import Armazem, Mundo

NOMES = ['Dona Cida', 'Seu Antônio', 'Marina Costa', 'Pedro Almeida', 'Ana Oliveira', 'Lucas Santos',
         'Beatriz Lima', 'Rafael Souza', 'Juliana Rocha', 'Bruno Ferreira', 'Camila Alves', 'Seu Zé']
ITENS = ['quero pao', 'quero leite', 'preciso de carne', 'quero uma pizza', 'preciso de dipirona']


class MundoAnotado(Mundo):
    """Mundo dos testes com os espiões da produção (src/bot/contexto.py e src/app.py).
    `agora` fixo por padrão (testes); `ao_vivo()` passa a seguir o relógio de verdade."""

    def __init__(self, diario_dic=None, nome=None, **kw):
        self._fixo = None
        super().__init__(**kw)
        self.nome = nome
        self.painel = diario_dic if diario_dic is not None else Armazem()
        self.diario = painel.Diario(self.painel, agora=lambda: self.agora, intervalo=None)
        self.ctx.wpp = painel.EspiaoWhatsApp(self.wpp, self.diario)
        mcp = self.mcp
        self.ctx._chamador = lambda wid: painel.espiar_mcp(mcp.chamar, self.diario, wid)
        Bot, mundo = self.Bot, self

        class BotAnotado(Bot):
            def processar(self, wa_id, msgs):
                if mundo.nome and msgs:
                    msgs[-1]['_nome'] = mundo.nome
                titulos = mundo.titulos()
                for msg in msgs:  # o fake manda o id como título; no WhatsApp vem o texto do botão
                    r = (msg.get('interactive') or {}).get('button_reply')
                    if r and r['id'] in titulos:
                        r['title'] = titulos[r['id']]
                painel.anotar_entrada(mundo.diario, wa_id, msgs)
                return super().processar(wa_id, msgs)
        self.Bot = BotAnotado

    @property
    def agora(self):
        return self._fixo if self._fixo is not None else time.time()

    @agora.setter
    def agora(self, valor):
        self._fixo = valor

    def ao_vivo(self):
        self._fixo = None

    def esperar(self, segundos):
        if self._fixo is None:
            time.sleep(segundos)
        else:
            self._fixo += segundos

    def eventos(self):
        return [v for k, v in self.painel.items() if k.startswith('ev:')]

    def sessoes(self, depois=0):
        return painel.montar_sessoes(self.eventos(), agora=self.agora + depois)

    def titulos(self):
        t = {}
        for tipo, d in self.wpp.saida:
            if tipo == 'botoes':
                t.update(d['botoes'])
            elif tipo == 'lista':
                t.update((i, ti) for i, ti, _ in d['linhas'])
            elif tipo == 'carrossel':
                t.update(b for c in d['cards'] for b in c['botoes'])
        return t

    def tem(self, prefixo):
        return any(i.startswith(prefixo) for i in self.wpp.todos_ids())

    def rastrear(self, pedido, ritmo):
        from src.bot.rastreio import acompanhar
        ctx = copy.copy(self.ctx)
        ctx.wpp = painel.EspiaoWhatsApp(self.wpp, self.diario, 'rastreio')
        dormir = (lambda s: time.sleep(s * ritmo / 10)) if self._fixo is None else (lambda s: self.esperar(s))
        acompanhar(ctx, self.wa, pedido, dormir=dormir, relogio=lambda: self.agora)


def _passo(m, ritmo, *msgs):
    m.wpp.limpar()
    m.enviar(*msgs)
    m.esperar(random.uniform(2, 9) * ritmo)


def jornada(m, ritmo=1.0, sorte=None):
    """Uma conversa com final sorteado: compra, abandono, cancelamento, só um oi..."""
    r = sorte if sorte is not None else random.random()
    u = m.armazem.get(f'u:{m.wa}')
    if u and u.get('carrinho'):
        # carrinho de outra visita: o bot guarda pra sempre e trava a busca na loja dele
        # ("Não achei pizza no Drogaria Saúde"). Aqui ele expira em silêncio, como um cancelar.
        u.update({'carrinho': None, 'fila': [], 'escolha': None, 'atual': None, 'pendente': None, 'fase': 'inicio'})
        m.armazem[f'u:{m.wa}'] = u
    if r < 0.06:
        _passo(m, ritmo, random.choice(['bom dia', 'oi', 'boa tarde']))
        return 'só oi'
    pedido = ('audio', f'm{random.randint(1, 999)}') if r < 0.14 else random.choice(ITENS)
    _passo(m, ritmo, pedido)
    if m.estado().get('fase') in ('endereco', 'novo_endereco') or m.tem('cand:'):
        _passo(m, ritmo, 'Rua das Flores, 120, São Carlos')
        _passo(m, ritmo, ('botao', next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('cand:'))))
        if m.tem('compl_nao'):
            _passo(m, ritmo, ('botao', 'compl_nao'))
    if not m.wpp.cards() and not m.tem('pick:'):
        return 'não achou'
    if random.random() < 0.25 and m.tem('mais:'):
        m.tocar('mais:')
        m.esperar(random.uniform(3, 8) * ritmo)
    if not m.tem('pick:'):
        return 'sem cards'
    m.tocar('pick:')
    m.esperar(random.uniform(3, 8) * ritmo)
    for _ in range(3):  # opções obrigatórias (tamanho da pizza, acompanhamento...)
        if m.tem('opt:') and not m.tem('qtd:'):
            m.tocar('opt:')
    if m.tem('qtd:'):
        m.tocar(f'qtd:{random.choice([1, 1, 2, 3])}')
    m.esperar(random.uniform(3, 10) * ritmo)
    if 0.14 <= r < 0.26:
        return 'largou o carrinho'
    if 0.26 <= r < 0.32:  # some 40 min e volta pra fechar (vira recuperada)
        m.esperar(40 * 60 if m._fixo is not None else 0)
    if not m.tem('fim'):
        return 'sem finalizar'
    m.tocar('fim')
    m.esperar(random.uniform(2, 6) * ritmo)
    if m.estado().get('fase') == 'pagamento':
        m.tocar('pag:0')
    if 0.32 <= r < 0.38:
        return 'parou no pagamento'
    if m.estado().get('fase') == 'cpf':
        _passo(m, ritmo, '529.982.247-25')
    if 0.38 <= r < 0.42:
        m.tocar('cancelar')
        return 'cancelou'
    if not m.tem('ok:'):
        return 'sem resumo'
    m.tocar('ok:')
    if m.rastreios:
        pedido_id = m.rastreios.pop()
        if m._fixo is None:
            threading.Thread(target=m.rastrear, args=(pedido_id, ritmo), daemon=True).start()
        else:
            m.rastrear(pedido_id, ritmo)
    return 'comprou'


def _cliente(dic, n):
    return MundoAnotado(diario_dic=dic, nome=NOMES[n % len(NOMES)], wa=f'55169{n:08d}')


def preencher_historico(dic, dias=7, conversas=60, semente=17):
    """Conversas espalhadas nos últimos `dias`, no relógio adiantado (roda em segundos)."""
    random.seed(semente)
    agora = time.time()
    clientes = [_cliente(dic, n) for n in range(len(NOMES))]
    for _ in range(conversas):
        m = random.choice(clientes)
        m.agora = agora - random.uniform(0.2, dias) * 86400
        try:
            jornada(m, ritmo=0.2)
        except Exception as e:  # noqa: BLE001 - conversa simulada que tropeça não para as outras
            print(f'simulador: conversa do histórico tropeçou: {e!r}')
    return clientes


def rodar_ao_vivo(dic, parar, clientes=None, intervalo=(6, 15), ritmo=1.0):
    """Até `parar` (threading.Event): a cada `intervalo` segundos alguém puxa conversa. Quem já
    comprou no histórico volta (recompra); de vez em quando chega gente nova."""
    random.seed()
    clientes = list(clientes or [])
    for m in clientes:
        m.ao_vivo()
    ocupados = {}
    while not parar.is_set():
        ocupados = {wa: t for wa, t in ocupados.items() if t.is_alive()}
        livres = [m for m in clientes if m.wa not in ocupados]
        if len(ocupados) < 4:
            if not livres or random.random() < 0.2:
                m = _cliente(dic, len(clientes))
                m.ao_vivo()
                clientes.append(m)
            else:
                m = random.choice(livres)

            def conversar(m=m):
                try:
                    jornada(m, ritmo=ritmo)
                except Exception as e:  # noqa: BLE001
                    print(f'simulador: conversa ao vivo tropeçou: {e!r}')
            t = threading.Thread(target=conversar, daemon=True)
            t.start()
            ocupados[m.wa] = t
        parar.wait(random.uniform(*intervalo))
