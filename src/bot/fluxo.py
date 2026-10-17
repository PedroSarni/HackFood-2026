"""A conversa: recebe o lote de mensagens de uma pessoa e conduz o pedido até o fim.

Quem decide é o código, etapa por etapa (`u['fase']`). O Gemini só entra quando chega texto
livre, áudio ou foto que as regras rápidas não resolvem (src/bot/interpretar.py). Botão é
sempre caminho determinístico: rápido e sem chance de a IA "achar" outra coisa.

Cada pergunta que vai com botões fica guardada em `u['pergunta']`. É isso que permite aceitar
"2", "o segundo" ou o texto do botão digitado no lugar do toque, e reapresentar a pergunta
quando a pessoa responde outra coisa.

Estado da pessoa (`u`): ver `estado_novo()`. Mora no dicionário com chave `u:{wa_id}`.
"""
import os
import time
import traceback

from src.bot import ranking
from src.bot import textos as T
from src.bot.ifood import PrecisaLogin
from src.bot.interpretar import cpf_em, igual_a_botao, interpretar, normalizar, numero_em, regra_rapida
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao
from src.shared.llm import ErroLLM
from src.shared.whatsapp import ErroWhatsApp

POR_PAGINA = 3          # cards por vez ("Mais opções" mostra os próximos 3 da MESMA lista)
LISTAS_GUARDADAS = 3    # listas antigas que ainda aceitam toque de botão
PEDIDOS_GUARDADOS = 10
TRIVIAIS = {'saudacao', 'agradecer', 'sim'}
# etapas em que um "oi" no meio não deve jogar o pedido fora: reapresenta a pergunta
NO_MEIO_DO_PEDIDO = {'escolhendo', 'quantidade', 'opcao', 'mais', 'tirar', 'pagamento', 'cpf', 'confirmar',
                     'mudar', 'endereco', 'endereco_escolha', 'endereco_lista', 'complemento', 'bairro'}


def estado_novo():
    return {'fase': 'inicio', 'pergunta': {}, 'pendente': None, 'fila': [], 'atual': None,
            'listas': {}, 'lista_atual': None, 'escolha': None, 'carrinho': None,
            'endereco': None, 'novo_endereco': None, 'pagamento_preferido': None, 'cpf': None,
            'pedidos': [], 'contador': 0, 'nome': None, 'ultima_msg': 0, 'ultima_acao': None}


class Entrada:
    """Uma mensagem recebida, já sem a casca da Meta."""

    def __init__(self, tipo, texto='', botao=None, mime=None, dados=None, media_id=None):
        self.tipo = tipo            # texto | botao | audio | imagem | localizacao | outro
        self.texto = texto
        self.botao = botao          # id do botão tocado
        self.mime = mime
        self.dados = dados          # bytes de áudio/foto (baixados sob demanda)
        self.media_id = media_id


def entradas_de(msgs):
    saida = []
    for m in msgs:
        tipo = m.get('type')
        if tipo == 'text':
            saida.append(Entrada('texto', (m.get('text') or {}).get('body', '')))
        elif tipo == 'interactive':
            it = m.get('interactive') or {}
            r = it.get('button_reply') or it.get('list_reply') or {}
            saida.append(Entrada('botao', r.get('title', ''), botao=r.get('id', '')))
        elif tipo == 'button':  # quick reply de template (lembrete)
            b = m.get('button') or {}
            saida.append(Entrada('botao', b.get('text', ''), botao=b.get('payload') or b.get('text', '')))
        elif tipo == 'audio':
            a = m.get('audio') or {}
            saida.append(Entrada('audio', mime=a.get('mime_type'), media_id=a.get('id')))
        elif tipo == 'image':
            i = m.get('image') or {}
            saida.append(Entrada('imagem', i.get('caption', ''), mime=i.get('mime_type'), media_id=i.get('id')))
        elif tipo == 'location':
            loc = m.get('location') or {}
            txt = ', '.join(x for x in (loc.get('name'), loc.get('address')) if x)
            saida.append(Entrada('localizacao', txt))
        else:
            saida.append(Entrada('outro', tipo or ''))
    return saida


class Bot:
    def __init__(self, ctx):
        self.ctx = ctx
        self.wa = None
        self.u = None

    # ================================================================== entrada

    def processar(self, wa_id, msgs):
        self.wa = wa_id
        self.u = u = self._carregar(wa_id)
        if msgs and msgs[-1].get('_nome'):
            u['nome'] = msgs[-1]['_nome']
        u['ultima_msg'] = self.ctx.agora()
        try:
            entradas = entradas_de(msgs)
            if self._debug_reset(entradas):   # palavra secreta de debug: desloga e zera tudo
                return
            botoes = [e for e in entradas if e.tipo == 'botao']
            livres = [e for e in entradas if e.tipo != 'botao']
            if botoes:
                # toque duplo no mesmo botão vale um; de vários cards, vale o último toque
                vistos, unicos = set(), []
                for b in botoes:
                    if b.botao not in vistos:
                        vistos.add(b.botao)
                        unicos.append(b)
                picks = [b for b in unicos if b.botao.startswith('pick:')]
                unicos = [b for b in unicos if not b.botao.startswith('pick:')] + picks[-1:]
                for b in unicos:
                    self._protegido(lambda b=b: self.botao(b.botao))
                livres = [e for e in livres if not self._trivial(e)]
            if livres:
                self._protegido(lambda: self.livre(livres))
        finally:
            self._salvar()

    def logou(self, wa_id):
        """Chamado quando o OAuth termina no navegador."""
        self.wa = wa_id
        self.u = u = self._carregar(wa_id)
        try:
            def seguir():
                nome = (u.get('nome') or '').split(' ')[0]  # nome do perfil de WhatsApp, se já temos
                try:
                    perfil = self.ctx.ifood(wa_id).usuario()
                    u['nome_ifood'] = perfil.get('nome')
                    nome = nome or (perfil.get('nome') or '').split(' ')[0]
                except ErroMCP as e:
                    print(f'getUser falhou depois do login: {e!r}')
                self.wpp.texto(wa_id, T.logou(nome))
                pend, u['pendente'] = u.get('pendente'), None
                if pend:
                    self.botao(pend['botao']) if pend.get('acao') == 'botao' else self.intencao(pend)
                else:
                    self.perguntar(T.PERGUNTA_PEDIDO, T.MENU, fase='pedido')
            self._protegido(seguir)
        finally:
            self._salvar()

    @property
    def wpp(self):
        return self.ctx.wpp

    def _carregar(self, wa_id):
        u = estado_novo()
        u.update(self.ctx.armazem.get(f'u:{wa_id}') or {})
        return u

    def _salvar(self):
        if self.wa and self.u is not None:
            self.ctx.armazem[f'u:{self.wa}'] = self.u

    def _trivial(self, e):
        if e.tipo != 'texto':
            return False
        r = regra_rapida(e.texto)
        return bool(r and r['acao'] in TRIVIAIS)

    def _debug_reset(self, entradas):
        """Atalho interno: se a pessoa digitar a palavra secreta (env DEBUG_RESET, fora do git),
        desloga do iFood e zera a conversa, em QUALQUER etapa. Vazio = desligado."""
        palavra = os.environ.get('DEBUG_RESET', '')
        if not palavra or palavra == 'PREENCHER':
            return False
        alvo = normalizar(palavra)
        if not any(e.tipo == 'texto' and normalizar(e.texto) == alvo for e in entradas):
            return False
        try:
            self.ctx.sair(self.wa)                      # revoga e remove o token do iFood
            self.ctx.recorrencias.remover_todas(self.wa)
            self.ctx.armazem.pop(f'mock:{self.wa}', None)  # zera o iFood falso (demo)
        except Exception as e:  # noqa: BLE001 - debug não pode quebrar
            print(f'debug reset parcial: {e!r}')
        self.u = estado_novo()
        self.wpp.texto(self.wa, '🧹 [debug] Desconectei do iFood e zerei a conversa. Manda um "oi" pra recomeçar.')
        return True

    def _protegido(self, fn):
        """Nenhum erro chega mudo pra pessoa: login vencido pede login, o resto pede pra tentar."""
        try:
            fn()
        except (PrecisaLogin, SemAutorizacao):
            self.pedir_login(vencido=bool(self.ctx.armazem.get(f'tok:{self.wa}')))
        except ErroMCP as e:
            print(f'MCP {self.wa}: {e!r} {str(e.bruto)[:300] if e.bruto else ""}')
            self.erro_mcp(e)
        except Exception:
            traceback.print_exc()
            try:
                self.perguntar(T.ERRO, [T.B_TENTAR, T.B_INICIO])
            except Exception:  # noqa: BLE001 - nem o aviso com botão saiu: vai texto puro
                traceback.print_exc()
                self.dizer(T.ERRO_SEM_BOTAO)

    # ================================================================== envio

    def perguntar(self, texto, botoes, fase=None, rotulo='Ver opções', imagem=None, rodape=None):
        """Manda texto + botões (até 3) ou lista (4 a 10) e guarda a pergunta.
        botoes: [(id, título)] ou [(id, título, descrição)].
        Se a Meta recusar a mensagem interativa (formato), manda as opções numeradas em texto:
        a pessoa responde o número e a conversa segue (o "2" já vira o 2º botão)."""
        botoes = [tuple(b) for b in botoes]
        try:
            if len(botoes) <= 3:
                self.wpp.botoes(self.wa, texto, [(b[0], b[1]) for b in botoes], imagem=imagem, rodape=rodape)
            else:
                self.wpp.lista(self.wa, texto, rotulo, [(b[0], b[1], b[2] if len(b) > 2 else '') for b in botoes],
                               rodape=rodape)
        except ErroWhatsApp as e:
            if e.status != 400 or not botoes:
                raise
            print(f'interativa recusada, indo de texto numerado: {e}')
            opcoes = '\n'.join(f'{i}️⃣ {b[1]}' + (f' ({b[2]})' if len(b) > 2 and b[2] else '')
                               for i, b in enumerate(botoes, 1))
            self.dizer(f'{texto}\n\n{opcoes}\n\nResponda com o *número* da opção. 🙂')
        self.u['pergunta'] = {'texto': texto, 'botoes': [list(b[:2]) for b in botoes],
                              'titulos': [b[1] for b in botoes]}
        if fase:
            self.u['fase'] = fase

    def dizer(self, texto):
        self.wpp.texto(self.wa, texto)

    def repetir_pergunta(self, prefixo=None):
        p = self.u.get('pergunta') or {}
        if p.get('botoes'):
            if self.u.get('fase') == 'escolhendo':  # cards: reapresenta só o rodapé
                self._rodape_cards(prefixo)
                return
            texto = (prefixo + '\n\n' if prefixo else '') + p.get('texto', '')
            self.perguntar(texto, [tuple(b) for b in p['botoes']])
        else:
            self.menu(prefixo)

    def menu(self, prefixo=None, _arg=None):
        if not self.logado():  # sem login nada funciona: o "menu" de quem não entrou é o botão de entrar
            self.pedir_login()
            return
        texto = prefixo or T.boas_vindas(self._primeiro_nome())
        if prefixo:
            texto += '\n\n' + T.PERGUNTA_PEDIDO
        self.perguntar(texto, T.MENU, fase='pedido')

    def _primeiro_nome(self):
        n = self.u.get('nome_ifood') or self.u.get('nome') or ''
        return n.split(' ')[0] if n else ''

    # ================================================================== roteamento

    def botao(self, bid):
        acao, _, arg = (bid or '').partition(':')
        self.u['ultima_acao'] = ['botao', bid] if acao not in ('tentar',) else self.u.get('ultima_acao')
        rotas = {
            'pedir': self.perguntar_pedido, 'outra': self.perguntar_pedido, 'add': self.perguntar_pedido,
            'inicio': self.menu, 'repetir': self.repetir, 'meu_pedido': self.acompanhar,
            'ajuda': self.ajuda, 'pick': self.escolher_oferta, 'mais': self.mais_opcoes,
            'qtd': self.definir_qtd, 'opt': self.escolher_opcao, 'end': self.escolher_endereco,
            'end_novo': self.pedir_endereco, 'end_lista': self._listar_enderecos, 'cand': self.escolher_candidato,
            'compl_nao': self.sem_complemento, 'fim': self.finalizar, 'tirar': self.perguntar_tirar,
            'rem': self.tirar_item, 'ent': self.escolher_entrega, 'pag': self.escolher_pagamento,
            'cpf_nao': self.sem_cpf, 'ok': self.confirmar, 'mudar': self.mudar,
            'mud': self.mudar_o_que, 'cancelar': self.cancelar, 'rec': self.definir_recorrencia,
            'lem': self.responder_lembrete, 'pular': self.pular_item, 'reped': self.repetir_pedido,
            'apagar_sim': self.apagar, 'apagar_nao': self.menu, 'login': self.reenviar_login,
            'tentar': self.tentar_de_novo, 'nada': lambda _a=None: None,
        }
        fn = rotas.get(acao)
        if not fn:
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if acao in ('pick', 'mais', 'qtd', 'opt', 'fim', 'ok', 'reped', 'rem', 'ent', 'pag', 'cand',
                    'end') and not self.exigir_login(['botao', bid]):
            return
        fn(arg) if acao not in ('inicio', 'apagar_nao') else fn()

    def livre(self, entradas):
        u = self.u
        textos = [e.texto for e in entradas if e.tipo in ('texto', 'localizacao') and e.texto]
        texto = '\n'.join(textos).strip()
        midias = [e for e in entradas if e.tipo in ('audio', 'imagem')]
        if not texto and not midias:
            self.repetir_pergunta(T.NAO_ENTENDI)
            return
        fase = u.get('fase')

        if fase == 'cpf':  # CPF nunca vai pra IA
            if midias and not texto:
                self.dizer('Por segurança, escreva o CPF com os números, por favor. 🙂')
                return
            self.receber_cpf(texto)
            return
        if not midias:
            if fase == 'endereco':
                r = regra_rapida(texto)
                if r and r['acao'] in ('inicio', 'cancelar', 'ajuda', 'sair', 'apagar_dados'):
                    self.intencao(r)
                else:
                    u['ultima_acao'] = ['endereco', texto]  # "Tentar de novo" reusa o que ela digitou
                    self.receber_endereco(texto)
                return
            if fase == 'complemento':
                r = regra_rapida(texto)
                if r and r['acao'] == 'nao':
                    self.sem_complemento()
                else:
                    self.receber_complemento(texto)
                return
            if fase == 'bairro':
                self.receber_bairro(texto)
                return
            titulos = (u.get('pergunta') or {}).get('titulos') or []
            i = igual_a_botao(texto, titulos)
            if i is not None and len(texto) <= 40:
                self.botao(u['pergunta']['botoes'][i][0])
                return
            r = regra_rapida(texto)
            if r:
                self.intencao(r)
                return

        partes = [('texto', texto)] if texto else []
        for m in midias:
            try:
                mime, dados = self.ctx.baixar_midia(m.media_id)
            except Exception as e:  # noqa: BLE001
                print(f'baixar mídia falhou: {e!r}')
                continue
            partes.append(('arquivo', _mime_aceito(mime or m.mime), dados))
            if m.texto:
                partes.append(('texto', m.texto))
        if not partes:
            self.dizer(T.AUDIO_RUIM)
            return
        try:
            intent = interpretar(self.ctx.llm, u, partes)
        except ErroLLM as e:
            print(f'LLM falhou: {e!r}')
            if texto and fase in ('inicio', 'pedido', 'escolhendo', 'mais', None):
                intent = {'acao': 'comprar', 'itens': [{'termo': texto[:60], 'quantidade': None,
                                                        'tipo_loja': 'MERCADO', 'observacao': None}]}
            elif midias and not texto:
                self.dizer(T.AUDIO_RUIM)
                return
            else:
                self.repetir_pergunta(T.NAO_ENTENDI)
                return
        if intent.get('transcricao'):
            print(f'transcrição {self.wa}: {intent["transcricao"][:200]}')
        self.intencao(intent)

    def intencao(self, it):
        u = self.u
        a = it.get('acao')
        fase = u.get('fase')
        botoes = (u.get('pergunta') or {}).get('botoes') or []
        if a not in ('sim', 'nao', 'numero', 'escolher', 'quantidade', 'nao_entendi', 'fora_do_escopo',
                     'agradecer', 'saudacao'):
            u['ultima_acao'] = ['intencao', it]

        if a in ('numero', 'escolher', 'quantidade'):
            n = it.get('numero')
            if fase == 'quantidade' and n:
                self.definir_qtd(str(n))
            elif n and fase == 'escolhendo':
                visiveis = self._visiveis()
                if 1 <= n <= len(visiveis):
                    self.botao(visiveis[n - 1])
                else:
                    self._rodape_cards(f'Escolha entre 1 e {len(visiveis)}, ou toque em *Quero esse*. 🙂')
            elif n and 1 <= n <= len(botoes):
                self.botao(botoes[n - 1][0])
            else:
                self.repetir_pergunta(T.NAO_ENTENDI)
        elif a == 'sim':
            if fase == 'confirmar':
                self.botao(botoes[0][0] if botoes else 'nada')
            elif fase == 'apagar':
                self.apagar()
            elif fase == 'mais':
                self.perguntar_pedido()
            elif fase == 'login':
                self.reenviar_login()
            elif fase == 'recorrencia':
                self.definir_recorrencia('7')
            elif botoes and fase in ('endereco_lista', 'repetir_lista'):
                self.botao(botoes[0][0])
            else:
                self.perguntar_pedido()
        elif a == 'nao':
            if fase == 'mais':
                self.finalizar()
            elif fase == 'confirmar':
                self.mudar()
            elif fase == 'complemento':
                self.sem_complemento()
            elif fase == 'recorrencia':
                self.definir_recorrencia('0')
            elif fase == 'apagar':
                self.menu()
            else:
                self.menu('Tudo bem! 🙂')
        elif a == 'comprar':
            self.iniciar_compra(it.get('itens') or [])
        elif a == 'mais_opcoes':
            if u.get('lista_atual'):
                self.mais_opcoes(u['lista_atual'])
            else:
                self.perguntar_pedido()
        elif a == 'finalizar':
            self.finalizar()
        elif a == 'ver_pedido':
            self.mostrar_carrinho()
        elif a == 'tirar_item':
            self.perguntar_tirar()
        elif a == 'cancelar':
            self.cancelar()
        elif a == 'acompanhar':
            self.acompanhar()
        elif a == 'repetir':
            self.repetir()
        elif a == 'endereco':
            if it.get('texto'):
                self.receber_endereco(it['texto'])
            else:
                self.pedir_endereco()
        elif a == 'ajuda':
            self.ajuda()
        elif a == 'inicio':
            self.menu()
        elif a == 'saudacao':
            if fase in NO_MEIO_DO_PEDIDO and botoes:
                self.repetir_pergunta('Olá! 😊 Estávamos aqui:')
            else:
                self.saudar()
        elif a == 'agradecer':
            if fase in ('inicio', 'pedido', 'acompanhando', None):
                self.dizer(T.DE_NADA)
            else:
                self.repetir_pergunta('😊')
        elif a == 'sair':
            self.sair()
        elif a == 'apagar_dados':
            self.perguntar(T.APAGAR_CONFIRMA, [T.B_APAGAR_SIM, T.B_APAGAR_NAO], fase='apagar')
        elif a == 'parar_lembrete':
            self.parar_lembretes()
        elif a == 'fora_do_escopo':
            self.repetir_pergunta(T.FORA_DO_ESCOPO) if botoes else self.menu(T.FORA_DO_ESCOPO)
        else:
            self.repetir_pergunta(T.NAO_ENTENDI) if botoes else self.menu(T.NAO_ENTENDI)

    def tentar_de_novo(self, _arg=None):
        ult = self.u.get('ultima_acao')
        if not ult:
            self.menu()
        elif ult[0] == 'botao':
            self.botao(ult[1])
        elif ult[0] == 'endereco':
            self.receber_endereco(ult[1])
        else:
            self.intencao(ult[1])

    # ================================================================== login e conta

    def logado(self):
        return self.ctx.logado(self.wa)

    def exigir_login(self, pendente):
        """pendente: o que retomar depois do login, ['botao', id] ou uma intenção (dict)."""
        if self.logado():
            return True
        if isinstance(pendente, (list, tuple)) and pendente and pendente[0] == 'botao':
            pendente = {'acao': 'botao', 'botao': pendente[1]}
        self.u['pendente'] = pendente
        self.pedir_login()
        return False

    def pedir_login(self, vencido=False):
        texto = T.LOGIN_DE_NOVO if vencido else T.LOGIN
        if not vencido and self.u.get('fase') in ('inicio', None):
            texto = T.boas_vindas(self._primeiro_nome()) + '\n\n' + texto
        self.wpp.link(self.wa, texto, T.LOGIN_BOTAO, self.ctx.link_login(self.wa), rodape=T.LOGIN_RODAPE)
        self.u['fase'] = 'login'
        self.u['pergunta'] = {'texto': texto, 'botoes': [], 'titulos': []}

    def reenviar_login(self, _arg=None):
        if self.logado():
            self.menu()
        else:
            self.pedir_login()

    def saudar(self):
        if not self.logado():
            self.pedir_login()
            return
        if self._lembrete_pendente():
            return
        self.menu()

    def ajuda(self, _arg=None):
        self.perguntar(T.AJUDA, T.MENU, fase='pedido')

    def sair(self):
        self.ctx.sair(self.wa)
        self.u.update({'fase': 'inicio', 'pergunta': {}, 'carrinho': None, 'fila': [], 'escolha': None})
        self.dizer(T.SAIU)

    def apagar(self, _arg=None):
        self.ctx.apagar(self.wa)
        self.dizer(T.APAGADO)
        self.u = None  # _salvar não regrava

    # ================================================================== pedido: começo

    def perguntar_pedido(self, _arg=None):
        if not self.exigir_login(None):
            return
        car = self.u.get('carrinho')
        texto = T.PERGUNTA_PEDIDO
        if car and car.get('itens'):
            texto = 'O que mais você quer? 😊\nPode escrever ou mandar áudio 🎤'
        botoes = [T.B_FINALIZAR, T.B_INICIO] if car and car.get('itens') else [T.B_REPETIR, T.B_MEU_PEDIDO]
        self.perguntar(texto, botoes, fase='pedido')

    def iniciar_compra(self, itens):
        u = self.u
        if not itens:
            self.perguntar_pedido()
            return
        if not self.exigir_login({'acao': 'comprar', 'itens': itens}):
            return
        if not self.garantir_endereco({'acao': 'comprar', 'itens': itens}):
            return
        u['fila'] = list(itens[1:])
        if len(itens) > 1:
            self.dizer(T.lista_de_compras([i['termo'] for i in itens]))
        self.buscar(itens[0])

    # ================================================================== endereço

    def garantir_endereco(self, pendente):
        """Regra da doc (listAddresses.agentHints): 1 endereço = usa e avisa, sem perguntar;
        vários com histórico = sugere o provável e CONFIRMA numa pergunta; vários sem histórico
        = mostra as opções; nenhum = pede o endereço e salva na conta."""
        u = self.u
        if u.get('endereco') and u['endereco'].get('lat') is not None:
            return True
        ends = self.ctx.ifood(self.wa).enderecos()
        if len(ends) == 1:
            u['endereco'] = self._com_coordenadas(ends[0])
            return bool(u['endereco'])
        if ends:
            u['pendente'] = pendente
            u['enderecos'] = ends[:9]
            melhor = next((i for i, e in enumerate(ends) if e.get('ultimo')), None)
            if melhor is None:
                melhor = next((i for i, e in enumerate(ends) if e.get('mais_usado')), None)
            if melhor is not None and melhor < 9:
                e = ends[melhor]
                self.perguntar(f'🏠 Entrego em *{e.get("apelido")}*?\n{e.get("texto", "")}',
                               [(f'end:{melhor}', '✅ Sim, aqui'), ('end_lista', '📍 Outro endereço')],
                               fase='endereco_lista')
            else:
                self._listar_enderecos()
            return False
        u['pendente'] = pendente
        self.pedir_endereco()
        return False

    def _listar_enderecos(self, _arg=None):
        ends = self.u.get('enderecos') or []
        botoes = [(f'end:{i}', e.get('apelido') or f'Endereço {i + 1}', e.get('texto', ''))
                  for i, e in enumerate(ends[:9])] + [T.B_ENDERECO_NOVO + ('Cadastrar outro',)]
        self.perguntar(T.QUAL_ENDERECO, botoes, fase='endereco_lista', rotulo='Ver endereços')

    def _com_coordenadas(self, end):
        """A busca precisa de latitude/longitude. A doc avisa que o listAddresses pode vir sem
        `coordinates`: aí geocodifica o texto do endereço (o passo 1 do createAddress não salva nada)."""
        if end.get('lat') is not None:
            return end
        try:
            cands = self.ctx.ifood(self.wa).geocodificar(end.get('texto') or '').get('candidatos') or []
        except ErroMCP as e:
            print(f'geocodificar endereço salvo falhou: {e!r}')
            cands = []
        if cands and cands[0].get('lat') is not None:
            return {**end, 'lat': cands[0]['lat'], 'lng': cands[0]['lng']}
        norm = self.ctx.normalizar_endereco(end.get('texto') or '')
        if norm and norm['lat'] is not None:
            return {**end, 'lat': norm['lat'], 'lng': norm['lng']}
        self.dizer('Não consegui achar a localização desse endereço. 😕 Vamos cadastrar de novo?')
        self.pedir_endereco()
        return None

    def pedir_endereco(self, _arg=None):
        self.u['novo_endereco'] = None
        self.dizer(T.PEDIR_ENDERECO)
        self.u['fase'] = 'endereco'
        self.u['pergunta'] = {'texto': T.PEDIR_ENDERECO, 'botoes': [], 'titulos': []}

    def escolher_endereco(self, arg):
        ends = self.u.get('enderecos') or []
        try:
            end = ends[int(arg)]
        except (ValueError, IndexError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        end = self._com_coordenadas(end)
        if not end:
            return
        self.u['endereco'] = end
        self._endereco_mudou()

    def _perto(self):
        """Onde a pessoa costuma estar, pra puxar o geocodificador grátis pra cidade certa."""
        for e in [self.u.get('endereco')] + list(self.u.get('enderecos') or []):
            if e and e.get('lat') is not None:
                return e['lat'], e['lng']
        return None

    def _geocodificar_ifood(self, consultas):
        """Passo 1 do createAddress com a 1ª consulta que der resultado."""
        r = {}
        for consulta in dict.fromkeys(consultas):
            try:
                r = self.ctx.ifood(self.wa).geocodificar(consulta)
            except ErroMCP as e:
                if str(e.codigo) not in ('PLACE_NOT_FOUND', 'MISSING_ADDRESS'):
                    raise
                r = {}
            if r.get('criado') or r.get('candidatos'):
                break
        return r

    def receber_endereco(self, texto):
        # o geocode do iFood erra com texto bagunçado: um geocodificador grátis arruma antes
        # ("rua episcopal 1500 ap 3 sanca" -> "Rua Episcopal, 1500 - Centro, São Carlos - SP").
        # Invisível pra pessoa; se ele não achar, vai o texto dela mesmo
        norm = self.ctx.normalizar_endereco(texto, self._perto())
        r = self._geocodificar_ifood([norm['texto'], texto] if norm else [texto])
        if r.get('criado'):
            self._endereco_salvo(r['criado'])
            return
        cands = r.get('candidatos') or []
        for c in cands if norm else []:  # completa o que o iFood não devolveu (evita perguntar o bairro)
            if not c.get('bairro') and norm['bairro']:
                c['bairro'] = norm['bairro']
            if c.get('lat') is None and norm['lat'] is not None:
                c['lat'], c['lng'] = norm['lat'], norm['lng']
        if not cands:
            self.dizer(T.ENDERECO_NAO_ACHEI)
            self.u['fase'] = 'endereco'
            return
        self.u['novo_endereco'] = {'texto': texto, 'candidatos': cands[:9], 'escolhido': None, 'bairro': None}
        if len(cands) == 1:
            self.escolher_candidato('0')
            return
        # candidatos costumam ter a MESMA rua e número (muda o bairro): o endereço completo vai
        # no texto, numerado, e o botão leva o número e o bairro
        lista = '\n'.join(f'{i}️⃣ {c.get("texto", "")}' for i, c in enumerate(cands[:9], 1))
        # id interno é cand:<índice do array> (0-based); o rótulo mostra o número que a pessoa vê (1-based)
        botoes = [(f'cand:{i}', f'{i + 1} · {c.get("bairro") or c.get("titulo") or "Endereço"}', c.get('texto', ''))
                  for i, c in enumerate(cands[:9])]
        self.perguntar(f'{T.ESCOLHA_ENDERECO}\n\n{lista}', botoes, fase='endereco_escolha', rotulo='Ver endereços')

    def escolher_candidato(self, arg):
        novo = self.u.get('novo_endereco') or {}
        try:
            novo['escolhido'] = novo['candidatos'][int(arg)]
        except (KeyError, ValueError, IndexError, TypeError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        self.u['novo_endereco'] = novo
        if not novo['escolhido'].get('bairro'):  # geocodificação sem bairro: a doc manda perguntar
            self.dizer(f'📍 {novo["escolhido"].get("texto", "")}\n\nQual é o *bairro*? Escreva aqui. 🙂')
            self.u['fase'] = 'bairro'
            self.u['pergunta'] = {'texto': 'Qual é o bairro?', 'botoes': [], 'titulos': []}
            return
        self.perguntar(f'📍 {novo["escolhido"].get("texto", "")}\n\n{T.PEDIR_COMPLEMENTO}',
                       [T.B_SEM_COMPLEMENTO], fase='complemento')

    def receber_bairro(self, texto):
        novo = self.u.get('novo_endereco') or {}
        if not novo.get('escolhido'):
            self.pedir_endereco()
            return
        novo['bairro'] = ' '.join(texto.split())[:60]
        self.u['novo_endereco'] = novo
        self.perguntar(T.PEDIR_COMPLEMENTO, [T.B_SEM_COMPLEMENTO], fase='complemento')

    def sem_complemento(self, _arg=None):
        self.receber_complemento('')

    def receber_complemento(self, texto):
        novo = self.u.get('novo_endereco') or {}
        cand = novo.get('escolhido')
        if not cand:
            self.pedir_endereco()
            return
        apelido = 'Casa' if not self.u.get('enderecos') else f'Endereço {len(self.u["enderecos"]) + 1}'
        try:
            end = self.ctx.ifood(self.wa).criar_endereco(cand, complemento=texto.strip()[:80], apelido=apelido,
                                                         bairro=novo.get('bairro'))
        except ErroMCP as e:
            if str(e.codigo) == 'MISSING_NEIGHBORHOOD':
                self.dizer('Faltou o *bairro*. Qual é o bairro? Escreva aqui. 🙂')
                self.u['fase'] = 'bairro'
                return
            raise
        if end.get('lat') is None:
            end.update({'lat': cand.get('lat'), 'lng': cand.get('lng')})
        self._endereco_salvo(end)

    def _endereco_salvo(self, end):
        self.u['endereco'] = end
        self.u['novo_endereco'] = None
        self.u['enderecos'] = None
        self.dizer(T.endereco_salvo(end.get('apelido') or 'Casa', end.get('texto', '')))
        self._endereco_mudou()

    def _endereco_mudou(self):
        """Endereço novo: se já tinha carrinho, refaz pro endereço novo; senão retoma o pendente."""
        u = self.u
        car = u.get('carrinho')
        if car and car.get('itens'):
            novo = self.ctx.ifood(self.wa).criar_carrinho(
                car['loja_id'], u['endereco']['id'],
                [{'item_id': i['item_id'], 'qtd': i['qtd'], 'opcoes': i.get('opcoes') or [],
                  'obs': i.get('obs')} for i in car['itens']])
            novo['loja'] = car.get('loja')
            u['carrinho'] = novo
            self.finalizar()
            return
        pend, u['pendente'] = u.get('pendente'), None
        if pend:
            self.intencao(pend) if pend.get('acao') != 'botao' else self.botao(pend['botao'])
        else:
            self.perguntar_pedido()

    # ================================================================== busca e cards

    def buscar(self, pedido):
        """pedido: {termo, quantidade, tipo_loja, observacao}. Busca uma vez e guarda a lista."""
        u = self.u
        car = u.get('carrinho') or {}
        loja_id = car.get('loja_id') if car.get('itens') else None
        ofertas, proxima = self.ctx.ifood(self.wa).buscar(
            pedido['termo'], u['endereco'], pedido.get('tipo_loja') or 'MERCADO', loja_id=loja_id)
        ofertas = ranking.ordenar(ofertas, pedido)
        u['atual'] = pedido
        if not ofertas:
            botoes = [T.B_PULAR, T.B_ESCREVER] if u.get('fila') else [T.B_ESCREVER, T.B_INICIO]
            self.perguntar(T.nao_achei(pedido['termo'], car.get('loja') if loja_id else None), botoes,
                           fase='pedido')
            return
        u['contador'] = int(u.get('contador') or 0) + 1
        lid = f'L{u["contador"]}'
        u['listas'][lid] = {'termo': pedido['termo'], 'ofertas': ofertas, 'pos': 0, 'proxima': proxima,
                            'loja_id': loja_id, 'tipo_loja': pedido.get('tipo_loja'), 'pedido': pedido}
        for velha in sorted(u['listas'], key=lambda k: int(k[1:]))[:-LISTAS_GUARDADAS]:
            u['listas'].pop(velha, None)
        u['lista_atual'] = lid
        self.mostrar_pagina(lid)

    def mostrar_pagina(self, lid):
        u = self.u
        lst = u['listas'][lid]
        pagina = lst['ofertas'][lst['pos']:lst['pos'] + POR_PAGINA]
        inicio = lst['pos']
        lst['pos'] += len(pagina)
        if inicio == 0 and u.get('endereco') and not (u.get('carrinho') or {}).get('itens'):
            self.dizer(T.entregando_em(u['endereco'].get('apelido') or 'Casa', u['endereco'].get('texto', '')))
        for i, of in enumerate(pagina, start=inicio):
            self.wpp.botoes(self.wa, T.card(of), [(f'pick:{lid}:{i}', T.B_QUERO)],
                            imagem=of.get('imagem') or None)
        u['fase'] = 'escolhendo'
        u['visiveis'] = [f'pick:{lid}:{i}' for i in range(inicio, inicio + len(pagina))]
        self._rodape_cards()

    def _visiveis(self):
        return self.u.get('visiveis') or []

    def _rodape_cards(self, prefixo=None):
        u = self.u
        lid = u.get('lista_atual')
        lst = u['listas'].get(lid) if lid else None
        tem_mais = bool(lst and (lst['pos'] < len(lst['ofertas']) or lst.get('proxima')))
        texto = (prefixo + '\n\n' if prefixo else '') + T.rodape_opcoes(tem_mais)
        botoes = ([(f'mais:{lid}', T.B_MAIS)] if tem_mais else []) + [T.B_OUTRA]
        if u.get('fila'):
            botoes.append(T.B_PULAR)
        self.wpp.botoes(self.wa, texto, botoes)
        nomes = []
        for pid in self._visiveis():
            _, l2, i = pid.split(':')
            try:
                nomes.append(u['listas'][l2]['ofertas'][int(i)]['nome'])
            except (KeyError, IndexError, ValueError):
                nomes.append('')
        u['pergunta'] = {'texto': texto, 'botoes': [[pid, n] for pid, n in zip(self._visiveis(), nomes)]
                         + [list(b) for b in botoes], 'titulos': nomes + [b[1] for b in botoes]}

    def mais_opcoes(self, lid):
        u = self.u
        lst = u['listas'].get(lid or '')
        if not lst:
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        u['lista_atual'] = lid
        if lst['pos'] >= len(lst['ofertas']):
            if lst.get('proxima'):  # acabou o que já veio: aí sim busca a página seguinte
                novas, prox = self.ctx.ifood(self.wa).buscar(
                    lst['termo'], u['endereco'], lst.get('tipo_loja') or 'MERCADO',
                    loja_id=lst.get('loja_id'), pagina=lst['proxima'])
                ja = {o['item_id'] for o in lst['ofertas']}
                lst['ofertas'] += [o for o in ranking.ordenar(novas, lst.get('pedido') or {}) if o['item_id'] not in ja]
                lst['proxima'] = prox
            if lst['pos'] >= len(lst['ofertas']):
                lst['proxima'] = None
                self.perguntar(T.FIM_DAS_OPCOES, [T.B_OUTRA, T.B_INICIO], fase='pedido')
                return
        self.mostrar_pagina(lid)

    def pular_item(self, _arg=None):
        self._proximo_da_fila(pulou=True)

    # ================================================================== escolha do item

    def escolher_oferta(self, arg):
        u = self.u
        try:
            lid, idx = arg.split(':')
            of = u['listas'][lid]['ofertas'][int(idx)]
        except (KeyError, ValueError, IndexError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        car = u.get('carrinho') or {}
        if car.get('itens') and car.get('loja_id') != of['loja_id']:
            # carrinho é de uma loja só: o item de outra loja entra num pedido separado depois
            self.perguntar(f'Seu pedido já é do *{car.get("loja")}*. Esse item é de outra loja. 🙂\n'
                           'Termine este pedido primeiro, depois a gente faz outro.',
                           [T.B_FINALIZAR, T.B_OUTRA])
            return
        item = self.ctx.ifood(self.wa).item(of['item_id'], of['loja_id'], u['endereco'])
        item['nome'] = item.get('nome') or of['nome']
        pedido = (u['listas'][lid].get('pedido') or u.get('atual') or {})
        u['escolha'] = {'oferta': of, 'item': item, 'qtd': pedido.get('quantidade'),
                        'obs': pedido.get('observacao'), 'opcoes': [], 'grupo': 0, 'feitas': 0}
        self._proximo_passo_da_escolha()

    def _proximo_passo_da_escolha(self):
        u = self.u
        esc = u['escolha']
        grupos = [g for g in esc['item'].get('grupos') or [] if g.get('min', 0) > 0]
        while esc['grupo'] < len(grupos):
            g = grupos[esc['grupo']]
            if esc['feitas'] < g['min']:
                self._perguntar_opcao(g, esc['feitas'] + 1, g['min'])
                return
            esc['grupo'] += 1
            esc['feitas'] = 0
        if not esc.get('qtd'):
            nome = esc['item'].get('nome') or esc['oferta']['nome']
            self.perguntar(T.quantos(nome), [('qtd:1', '1'), ('qtd:2', '2'), ('qtd:3', '3')], fase='quantidade')
            return
        self.adicionar()

    def _perguntar_opcao(self, grupo, n, total):
        ops = grupo.get('opcoes') or []
        botoes = []
        for j, op in enumerate(ops[:10]):
            extra = f' +{T.reais(op["preco"])}' if op.get('preco') else ''
            botoes.append((f'opt:{j}', op['nome'], extra.strip()))
        if len(botoes) <= 3:
            botoes = [(i, t + d) if d else (i, t) for i, t, d in botoes]
        self.perguntar(T.escolha_opcao(grupo.get('nome') or 'opção', n, total), botoes, fase='opcao',
                       rotulo='Ver opções')

    def escolher_opcao(self, arg):
        u = self.u
        esc = u.get('escolha')
        if not esc:
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        grupos = [g for g in esc['item'].get('grupos') or [] if g.get('min', 0) > 0]
        try:
            g = grupos[esc['grupo']]
            op = g['opcoes'][int(arg)]
        except (IndexError, ValueError, KeyError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        esc['opcoes'].append({'grupo_id': g.get('id'), 'opcao_id': op['id'], 'nome': op['nome'],
                              'preco': op.get('preco')})
        esc['feitas'] += 1
        self._proximo_passo_da_escolha()

    def definir_qtd(self, arg):
        esc = self.u.get('escolha')
        if not esc:
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        n = numero_em(arg) if not str(arg).isdigit() else int(arg)
        if not n or n < 1 or n > 50:
            self.perguntar('Me diga um número de 1 a 50. 🙂', [('qtd:1', '1'), ('qtd:2', '2'), ('qtd:3', '3')],
                           fase='quantidade')
            return
        esc['qtd'] = n
        self.adicionar()

    def adicionar(self):
        u = self.u
        esc = u['escolha']
        of = esc['oferta']
        api = self.ctx.ifood(self.wa)
        car = u.get('carrinho')
        linha = {'item_id': of['item_id'], 'qtd': int(esc['qtd']), 'opcoes': esc['opcoes'], 'obs': esc.get('obs')}
        if not car or not car.get('id'):
            novo = api.criar_carrinho(of['loja_id'], u['endereco']['id'], [linha])
            antes = {}
        else:
            antes = {i['cart_item_id']: i for i in car.get('itens') or []}
            novo = api.adicionar(car['id'], linha)
        novo['loja'] = novo.get('loja') or (car or {}).get('loja') or of.get('loja')
        # guardamos as opções escolhidas de cada linha pra conseguir refazer o carrinho depois
        # (mudança de endereço); a linha nova é o cartItemId que não existia antes
        for it in novo.get('itens') or []:
            velho = antes.get(it['cart_item_id'])
            if velho:
                it['opcoes'], it['obs'] = velho.get('opcoes'), velho.get('obs')
            elif it.get('item_id') == of['item_id']:
                it['opcoes'], it['obs'] = esc['opcoes'], esc.get('obs')
        u['carrinho'] = novo
        u['escolha'] = None
        nome = esc['item'].get('nome') or of['nome']
        if esc['opcoes']:
            nome += ' (' + ', '.join(o['nome'] for o in esc['opcoes']) + ')'
        self.dizer(T.colocado(esc['qtd'], nome))
        self._proximo_da_fila()

    def _proximo_da_fila(self, pulou=False):
        u = self.u
        fila = u.get('fila') or []
        if fila:
            prox = fila.pop(0)
            u['fila'] = fila
            if not pulou:
                self.dizer(T.proximo_da_lista(prox['termo']))
            self.buscar(prox)
            return
        car = u.get('carrinho') or {}
        if not car.get('itens'):
            self.perguntar_pedido()
            return
        self.perguntar(T.mais_alguma(car.get('total') or car.get('subtotal')),
                       [T.B_FINALIZAR, T.B_MAIS_COISAS, T.B_TIRAR], fase='mais')

    def mostrar_carrinho(self):
        car = self.u.get('carrinho') or {}
        if not car.get('itens'):
            self.perguntar(T.PERGUNTA_PEDIDO, T.MENU, fase='pedido')
            return
        linhas = '\n'.join(f'• {i["qtd"]}x {i["nome"]}' for i in car['itens'])
        self.perguntar(f'🧺 *Seu pedido:*\n{linhas}\n\n{T.mais_alguma(car.get("total") or car.get("subtotal"))}',
                       [T.B_FINALIZAR, T.B_MAIS_COISAS, T.B_TIRAR], fase='mais')

    def perguntar_tirar(self, _arg=None):
        car = self.u.get('carrinho') or {}
        itens = car.get('itens') or []
        if not itens:
            self.perguntar_pedido()
            return
        botoes = [(f'rem:{i}', it['nome'], f'{it["qtd"]}x · {T.reais(it.get("preco_total"))}')
                  for i, it in enumerate(itens[:10])]
        if len(botoes) <= 3:
            botoes = [(b[0], b[1]) for b in botoes]
        self.perguntar('Qual item eu tiro? 👇', botoes, fase='tirar', rotulo='Ver itens')

    def tirar_item(self, arg):
        u = self.u
        car = u.get('carrinho') or {}
        try:
            it = car['itens'][int(arg)]
        except (KeyError, IndexError, ValueError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        api = self.ctx.ifood(self.wa)
        if len(car['itens']) == 1:
            # carrinho vazio dá erro no submitOrder: esquece o carrinho em vez de esvaziar
            u['carrinho'] = None
            self.dizer(f'🗑️ Tirei *{it["nome"]}*. Seu pedido ficou vazio.')
            self.perguntar_pedido()
            return
        novo = api.remover(car['id'], it['cart_item_id'])
        if not novo or not novo.get('itens'):
            u['carrinho'] = None
            self.dizer(f'🗑️ Tirei *{it["nome"]}*. Seu pedido ficou vazio.')
            self.perguntar_pedido()
            return
        novo['loja'] = novo.get('loja') or car.get('loja')
        guardadas = {i['cart_item_id']: (i.get('opcoes'), i.get('obs')) for i in car['itens']}
        for i in novo['itens']:
            i['opcoes'], i['obs'] = guardadas.get(i['cart_item_id'], ([], None))
        u['carrinho'] = novo
        self.dizer(f'🗑️ Tirei *{it["nome"]}*.')
        self._proximo_da_fila()

    # ================================================================== fechamento

    def finalizar(self, _arg=None):
        u = self.u
        car = u.get('carrinho')
        if not car or not car.get('itens'):
            self.perguntar('Seu pedido ainda está vazio. 🙂\n' + T.PERGUNTA_PEDIDO, T.MENU, fase='pedido')
            return
        u['fila'] = []
        api = self.ctx.ifood(self.wa)
        if car.get('minimo') and (car.get('subtotal') or 0) < car['minimo']:
            self.perguntar(f'O pedido mínimo do *{car.get("loja")}* é {T.reais(car["minimo"])}. 🙂\n'
                           f'Seu pedido está em {T.reais(car.get("subtotal"))}. Quer colocar mais alguma coisa?',
                           [T.B_MAIS_COISAS, T.B_CANCELAR], fase='mais')
            return
        # 1. entrega (a doc exige getCartDeliveryMethods -> setCartDelivery antes do pagamento).
        # Escolhe sozinho a entrega padrão: uma pergunta a menos, e o resumo mostra prazo e taxa.
        if not car.get('entrega'):
            entregas = api.entregas(car['id'])
            if not entregas:
                self.perguntar(T.LOJA_FECHADA + '\nVamos procurar em outra loja?', [T.B_OUTRA, T.B_INICIO], fase='pedido')
                u['carrinho'] = None
                return
            self._definir_entrega(entregas[0])
        car = u['carrinho']
        # 2. pagamento: só o que um bot consegue pagar (PIX e vales); repete o da última vez
        if not car.get('pagamento'):
            formas = api.pagamentos(car['loja_id'])
            pref = u.get('pagamento_preferido') or {}
            igual = next((f for f in formas if f['tipo'] == pref.get('tipo')), None)
            if igual:
                self._definir_pagamento(igual)
            elif len(formas) == 1:
                self._definir_pagamento(formas[0])
            elif not formas:
                self.perguntar('Essa loja não aceita PIX nem vale por aqui. 😕\nVamos procurar em outra loja?',
                               [T.B_OUTRA, T.B_INICIO], fase='pedido')
                u['carrinho'] = None
                return
            else:
                u['formas'] = formas[:9]
                botoes = [(f'pag:{i}', f['nome']) for i, f in enumerate(formas[:9])]
                self.perguntar(T.QUAL_PAGAMENTO, botoes, fase='pagamento', rotulo='Ver formas')
                return
        car = u['carrinho']
        # 3. cupom: aplica o melhor que existir (desconto nunca atrapalha)
        if 'cupom' not in car:
            car['cupom'] = None
            try:
                cupons = api.cupons(car['id'], car.get('subtotal'))
                if cupons:
                    melhor = max(cupons, key=lambda c: c.get('valor') or 0)
                    self._atualizar_carrinho(api.aplicar_cupom(car['id'], melhor))
                    u['carrinho']['cupom'] = melhor
            except ErroMCP as e:
                print(f'cupom ignorado: {e!r}')
        # 4. CPF: primeiro o da conta iFood (escopo advanced); só pergunta se não tiver, e uma vez só
        if u.get('cpf') is None:
            try:
                cpf = cpf_em(api.usuario().get('cpf') or '')
            except ErroMCP:
                cpf = None
            if cpf:
                u['cpf'] = cpf
            else:
                self.perguntar(T.PEDIR_CPF, [T.B_SEM_CPF], fase='cpf')
                return
        self.mostrar_resumo()

    def _atualizar_carrinho(self, novo):
        """Troca os números do carrinho pelos que o iFood devolveu, sem perder o que é nosso
        (loja, entrega, pagamento, cupom e as opções escolhidas de cada linha)."""
        car = self.u['carrinho']
        if not novo:
            return car
        guardadas = {i.get('cart_item_id'): (i.get('opcoes'), i.get('obs')) for i in car.get('itens') or []}
        for i in novo.get('itens') or []:
            i['opcoes'], i['obs'] = guardadas.get(i.get('cart_item_id'), ([], None))
        for k in ('itens', 'subtotal', 'taxa_entrega', 'taxas', 'desconto', 'total', 'minimo'):
            if novo.get(k) is not None:
                car[k] = novo[k]
        return car

    def _definir_entrega(self, ent):
        car = self.u['carrinho']
        self._atualizar_carrinho(self.ctx.ifood(self.wa).definir_entrega(car['id'], ent['id']))
        car['entrega'] = ent

    def _definir_pagamento(self, forma):
        car = self.u['carrinho']
        self._atualizar_carrinho(self.ctx.ifood(self.wa).definir_pagamento(car['id'], forma))
        car['pagamento'] = forma
        self.u['pagamento_preferido'] = forma

    def escolher_entrega(self, arg):
        try:
            ent = (self.u.get('entregas') or [])[int(arg)]
        except (ValueError, IndexError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if not self.u.get('carrinho'):
            self.menu()
            return
        self._definir_entrega(ent)
        self.finalizar()

    def escolher_pagamento(self, arg):
        try:
            forma = (self.u.get('formas') or [])[int(arg)]
        except (ValueError, IndexError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if not self.u.get('carrinho'):
            self.menu()
            return
        self._definir_pagamento(forma)
        self.finalizar()

    def receber_cpf(self, texto):
        cpf = cpf_em(texto)
        if cpf:
            self.u['cpf'] = cpf
            self.finalizar()
            return
        t = normalizar(texto)
        if t in ('nao', 'sem cpf', 'sem', 'nao quero', 'n', 'pular', 'nao tenho'):
            self.sem_cpf()
            return
        self.perguntar(T.CPF_INVALIDO, [T.B_SEM_CPF], fase='cpf')

    def sem_cpf(self, _arg=None):
        self.u['cpf'] = ''
        self.finalizar()

    def mostrar_resumo(self):
        u = self.u
        car = u['carrinho']
        try:  # a doc pede getCart pra confirmar o estado final antes do submitOrder
            self._atualizar_carrinho(self.ctx.ifood(self.wa).carrinho(car['id']))
        except ErroMCP as e:
            if 'NOT_FOUND' in str(e.codigo):
                raise
            print(f'getCart antes do resumo falhou: {e!r}')
        texto = T.resumo(car, u.get('endereco'), car.get('entrega'), car.get('pagamento'), car.get('cupom'))
        self.perguntar(texto, [(f'ok:{car["id"][:12]}', T.B_CONFIRMAR), T.B_MUDAR, T.B_CANCELAR], fase='confirmar')

    def confirmar(self, arg):
        u = self.u
        car = u.get('carrinho')
        if not car or not car.get('id') or not str(car['id']).startswith(arg or '#'):
            ultimo = (u.get('pedidos') or [{}])[0]
            if ultimo.get('carrinho', '')[:12] == arg:
                self.dizer('✅ Esse pedido já foi feito!')
                return
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if u.get('fase') != 'confirmar' or not car.get('entrega') or not car.get('pagamento'):
            self.finalizar()
            return
        if car.get('status') == 'enviando':
            self.dizer(T.ENVIANDO)
            return
        car['status'] = 'enviando'
        self._salvar()  # trava contra toque duplo em outra rodada
        try:
            feito = self.ctx.ifood(self.wa).fechar(car['id'], u.get('cpf') or None)
        except ErroMCP:
            car['status'] = None
            raise
        u['pedidos'] = ([{'id': feito['id'], 'carrinho': car['id'], 'quando': self.ctx.agora(),
                          'loja': car.get('loja'), 'loja_id': car.get('loja_id'),
                          'resumo': ', '.join(f'{i["qtd"]}x {i["nome"]}' for i in car['itens'])[:300],
                          'total': car.get('total')}] + (u.get('pedidos') or []))[:PEDIDOS_GUARDADOS]
        u['carrinho'] = None
        u['fila'] = []
        u['escolha'] = None
        detalhes = {}
        for tentativa in range(2):  # getOrder logo depois do checkout pode dar NOT_FOUND (consistência eventual)
            try:
                detalhes = self.ctx.ifood(self.wa).pedido(feito['id'])
                break
            except ErroMCP as e:
                print(f'getOrder depois do pedido: {e!r}')
                if tentativa == 0:
                    self.ctx.dormir(1.5)
        u['pedidos'][0]['codigo'] = detalhes.get('codigo')
        self.dizer(T.pedido_feito(detalhes.get('codigo'), (car.get('entrega') or {}).get('tempo'),
                                  detalhes.get('codigo_entrega'), (car.get('pagamento') or {}).get('tipo')))
        self.ctx.iniciar_rastreio(self.wa, feito['id'])
        self.perguntar(T.OFERECER_REPETIR, [T.B_REC_SEMANA, T.B_REC_MES, T.B_REC_NAO], fase='recorrencia')

    def mudar(self, _arg=None):
        if not self.u.get('carrinho'):
            self.menu()
            return
        self.perguntar(T.O_QUE_MUDAR, [('mud:itens', '🧺 Itens'), ('mud:endereco', '🏠 Endereço'),
                                       ('mud:pagamento', '💳 Pagamento')], fase='mudar')

    def mudar_o_que(self, arg):
        car = self.u.get('carrinho')
        if not car:
            self.menu()
            return
        if arg == 'itens':
            self.mostrar_carrinho()
        elif arg == 'endereco':
            self.u['endereco'] = None
            self.u['pendente'] = None
            car.pop('entrega', None)
            car.pop('pagamento', None)
            self.pedir_endereco()
        elif arg == 'pagamento':
            formas = self.ctx.ifood(self.wa).pagamentos(car['loja_id'])
            if len(formas) <= 1:
                nome = formas[0]['nome'] if formas else 'essa forma'
                self.perguntar(f'Essa loja só aceita *{nome}* por aqui. 🙂', [T.B_FINALIZAR, T.B_CANCELAR])
                return
            car.pop('pagamento', None)
            self.u['formas'] = formas[:9]
            self.perguntar(T.QUAL_PAGAMENTO, [(f'pag:{i}', f['nome']) for i, f in enumerate(formas[:9])],
                           fase='pagamento', rotulo='Ver formas')
        else:
            self.mudar()

    def cancelar(self, _arg=None):
        u = self.u
        tinha = bool((u.get('carrinho') or {}).get('itens'))
        u.update({'carrinho': None, 'fila': [], 'escolha': None, 'atual': None, 'pendente': None})
        self.menu(T.CANCELADO if tinha else 'Tudo bem! 🙂')

    # ================================================================== depois do pedido

    def acompanhar(self, _arg=None):
        if not self.exigir_login(['botao', 'meu_pedido']):
            return
        pedidos = self.u.get('pedidos') or []
        if not pedidos:
            self.perguntar(T.SEM_PEDIDO, [T.B_PEDIR, T.B_REPETIR], fase='pedido')
            return
        st = self.ctx.ifood(self.wa).rastrear(pedidos[0]['id'])
        self.perguntar(T.status_pedido(st.get('codigo'), st.get('descricao')) +
                       f'\n\n🧾 {pedidos[0].get("resumo", "")}', [T.B_PEDIR, T.B_INICIO], fase='acompanhando')

    def repetir(self, _arg=None):
        if not self.exigir_login(['botao', 'repetir']):
            return
        if not self.garantir_endereco({'acao': 'botao', 'botao': 'repetir'}):
            return
        conhecidos = {p['id'] for p in self.u.get('pedidos') or []}
        opcoes = [{'id': p['id'], 'resumo': p.get('resumo', ''), 'loja': p.get('loja')}
                  for p in self.u.get('pedidos') or []]
        try:  # pedidos feitos fora do bot também (app do iFood), via getRecommendations(RECENT_ORDERS)
            opcoes += [p for p in self.ctx.ifood(self.wa).pedidos_recentes(self.u['endereco'])
                       if p['id'] not in conhecidos]
        except ErroMCP as e:
            print(f'pedidos recentes falhou: {e!r}')
        if not opcoes:
            self.perguntar(T.NADA_PRA_REPETIR, [T.B_PEDIR, T.B_INICIO], fase='pedido')
            return
        self.u['repetiveis'] = opcoes[:9]
        botoes = [(f'reped:{i}', p.get('loja') or 'Pedido', p.get('resumo', '')) for i, p in enumerate(opcoes[:9])]
        if len(botoes) <= 3:
            botoes = [(b[0], (b[2] or b[1])[:20]) for b in botoes]
        self.perguntar(T.QUAL_REPETIR, botoes, fase='repetir_lista', rotulo='Ver pedidos')

    def repetir_pedido(self, arg):
        u = self.u
        try:
            ped = (u.get('repetiveis') or [])[int(arg)]
        except (ValueError, IndexError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        self._refazer(ped['id'], ped.get('loja'))

    def _refazer(self, pedido_id, loja=None):
        car = self.ctx.ifood(self.wa).repetir_pedido(pedido_id)
        car['loja'] = car.get('loja') or loja
        self.u['carrinho'] = car
        self.u['fila'] = []
        linhas = '\n'.join(f'• {i["qtd"]}x {i["nome"]}' for i in car.get('itens') or [])
        self.dizer(f'🔁 Montei igual da outra vez:\n{linhas}')
        self.finalizar()

    # ================================================================== recorrência

    def definir_recorrencia(self, arg):
        dias = int(arg) if str(arg).isdigit() else 0
        ped = (self.u.get('pedidos') or [None])[0]
        if not dias or not ped:
            self.perguntar(T.DE_NADA, [T.B_PEDIR, T.B_MEU_PEDIDO], fase='acompanhando')
            return
        self.ctx.recorrencias.criar(self.wa, ped, dias)
        self.perguntar(T.recorrencia_ok(dias), [T.B_MEU_PEDIDO, T.B_INICIO], fase='acompanhando')

    def responder_lembrete(self, arg):
        oque, _, rid = arg.partition(':')
        rec = self.ctx.recorrencias.pegar(self.wa, rid)
        if not rec:
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if oque == 'pedir':
            if not self.exigir_login(['botao', f'lem:pedir:{rid}']):
                return
            if not self.garantir_endereco({'acao': 'botao', 'botao': f'lem:pedir:{rid}'}):
                return
            self.ctx.recorrencias.respondido(self.wa, rid)
            self._refazer(rec['pedido_id'], rec.get('loja'))
        elif oque == 'parar':
            self.ctx.recorrencias.remover(self.wa, rid)
            self.perguntar(T.LEMBRETE_PARADO, T.MENU, fase='pedido')
        else:
            self.ctx.recorrencias.respondido(self.wa, rid)
            self.perguntar(T.LEMBRETE_ADIADO, T.MENU, fase='pedido')

    def parar_lembretes(self):
        n = self.ctx.recorrencias.remover_todas(self.wa)
        self.perguntar(T.LEMBRETE_PARADO if n else 'Você não tem lembretes ligados. 🙂', T.MENU, fase='pedido')

    def _lembrete_pendente(self):
        """Lembrete que venceu quando a janela de 24h estava fechada: mostra agora."""
        rec = self.ctx.recorrencias.vencido_sem_aviso(self.wa)
        if not rec:
            return False
        self.ctx.recorrencias.avisado(self.wa, rec['id'])
        self.perguntar(T.lembrete(rec.get('resumo', '')),
                       [(f'lem:pedir:{rec["id"]}', T.B_LEMBRETE_PEDIR), (f'lem:hoje:{rec["id"]}', T.B_LEMBRETE_HOJE_NAO),
                        (f'lem:parar:{rec["id"]}', T.B_LEMBRETE_PARAR)], fase='lembrete')
        return True

    # ================================================================== erros

    def erro_mcp(self, e):
        """Erro de negócio do iFood em linguagem de gente, sempre com um caminho pra seguir."""
        cod = str(e.codigo or '').upper()
        u = self.u
        if 'CLOSED' in cod or 'UNAVAILABLE_MERCHANT' in cod:
            msg = T.LOJA_FECHADA + '\nVamos procurar em outra loja?'
            u['carrinho'] = None
            self.perguntar(msg, [T.B_OUTRA, T.B_INICIO], fase='pedido')
        elif 'CART' in cod and 'NOT_FOUND' in cod:
            u['carrinho'] = None
            self.perguntar('Seu pedido em andamento expirou. 😕 Vamos montar de novo?', [T.B_PEDIR, T.B_INICIO],
                           fase='pedido')
        elif 'PLACE_NOT_FOUND' in cod or 'ADDRESS' in cod:
            self.pedir_endereco()
        elif 'PAYMENT' in cod:
            if u.get('carrinho'):
                u['carrinho'].pop('pagamento', None)
            u['pagamento_preferido'] = None
            self.perguntar('Essa forma de pagamento não deu certo. 😕 Vamos escolher outra?',
                           [('mud:pagamento', '💳 Escolher outra'), T.B_CANCELAR])
        elif 'DOCUMENT' in cod or 'CPF' in cod:
            u['cpf'] = None
            self.perguntar(T.PEDIR_CPF, [T.B_SEM_CPF], fase='cpf')
        else:
            msg = e.para_usuario or T.ERRO
            self.perguntar(msg, [T.B_TENTAR, T.B_INICIO])


def _mime_aceito(mime):
    """O WhatsApp manda áudio como 'audio/ogg; codecs=opus'; o Gemini quer só 'audio/ogg'."""
    return (mime or 'application/octet-stream').split(';')[0].strip()
