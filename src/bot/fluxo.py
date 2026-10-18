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
import re
import time
import traceback

from src.bot import ranking, relevancia, tutor, voz
from src.bot import textos as T
from src.bot.combina import complementos
from src.bot.ifood import PrecisaLogin
from src.bot.interpretar import (cpf_em, igual_a_botao, interpretar, normalizar, numero_em, opcao_dita, pede_sugestao,
                                 so_complemento, so_endereco,
                                 regra_rapida)
from src.bot.recorrencia import DEMO_SEGUNDOS, botoes_lembrete, categoria
from src.shared.ifood_mcp import ErroMCP, SemAutorizacao
from src.shared.llm import ErroLLM
from src.shared.whatsapp import MAX_BOTAO, MAX_LINHA, ErroWhatsApp, partir

IFOOD_INSTAVEL_SEG = 600  # depois de uma falha do iFood, o atendente avisa por 10 min
POR_PAGINA = 10         # cards por vez no carrossel ("Mais opções" mostra os próximos da MESMA lista)
POR_PAGINA_VOZ = 3      # modo áudio: as opções são ditas uma a uma, mais que 3 ninguém guarda de ouvido
POR_PAGINA_SEM_CARROSSEL = 3  # se a Meta recusar o carrossel, volta pros cards soltos
# carrossel exige foto em todo card: produto sem foto usa a nossa logo
FOTO_PADRAO = (os.environ.get('HACKFOOD_BASE') or 'https://fabio-araujo-silva--hackfood-bot.us-east.modal.run') + '/logo.png'
LISTAS_GUARDADAS = 3    # listas antigas que ainda aceitam toque de botão
PEDIDOS_GUARDADOS = 10
TRIVIAIS = {'saudacao', 'agradecer', 'sim'}
# etapas em que um "oi" no meio não deve jogar o pedido fora: reapresenta a pergunta
NO_MEIO_DO_PEDIDO = {'escolhendo', 'quantidade', 'opcao', 'mais', 'tirar', 'pagamento', 'cpf', 'confirmar',
                     'mudar', 'endereco', 'endereco_escolha', 'endereco_lista', 'complemento', 'bairro'}
# sumiu mais que isso no meio de uma pergunta aberta: o "oi" da volta não é resposta daquela etapa
IDLE_MAX = 1800
FASES_QUE_EXPIRAM = {'endereco', 'complemento', 'bairro', 'cpf', 'endereco_escolha', 'quantidade', 'opcao',
                     'tirar', 'mudar'}
VOLTOU = 'Faz um tempinho que você sumiu, recomeçamos? 🙂'
# calou no meio de uma pergunta aberta: depois disso o bot cutuca uma vez (src/app.py dispara)
FOLLOWUP_SEG = 180
FASES_FOLLOWUP = {'endereco', 'complemento', 'bairro', 'endereco_escolha', 'escolhendo', 'quantidade', 'opcao',
                  'mais', 'tirar', 'pagamento', 'confirmar'}


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
        self._resposta = None
        self._direto = None
        self._disse = ''
        self._gravador = None   # modo áudio (src/bot/voz.py): guarda o que seria escrito nesta rodada
        self._voz_recem = False  # ligou nesta mensagem: o resto dela, se for só conversa, não vira "não entendi"
        self._voz_acaba = False  # a sessão terminou nesta rodada: a última resposta ainda vai em áudio

    # ================================================================== entrada

    def processar(self, wa_id, msgs):
        self.wa = wa_id
        self.u = u = self._carregar(wa_id)
        car = u.get('carrinho') or {}
        if car.get('loja_id') and not self.ctx.carrinho_valido(car):
            # ligaram/desligaram o mock: o carrinho é do outro iFood e prendia a busca numa loja que não existe aqui
            print(f'carrinho de outro iFood largado {wa_id}: {car.get("loja")}')
            u.update(carrinho=None, fila=[], listas={}, lista_atual=None, atual=None, visiveis=[], sugeridos=None)
            if u.get('fase') in NO_MEIO_DO_PEDIDO:
                u['fase'] = 'inicio'
        if msgs and msgs[-1].get('_nome'):
            u['nome'] = msgs[-1]['_nome']
        anterior = u.get('ultima_msg') or 0  # lido antes de sobrescrever (recorrencia.py usa o novo)
        u['ultima_msg'] = self.ctx.agora()
        self._resposta = None   # fala do Gemini pra esta rodada (interpretar preenche)
        self._direto = None     # "Sim, pode pedir" do lembrete: {'teto': total} = fecha sem resumo
        self._disse = ''
        if u.get('voz') and anterior and self.ctx.agora() - float(anterior) > IDLE_MAX:
            u['voz'] = None  # o modo áudio vale pra sessão: sumiu, a próxima volta escrita
        self._gravar()
        try:
            entradas = entradas_de(msgs)
            self._disse = ' / '.join(e.texto for e in entradas if e.texto)[:300]
            if self._debug_reset(entradas):   # palavra secreta de debug: desloga e zera tudo
                return
            if self._sessao_ociosa(anterior, entradas):
                return
            botoes =[e for e in entradas if e.tipo == 'botao']
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
            self._falar_rodada()
            self._salvar()

    def logou(self, wa_id):
        """Chamado quando o OAuth termina no navegador."""
        self.wa = wa_id
        self.u = u = self._carregar(wa_id)
        self._gravar()
        try:
            def seguir():
                nome = (u.get('nome') or '').split(' ')[0]  # nome do perfil de WhatsApp, se já temos
                perfil = {}
                try:
                    perfil = self.ctx.ifood(wa_id).usuario()
                    u['nome_ifood'] = perfil.get('nome')
                    nome = nome or (perfil.get('nome') or '').split(' ')[0]
                except ErroMCP as e:
                    print(f'getUser falhou depois do login: {e!r}')
                self.wpp.texto(wa_id, T.logou(nome, perfil.get('nome')))
                pend, u['pendente'] = u.get('pendente'), None
                if pend:
                    self.botao(pend['botao']) if pend.get('acao') == 'botao' else self.intencao(pend)
                else:
                    self.perguntar(T.PERGUNTA_PEDIDO, self._menu(), fase='pedido')
            self._protegido(seguir)
        finally:
            self._falar_rodada()
            self._salvar()

    @property
    def wpp(self):
        return self._gravador or self.ctx.wpp

    # ================================================================== modo áudio

    def _gravar(self):
        self._voz_acaba = False
        self._voz_recem = False
        self._gravador = voz.Gravador(self.ctx.wpp, lambda: bool(self.u and self.u.get('voz')))

    def _falar_rodada(self):
        """Fim da rodada no modo áudio: o que seria escrito vira UMA nota de voz, por último.
        Qualquer falha (Gemini, ElevenLabs, Meta) manda as mensagens seguradas, na ordem."""
        g, self._gravador = self._gravador, None
        try:
            if not g or not g.falas:
                return
            enviado = False
            try:
                modo = (self.u or {}).get('voz') or {}
                fala = voz.roteiro(self.ctx.llm, g.falas, self._disse, (self.u or {}).get('fase'),
                                   antes=modo.get('ultima') or '')
                nota = self.ctx.falar(fala) if fala else None
                if nota:
                    print(f'voz {self.wa}: {fala[:200]}')
                    self.ctx.wpp.audio(self.wa, self.ctx.wpp.subir_midia(*nota), transcricao=fala)
                    enviado = True
                    if modo:
                        modo['ultima'] = fala[:200]
                        modo['falou'] = True
            except Exception:  # noqa: BLE001 - sem áudio, vai escrito
                traceback.print_exc()
            if not enviado:
                trocar = None
                if self.u and self.u.get('voz') and not self.u['voz'].get('falou'):
                    # nem o 1º áudio saiu (key sem permissão, ElevenLabs fora): não promete o que não cumpre
                    self.u['voz'] = None
                    trocar = {T.VOZ_LIGADA: T.VOZ_INDISPONIVEL}
                g.soltar(trocar)
        finally:
            if self._voz_acaba and self.u:
                self.u['voz'] = None

    def _pedido_de_voz(self, texto):
        """Liga ou desliga o modo áudio quando a pessoa PEDE. Devolve (resto, acabou): o resto do
        texto segue o fluxo normal ("quero pão e me responde por áudio" -> "quero pão");
        acabou = a mensagem era só o pedido e a rodada já respondeu."""
        u = self.u
        if u.get('voz') and voz.pediu_texto(texto):
            u['voz'] = None
            resto = voz.resto_do_pedido(texto, voz.PEDE_TEXTO)
            self.dizer(T.VOZ_DESLIGADA)
        elif not u.get('voz') and voz.pediu_audio(texto):
            resto = voz.resto_do_pedido(texto, voz.PEDE_AUDIO)
            if self.ctx.pode_falar():
                u['voz'] = {'desde': self.ctx.agora()}
                self._voz_recem = True
                self.dizer(T.VOZ_LIGADA)
            else:
                self.dizer(T.VOZ_INDISPONIVEL)
        else:
            return texto, False
        if resto:
            return resto, False
        self._continuar_de_onde_parou()
        return '', True

    def _continuar_de_onde_parou(self):
        """Depois de trocar o jeito de responder: refaz a pergunta aberta (com ou sem botões)."""
        p = self.u.get('pergunta') or {}
        if p.get('botoes') or not p.get('texto'):
            self.repetir_pergunta()
        else:  # pergunta escrita (endereço, bairro): repete sem jogar a pessoa pro menu
            self.dizer(p['texto'])

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
                self.perguntar(self._tutor('erro_nosso', T.ERRO), [T.B_TENTAR, T.B_INICIO])
            except Exception:  # noqa: BLE001 - nem o aviso com botão saiu: vai texto puro
                traceback.print_exc()
                self.dizer(T.ERRO_SEM_BOTAO)

    def marca_followup(self):
        """Depois do processar(): a rodada terminou com pergunta aberta? Devolve a marca (o ultima_msg
        desta rodada) pro src/app.py agendar o follow-up, ou None."""
        u = self.u
        if not u or u.get('voz') or u.get('fase') not in FASES_FOLLOWUP:
            return None
        if u['fase'] not in ('endereco', 'bairro') and not (u.get('pergunta') or {}).get('botoes'):
            return None  # sem pergunta guardada não há o que reapresentar
        return u.get('ultima_msg') or None

    def followup(self, wa_id, marca):
        """FOLLOWUP_SEG depois: se a pessoa continuou calada (ultima_msg == marca) e ainda não foi
        cutucada por essa mesma mensagem, reapresenta a pergunta da etapa. Não mexe em ultima_msg,
        fase nem na pergunta guardada; no resumo só repete o resumo, nunca confirma."""
        self.wa = wa_id
        self.u = u = self._carregar(wa_id)
        if not marca or u.get('ultima_msg') != marca or u.get('followup_de') == marca:
            return False
        if self.marca_followup() != marca:  # mudou de etapa, entrou no modo áudio ou não tem pergunta
            return False
        guardado = {k: u.get(k) for k in ('ultima_msg', 'fase', 'pergunta')}
        u['followup_de'] = marca
        try:
            self._voltar_pra_etapa(T.AINDA_AI)
        finally:
            u.update(guardado)
            self._salvar()
        return True

    def _sessao_ociosa(self, anterior, entradas):
        """Voltou depois de IDLE_MAX com uma pergunta aberta: recomeça do menu (ou reapresenta o
        resumo, se o carrinho está montado). Login, endereços, histórico e carrinho ficam.
        True = a rodada acabou aqui (só "oi"/"sim"/"valeu", ou o texto era da etapa do CPF)."""
        u = self.u
        if not anterior or self.ctx.agora() - float(anterior) <= IDLE_MAX:
            return False  # 0/None = estado antigo sem a informação: não expira
        if any(e.tipo == 'botao' for e in entradas):
            return False  # tocou num botão: é resposta explícita, segue o caminho normal
        fase = u.get('fase')
        if fase == 'confirmar' and (u.get('carrinho') or {}).get('id'):
            self._protegido(self.mostrar_resumo)
        elif fase in FASES_QUE_EXPIRAM:
            u.update({'fase': 'pedido', 'pergunta': {}, 'pendente': None, 'fila': [], 'atual': None,
                      'escolha': None, 'novo_endereco': None})
            self._protegido(lambda: self.menu(VOLTOU))
            if fase == 'cpf':
                return True  # CPF nunca vai pra IA: o que ela digitou não segue pro fluxo livre
        else:
            return False
        return all(self._trivial(e) for e in entradas)

    def _ifood_instavel(self):
        try:
            return self.ctx.agora() - float(self.ctx.armazem.get('ifood_instavel') or 0) < IFOOD_INSTAVEL_SEG
        except Exception:  # noqa: BLE001
            return False

    def _aviso_ifood(self):
        if not self._ifood_instavel():
            return None
        return ('o servidor do iFood ficou instável nos últimos minutos e buscas/pedidos podem falhar; '
                'não é culpa da pessoa e costuma voltar logo')

    def _tutor(self, situacao, padrao):
        """Explicação do Gemini pro que deu errado, no contexto; sem ele, o texto fixo."""
        u = self.u or {}
        return tutor.falar(self.ctx.llm, situacao, getattr(self, '_disse', ''), u.get('fase'),
                           (u.get('pergunta') or {}).get('texto', '')) or padrao

    # ================================================================== envio

    def perguntar(self, texto, botoes, fase=None, rotulo='Ver opções', imagem=None, rodape=None):
        """Manda texto + botões (até 3) ou lista (4 a 10) e guarda a pergunta.
        botoes: [(id, título)] ou [(id, título, descrição)].
        Se a Meta recusar a mensagem interativa (formato), manda as opções numeradas em texto:
        a pessoa responde o número e a conversa segue (o "2" já vira o 2º botão)."""
        botoes = [tuple(b) for b in botoes]
        # título longo é cortado pela Meta ("Não desejo sachês #…"): o que está entre parênteses
        # vira detalhe no texto; se mesmo assim não couber em 20, vai de lista (24 + descrição 72)
        curtos = [partir(b[1], MAX_BOTAO) for b in botoes]
        cabe = len(botoes) <= 3 and not any(cortou for _, _, cortou in curtos)
        try:
            if cabe:
                detalhes = '\n'.join(f'• *{c}*: {d}' for c, d, _ in curtos if d)
                self.wpp.botoes(self.wa, f'{texto}\n\n{detalhes}' if detalhes else texto,
                                [(b[0], c) for b, (c, _, _) in zip(botoes, curtos)], imagem=imagem, rodape=rodape)
            else:
                linhas = []
                for b in botoes:
                    curto, resto, _ = partir(b[1], MAX_LINHA)
                    extra = b[2] if len(b) > 2 else ''
                    linhas.append((b[0], curto, ' · '.join(x for x in (resto, extra) if x)))
                self.wpp.lista(self.wa, texto, rotulo, linhas, rodape=rodape)
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
        self.perguntar(texto, self._menu(), fase='pedido')

    def _menu(self):
        """Botões do menu: "Fazer pedido" sempre; os atalhos só quando levam a algo."""
        return [T.B_PEDIR] + self._atalhos()

    def _atalhos(self):
        """"Pedir de novo" só com algo pra repetir (pedido nosso ou histórico) e "Meu pedido" só com pedido
        feito: botão que leva a "não tem nada" é botão a menos."""
        tem_pedido = bool(self.u.get('pedidos'))
        repete = tem_pedido or bool(self.ctx.armazem.get(f'hist:{self.wa}'))
        return ([T.B_REPETIR] if repete else []) + ([T.B_MEU_PEDIDO] if tem_pedido else [])

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
            'tentar': self.tentar_de_novo, 'sugerir': self.sugerir, 'nada': lambda _a=None: None,
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
        fase = u.get('fase')
        if fase != 'cpf':  # CPF nunca vai pra IA, nem falado: lá embaixo pede pra escrever
            entradas = [self._ouvir(e) for e in entradas]
        textos = [e.texto for e in entradas if e.tipo in ('texto', 'localizacao') and e.texto]
        texto = '\n'.join(textos).strip()
        if texto and fase != 'cpf':  # "me responde por áudio" / "pode escrever"
            texto, acabou = self._pedido_de_voz(texto)
            if acabou:
                return
        midias = [e for e in entradas if e.tipo in ('audio', 'imagem')]
        if not texto and not midias:
            self.repetir_pergunta(T.NAO_ENTENDI)
            return

        if fase == 'cpf':  # CPF nunca vai pra IA
            if midias and not texto:
                self.dizer('Por segurança, escreva o CPF com os números, por favor. 🙂')
                return
            # sem nenhum número não tem CPF ali: é outro assunto ("cancelar", "tira a coca"), que segue o fluxo
            if re.search(r'\d', texto) or normalizar(texto) in SEM_CPF:
                self.receber_cpf(texto)
                return
        if not midias:
            if fase in ('complemento', 'bairro'):
                r = regra_rapida(texto)
                if r and r['acao'] in ('inicio', 'cancelar', 'ajuda', 'sair', 'apagar_dados'):
                    self.intencao(r)  # comando escapa da etapa, como no endereço
                    return
                if (r and r['acao'] == 'saudacao') or (not r and _quer_novo_pedido(texto)):
                    # "oi" ou "quero fazer um pedido" não é complemento nem bairro: não salva, repete a pergunta
                    self._voltar_pra_etapa(T.ENDERECO_FALTA_POUCO)
                    return
            if fase in ('endereco', 'complemento', 'bairro') and not regra_rapida(texto):
                texto = self._etapa_ou_outro_assunto(texto, fase)
                if texto is None:  # era outro assunto e já foi atendido
                    return
            if fase == 'endereco':
                r = regra_rapida(texto)
                if r and r['acao'] in ('inicio', 'cancelar', 'ajuda', 'sair', 'apagar_dados'):
                    self.intencao(r)
                elif (r and r['acao'] == 'saudacao') or _quer_novo_pedido(texto):
                    # "oi" ou "quero fazer um pedido" não é endereço: não gasta geocoder nem prende a pessoa
                    self.perguntar(T.ENDERECO_AINDA, [T.B_TENTAR, T.B_INICIO], fase='endereco')
                elif not _parece_endereco(texto):
                    self.perguntar(T.ENDERECO_NAO_PARECE, [T.B_TENTAR, T.B_INICIO], fase='endereco')
                else:
                    texto = so_endereco(texto)  # "pode mandar pra minha casa, que é na Rua X, 1" -> "Rua X, 1"
                    u['ultima_acao'] = ['endereco', texto]  # "Tentar de novo" reusa o que ela digitou
                    self.receber_endereco(texto)
                return
            if fase == 'complemento':
                r = regra_rapida(texto)
                if (r and r['acao'] == 'nao') or normalizar(texto) in SEM_COMPLEMENTO:
                    self.sem_complemento()
                else:
                    self.receber_complemento(so_complemento(texto))  # "eu moro no apartamento 14" -> "Apto 14"
                return
            if fase == 'bairro':
                self.receber_bairro(texto)
                return
            titulos = (u.get('pergunta') or {}).get('titulos') or []
            i = igual_a_botao(texto, titulos)
            if i is None or len(texto) > 40:
                i = opcao_dita(texto, titulos)  # "é no centro": frase falada com o nome de uma opção
            if i is not None and len(texto) <= 60:
                self.botao(u['pergunta']['botoes'][i][0])
                return
            if pede_sugestao(texto):  # "algo que complete esse valor": sem depender do Gemini
                self.sugerir()
                return
            r = regra_rapida(texto)
            if r:
                self.intencao(r)
                return

        partes = [('texto', texto)] if texto else []
        for m in midias:
            try:  # o áudio que o Scribe não entendeu já chega baixado
                mime, dados = (m.mime, m.dados) if m.dados else self.ctx.baixar_midia(m.media_id)
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
            intent = interpretar(self.ctx.llm, u, partes, aviso=self._aviso_ifood())
            self._resposta = intent.get('resposta')
        except ErroLLM as e:
            print(f'LLM falhou: {e!r}')
            # sem Gemini, texto curto ainda vira busca ("pão", "leite integral"); frase não:
            # "algo que complete esse valor" ia pra busca do iFood ao pé da letra
            if texto and fase in ('inicio', 'pedido', 'escolhendo', 'mais', None) and len(texto.split()) <= 4:
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

    def _ouvir(self, e):
        """Áudio vira texto no Scribe e daí segue igual mensagem digitada (botão, endereço, sugestão...).
        Scribe desligado ou falhou: o áudio continua áudio e o Gemini ouve, como antes."""
        if e.tipo != 'audio':
            return e
        try:
            mime, dados = self.ctx.baixar_midia(e.media_id)
        except Exception as erro:  # noqa: BLE001 - o Gemini tenta baixar de novo lá na frente
            print(f'baixar áudio falhou: {erro!r}')
            return e
        texto = self.ctx.transcrever(mime or e.mime, dados)
        if not texto:
            e.mime, e.dados = mime or e.mime, dados  # já baixado: o Gemini não baixa de novo
            return e
        print(f'scribe {self.wa}: {texto[:200]}')
        self._disse = ' / '.join(x for x in (self._disse, texto) if x)[:300]
        return Entrada('texto', texto)

    def intencao(self, it):
        u = self.u
        a = it.get('acao')
        fase = u.get('fase')
        if self._voz_recem and a in ('nao_entendi', 'fora_do_escopo', 'saudacao', 'agradecer'):
            # "me responde por áudio, não enxergo bem": o resto era conversa, não pedido
            self._voz_recem = False
            self._continuar_de_onde_parou()
            return
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
                self.repetir_pergunta(self._resposta or T.NAO_ENTENDI)
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
        elif a == 'sugerir':
            self.sugerir(itens=it.get('itens'))
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
            if self._resposta and self._ifood_instavel():  # "vc tá aí?" com o iFood fora: explica
                self.repetir_pergunta(self._resposta) if botoes else self.menu(self._resposta)
            elif fase in NO_MEIO_DO_PEDIDO and botoes:
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
        elif a == 'agendar':
            self.agendar(it.get('numero'), it.get('hora'), it.get('itens'))
        elif a == 'fora_do_escopo':
            fala = self._resposta or T.FORA_DO_ESCOPO
            self.repetir_pergunta(fala) if botoes else self.menu(fala)
        else:
            fala = self._resposta or T.NAO_ENTENDI
            self.repetir_pergunta(fala) if botoes else self.menu(fala)

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
        self.perguntar(T.AJUDA, self._menu(), fase='pedido')

    def sair(self):
        self.ctx.sair(self.wa)
        self.u.update({'fase': 'inicio', 'pergunta': {}, 'carrinho': None, 'fila': [], 'escolha': None})
        self.dizer(T.SAIU)
        self._voz_acaba = True

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
            texto = 'O que mais você quer? 😊\nÉ só escrever ✍️'
        botoes = [T.B_FINALIZAR, T.B_INICIO] if car and car.get('itens') else self._atalhos()
        falta = _falta(car or {})
        if falta:  # abaixo do mínimo a sugestão vira botão: quem não sabe o que digitar só toca
            texto = (f'O que mais você quer? 😊\n{T.falta_minimo(falta, car.get("loja"))}\n'
                     'É só escrever ✍️ ou tocar em *Me sugere algo*.')
            botoes = [T.B_SUGERIR] + botoes
        if botoes:
            self.perguntar(texto, botoes, fase='pedido')
            return
        # sem pedido nem histórico não há atalho que sirva: só a pergunta, sem botão que não leva a nada
        self.dizer(texto)
        self.u['fase'] = 'pedido'
        self.u['pergunta'] = {'texto': texto, 'botoes': [], 'titulos': []}

    def sugerir(self, _arg=None, itens=None):
        """'Me sugere algo', 'algo que complete esse valor' ou o botão 💡. Na loja do carrinho,
        oferece 1º o que acompanha o pedido (o que o Gemini sugeriu e src/bot/combina.py: refri pro
        lanche, manteiga pro pão), depois o que a pessoa costuma comprar (hist:{wa}), depois algo
        parecido com o carrinho; quem fecha o pedido mínimo vem na frente. Cada pedido de sugestão
        traz outra coisa (u['sugeridos'], por loja). No máximo 3 buscas por toque: o iFood barra rajada."""
        if not self.exigir_login(None):
            return
        if not self.garantir_endereco({'acao': 'sugerir'}):
            return
        u = self.u
        car = u.get('carrinho') or {}
        ja = u.get('sugeridos') or {}
        if ja.get('loja') != car.get('loja_id'):
            ja = {'loja': car.get('loja_id'), 'termos': []}
        tipo = (u.get('atual') or {}).get('tipo_loja') or 'MERCADO'
        nomes = [i.get('nome') or '' for i in car.get('itens') or []]
        candidatos = ([{'termo': i['termo'], 'busca': i.get('busca'), 'tipo_loja': i.get('tipo_loja'),
                        'de_onde': 'combina'} for i in itens or []]
                      + [{'termo': t, 'de_onde': 'combina'} for t in complementos(nomes, tipo)]
                      + [{'termo': t, 'de_onde': 'costuma'} for t in self._costuma(car)]
                      + [{'termo': t, 'de_onde': 'parecido'} for t in self._parecidos(car)])
        candidatos = [c for c in candidatos if normalizar(c['termo'])]
        if candidatos and all(normalizar(c['termo']) in ja['termos'] for c in candidatos):
            ja['termos'] = []  # já sugeriu tudo: recomeça a roda
        novos, vistos = [], set(ja['termos'])
        for c in candidatos:
            if normalizar(c['termo']) not in vistos:
                vistos.add(normalizar(c['termo']))
                novos.append(c)
        if not novos:
            self.perguntar_pedido()
            return
        falta = _falta(car)
        evitar = [i.get('item_id') for i in car.get('itens') or []]
        for c in novos[:3]:
            ja['termos'].append(normalizar(c['termo']))
            u['sugeridos'] = ja
            pedido = {'termo': c['termo'], 'busca': c.get('busca') or c['termo'], 'quantidade': None,
                      'observacao': None, 'sugestao': {'falta': falta, 'evitar': evitar},
                      # com carrinho a busca é na loja dele, que tem um tipo só
                      'tipo_loja': tipo if car.get('itens') else (c.get('tipo_loja') or tipo)}
            if self.buscar(pedido, antes=T.sugestao(c['termo'], c['de_onde'], falta, car.get('loja'))):
                return
        outra = [T.B_SUGERIR] if len(novos) > 3 else []  # sobrou o que tentar: o 💡 tenta os próximos
        self.perguntar(T.SEM_SUGESTAO, outra + ([T.B_FINALIZAR, T.B_INICIO] if car.get('itens') else [T.B_INICIO]),
                       fase='pedido')

    def _costuma(self, car):
        """O que a pessoa mais compra (hist:{wa}, nomes e categorias) como termo de busca, fora o
        que já está no carrinho. Mais vezes primeiro; no empate, o mais recente."""
        hist = self.ctx.armazem.get(f'hist:{self.wa}') or {}
        no_car = ' | '.join(normalizar(i.get('nome')) for i in car.get('itens') or [])
        termos = []
        for k, h in sorted(hist.items(), key=lambda kv: (-kv[1].get('vezes', 0), -kv[1].get('ultima', 0))):
            termo = h.get('nome') if k.startswith('cat:') else _termo_curto(h.get('nome'))
            if normalizar(termo) and normalizar(termo) not in no_car:
                termos.append(termo)
        return termos

    def _parecidos(self, car):
        """Algo parecido com o carrinho: a categoria ('Pão francês' -> 'pão') ou o nome curto, pra
        busca na mesma loja mostrar as variações."""
        return [categoria(i.get('nome')) or _termo_curto(i.get('nome')) for i in car.get('itens') or []]

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

    def _etapa_ou_outro_assunto(self, texto, fase):
        """Endereço, bairro e complemento não engolem qualquer coisa: "quero uma pizza e uma coca de 2"
        tem número e não é endereço. Com cara forte da etapa (CEP, rua/avenida, apto/bloco...) segue
        direto; o resto o Gemini lê sabendo a etapa, e outro assunto muda a função do bot (pedido novo
        vira o pendente, cancelar cancela...). Devolve o texto pra etapa, ou None se já atendeu."""
        if _cara_de_etapa(texto, fase):
            return texto
        try:
            it = interpretar(self.ctx.llm, self.u, [('texto', texto)], aviso=self._aviso_ifood())
        except ErroLLM as e:
            print(f'LLM falhou lendo a etapa {fase}: {e!r}')
            if fase == 'endereco' and PEDIDO.search(normalizar(texto)):  # sem Gemini, pedido não vai pro geocoder
                self.perguntar(T.ENDERECO_AINDA, [T.B_TENTAR, T.B_INICIO], fase='endereco')
                return None
            return texto
        self._resposta = it.get('resposta')
        a = it.get('acao')
        if a in ('comprar', 'sugerir'):
            self.u['pendente'] = it  # o pedido novo substitui o que esperava o endereço
            self._voltar_pra_etapa(T.anotei(it.get('itens') or []))
            return None
        if a == 'fora_do_escopo':
            self._voltar_pra_etapa(self._resposta or T.FORA_DO_ESCOPO)
            return None
        if a in OUTRO_ASSUNTO:
            self.intencao(it)
            return None
        if a == 'endereco' and fase == 'endereco':
            if it.get('texto'):
                return it['texto']  # o endereço sem o resto da frase ("entrega na rua x, 120")
            # o Gemini não achou endereço nenhum ali ("que calor hoje"): responde e pede de novo
            self._voltar_pra_etapa(self._resposta or 'Hmm, isso não parece um endereço. 🤔')
            return None
        return texto

    def _voltar_pra_etapa(self, prefixo):
        """Responde o outro assunto e repete a pergunta da etapa (a do endereço não tem botão, e o
        repetir_pergunta de pergunta sem botão cai no menu)."""
        fase = self.u.get('fase')
        if fase == 'endereco':
            self.perguntar(f'{prefixo}\n\n{T.PEDIR_ENDERECO}', [T.B_INICIO], fase='endereco')
        elif fase == 'bairro':
            self.perguntar(f'{prefixo}\n\nQual é o *bairro*? Escreva aqui. 🙂', [T.B_INICIO], fase='bairro')
        else:
            self.repetir_pergunta(prefixo)

    def pedir_endereco(self, _arg=None):
        self.u['novo_endereco'] = None
        self.u['falhas_endereco'] = 0
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

    def _geocodificar_ifood(self, consultas):
        """Passo 1 do createAddress com a 1ª consulta que der resultado."""
        r = {}
        for consulta in dict.fromkeys(consultas):
            try:
                r = self.ctx.ifood(self.wa).geocodificar(consulta)
            except ErroMCP as e:
                if str(e.codigo) not in ('PLACE_NOT_FOUND', 'MISSING_ADDRESS', 'CANDIDATE_NOT_FOUND', 'GEOCODE_FAILED'):
                    raise
                r = {}
            if r.get('criado') or r.get('candidatos'):
                break
        return r

    def receber_endereco(self, texto):
        # CEP solto deixa o geocode do iFood perdido (já mandou pro Canadá): o CEP vira rua/bairro/cidade
        # antes (src/shared/geocoder.py). Invisível pra pessoa; se não resolver, vai o texto dela mesmo
        norm = self.ctx.normalizar_endereco(texto)
        r = self._geocodificar_ifood([norm['texto'], texto] if norm else [texto])
        if r.get('criado'):
            self.u['falhas_endereco'] = 0
            self._endereco_salvo(r['criado'])
            return
        cands = r.get('candidatos') or []
        for c in cands if norm else []:  # completa o que o iFood não devolveu (evita perguntar o bairro)
            if not c.get('bairro') and norm['bairro']:
                c['bairro'] = norm['bairro']
            if c.get('lat') is None and norm['lat'] is not None:
                c['lat'], c['lng'] = norm['lat'], norm['lng']
        if not cands:
            # .get: estado salvo antes deste campo existir não tem a chave
            self.u['falhas_endereco'] = self.u.get('falhas_endereco', 0) + 1
            if self.u['falhas_endereco'] >= 2:  # 2ª falha seguida: dá saída com botão em vez de loop mudo
                self.perguntar(T.ENDERECO_NAO_ACHEI, [T.B_TENTAR, T.B_INICIO], fase='endereco')
            else:
                self.dizer(T.ENDERECO_NAO_ACHEI)
                self.u['fase'] = 'endereco'
            return
        self.u['falhas_endereco'] = 0
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

    def buscar(self, pedido, antes=None):
        """pedido: {termo, quantidade, tipo_loja, observacao}. Busca uma vez e guarda a lista.
        antes: fala que vai logo antes dos cards. Sugestão (pedido['sugestao']) sem resultado
        devolve False calada, pra quem chamou tentar o próximo termo."""
        u = self.u
        car = u.get('carrinho') or {}
        loja_id = car.get('loja_id') if car.get('itens') else None
        # 1º o que a pessoa quer: busca desambiguada pelo Gemini ("cebola in natura", não "cebola"),
        # depois o filtro tira o que não é o produto (a busca do iFood casa com nome de loja e sabor);
        # só então a ordem do ranking. Se a busca precisa não achar nada, tenta o termo puro.
        ofertas, proxima = [], None
        for consulta in dict.fromkeys(x for x in (pedido.get('busca'), pedido['termo']) if x):
            achadas, proxima = self.ctx.ifood(self.wa).buscar(
                consulta, u['endereco'], pedido.get('tipo_loja') or 'MERCADO', loja_id=loja_id)
            ofertas = ranking.ordenar(relevancia.filtrar(self.ctx.llm, achadas, pedido), pedido)
            if pedido.get('sugestao'):
                ofertas = _sugeridas(ofertas, pedido['sugestao'])
            if ofertas:
                pedido['consulta_usada'] = consulta
                break
        u['atual'] = pedido
        if not ofertas:
            if pedido.get('sugestao'):
                return False
            botoes = [T.B_PULAR, T.B_ESCREVER] if u.get('fila') else [T.B_ESCREVER, T.B_INICIO]
            self.perguntar(T.nao_achei(pedido['termo'], car.get('loja') if loja_id else None), botoes,
                           fase='pedido')
            return False
        u['contador'] = int(u.get('contador') or 0) + 1
        lid = f'L{u["contador"]}'
        u['listas'][lid] = {'termo': pedido['termo'], 'ofertas': ofertas, 'pos': 0, 'proxima': proxima,
                            'loja_id': loja_id, 'tipo_loja': pedido.get('tipo_loja'), 'pedido': pedido}
        for velha in sorted(u['listas'], key=lambda k: int(k[1:]))[:-LISTAS_GUARDADAS]:
            u['listas'].pop(velha, None)
        u['lista_atual'] = lid
        if antes:
            self.dizer(antes)
        self.mostrar_pagina(lid)
        return True

    def mostrar_pagina(self, lid):
        u = self.u
        lst = u['listas'][lid]
        inicio = lst['pos']
        if inicio == 0 and u.get('endereco') and not (u.get('carrinho') or {}).get('itens'):
            self.dizer(T.entregando_em(u['endereco'].get('apelido') or 'Casa', u['endereco'].get('texto', '')))
        pagina = lst['ofertas'][inicio:inicio + (POR_PAGINA_VOZ if u.get('voz') else POR_PAGINA)]
        enviado = False
        if len(pagina) >= 2:  # carrossel pede de 2 a 10 cards
            try:
                self.wpp.carrossel(self.wa, T.topo_carrossel(lst['termo']),
                                   [(of.get('imagem') or FOTO_PADRAO, T.card_curto(of), [(f'pick:{lid}:{i}', T.B_QUERO)])
                                    for i, of in enumerate(pagina, start=inicio)])
                enviado = True
            except ErroWhatsApp as e:
                if e.status != 400:
                    raise
                print(f'carrossel recusado, indo de cards soltos: {e}')
        if not enviado:
            pagina = pagina[:POR_PAGINA_SEM_CARROSSEL]
            for i, of in enumerate(pagina, start=inicio):
                self.wpp.botoes(self.wa, T.card(of), [(f'pick:{lid}:{i}', T.B_QUERO)],
                                imagem=of.get('imagem') or None)
        lst['pos'] = inicio + len(pagina)
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
                    (lst.get('pedido') or {}).get('consulta_usada') or lst['termo'], u['endereco'], lst.get('tipo_loja') or 'MERCADO',
                    loja_id=lst.get('loja_id'), pagina=lst['proxima'])
                ja = {o['item_id'] for o in lst['ofertas']}
                novas = relevancia.filtrar(self.ctx.llm, novas, lst.get('pedido') or {'termo': lst['termo']})
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
            self.perguntar(T.PERGUNTA_PEDIDO, self._menu(), fase='pedido')
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
            self.perguntar('Seu pedido ainda está vazio. 🙂\n' + T.PERGUNTA_PEDIDO, self._menu(), fase='pedido')
            return
        u['fila'] = []
        api = self.ctx.ifood(self.wa)
        if car.get('minimo') and (car.get('subtotal') or 0) < car['minimo']:
            self.perguntar(f'O pedido mínimo do *{car.get("loja")}* é {T.reais(car["minimo"])}. 🙂\n'
                           f'Seu pedido está em {T.reais(car.get("subtotal"))}. Quer colocar mais alguma coisa?',
                           [T.B_SUGERIR, T.B_MAIS_COISAS, T.B_CANCELAR], fase='mais')
            return
        modelo = u.pop('agendar_modelo', None)
        if modelo:  # "todo dia às 7h peça dois pães": este carrinho vira o modelo do automático, nada sai agora
            self._salvar_modelo(car, modelo)
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
        if t in SEM_CPF:
            self.sem_cpf()
            return
        if self._cpf_obrigatorio():
            self.perguntar(T.CPF_INVALIDO, [T.B_CANCELAR], fase='cpf')
            return
        self.perguntar(T.CPF_INVALIDO, [T.B_SEM_CPF], fase='cpf')

    def _cpf_obrigatorio(self):
        return bool((self.u.get('carrinho') or {}).get('cpf_obrigatorio'))

    def sem_cpf(self, _arg=None):
        if self._cpf_obrigatorio():  # loja exige CPF na nota: "sem CPF" voltaria pro mesmo erro
            self.perguntar(T.CPF_OBRIGATORIO, [T.B_CANCELAR], fase='cpf')
            return
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
        direto, self._direto = self._direto, None
        if direto is not None:
            # a pessoa já disse "sim" no lembrete vendo valor, endereço e pagamento: fecha na hora,
            # a não ser que o preço tenha subido mais de 10% (aí ela confere o resumo antes)
            teto = direto.get('teto')
            if not teto or (car.get('total') or 0) <= teto * 1.10:
                u['fase'] = 'confirmar'
                u['via_lembrete'] = True
                self.confirmar(car['id'][:12])
                return
            texto = T.PRECO_SUBIU + '\n\n' + texto
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
        self._voz_acaba = True  # pedido feito = fim da sessão: esta resposta ainda vai em áudio, a próxima não
        self.ctx.iniciar_rastreio(self.wa, feito['id'])
        # lembrete só quando a compra se repete (item ou categoria, de qualquer loja) ou quando a pessoa
        # pediu pra agendar: na 1ª vez de um item ninguém quer ser cobrado de rotina
        repetidos = self._registrar_compra(car['itens'])
        dias_pedidos = u.pop('agendar_depois', None)
        if u.pop('via_lembrete', None):
            u['fase'] = 'acompanhando'  # já é recorrente: não oferece de novo
        elif dias_pedidos:
            self.perguntar(T.oferecer_repetir(repetidos[0] if repetidos else None),
                           [(f'rec:{dias_pedidos}', T.quando(dias_pedidos, u.get('agendar_hora')).capitalize()),
                            T.B_REC_NAO],
                           fase='recorrencia')
        elif repetidos:
            self.perguntar(T.oferecer_repetir(repetidos[0]), [T.B_REC_SEMANA, T.B_REC_MES, T.B_REC_NAO],
                           fase='recorrencia')
        else:
            u['fase'] = 'acompanhando'

    def _registrar_compra(self, itens):
        """Histórico de compras NOSSO (o iFood não diz se a pessoa já comprou aquilo): hist:{wa}
        = {nome normalizado: {nome, vezes, ultima}} + {'cat:<categoria>': ...}. Chave pelo nome, não
        pelo id: pão francês de outra padaria ainda é a 2ª vez do pão; e X-Bacon de uma hamburgueria
        depois de Smash Burger de outra é a 2ª vez de hambúrguer (categoria conta 1x por pedido).
        Devolve o que já tinha sido comprado antes: categoria primeiro, depois nomes."""
        chave = f'hist:{self.wa}'
        hist = self.ctx.armazem.get(chave) or {}
        repetidos, cats = [], []
        for i in itens:
            k = normalizar(i.get('nome'))
            if not k:
                continue
            h = hist.get(k) or {'nome': i.get('nome'), 'vezes': 0}
            h.update(nome=i.get('nome'), vezes=h['vezes'] + 1, ultima=self.ctx.agora())
            hist[k] = h
            if h['vezes'] >= 2:
                repetidos.append(h['nome'])
            cat = categoria(i.get('nome'))
            if cat and cat not in cats:
                cats.append(cat)
        for cat in cats:
            h = hist.get(f'cat:{cat}') or {'nome': cat, 'vezes': 0}
            h.update(vezes=h['vezes'] + 1, ultima=self.ctx.agora())
            hist[f'cat:{cat}'] = h
            if h['vezes'] >= 2:
                repetidos.insert(0, cat)
        self.ctx.armazem[chave] = hist
        return repetidos

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
            self.perguntar(T.SEM_PEDIDO, self._menu(), fase='pedido')
            return
        try:
            st = self.ctx.ifood(self.wa).rastrear(pedidos[0]['id'])
        except ErroMCP as e:
            if 'NOT_FOUND' not in str(e.codigo or '').upper():
                raise
            # pedido que este iFood não conhece (feito antes de ligar o mock, por exemplo): sai da lista
            self.u['pedidos'] = pedidos[1:]
            self.perguntar(T.SEM_PEDIDO, self._menu(), fase='pedido')
            return
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

    def _refazer(self, pedido_id, loja=None, modelo=None):
        api = self.ctx.ifood(self.wa)
        # modelo do automático ("todo dia às 7h, 2 pães"): o carrinho sai dos itens guardados, não de um pedido
        car = (api.criar_carrinho(modelo['loja_id'], self.u['endereco']['id'], modelo['itens']) if modelo
               else api.repetir_pedido(pedido_id))
        car['loja'] = car.get('loja') or loja
        self.u['carrinho'] = car
        self.u['fila'] = []
        linhas = '\n'.join(f'• {i["qtd"]}x {i["nome"]}' for i in car.get('itens') or [])
        self.dizer(f'🔁 Montei igual da outra vez:\n{linhas}')
        self.finalizar()

    # ================================================================== recorrência

    def definir_recorrencia(self, arg):
        dias = int(arg) if str(arg).isdigit() else 0
        hora = self.u.pop('agendar_hora', None)
        ped = (self.u.get('pedidos') or [None])[0]
        if not dias or not ped:
            self.perguntar(T.DE_NADA, [T.B_PEDIR, T.B_MEU_PEDIDO], fase='acompanhando')
            return
        demo = bool(self.ctx.armazem.get('cfg:demo_rapido'))
        pag = (self.u.get('pagamento_preferido') or {}).get('nome')
        # demo: a pessoa vê o combinado normal ("todo dia às 18h"), mas o 1º lembrete vem em 1 minuto
        rec = self.ctx.recorrencias.criar(self.wa, ped, dias, pagamento=pag, hora=hora,
                                          ciclo=DEMO_SEGUNDOS if demo else None)
        self.perguntar(T.recorrencia_ok(dias, hora), [T.B_MEU_PEDIDO, T.B_INICIO], fase='acompanhando')
        if demo:
            self.ctx.agendar_lembrete(self.wa, rec['proximo'])

    def agendar(self, dias=None, hora=None, itens=None):
        """"todo dia às 18h", "deixa no automático": a recorrência é nossa (o iFood não tem).
        Com itens ("todo dia às 7h peça dois pães") o automático é do que a pessoa disse: monta o pedido
        uma vez com ela e guarda como modelo, sem pedir agora (no dia o lembrete monta o carrinho dele).
        Sem itens, oferece deixar o último pedido no automático."""
        u = self.u
        dias = dias if isinstance(dias, int) and 0 < dias <= 90 else 7
        hora = hora if isinstance(hora, str) and re.fullmatch(r'\d{1,2}:\d{2}', hora) else None
        u['agendar_hora'] = hora
        car = u.get('carrinho') or {}
        if itens and not car.get('itens'):
            u['agendar_modelo'] = {'dias': dias, 'hora': hora}
            self.dizer(T.agendar_itens(itens, dias, hora))
            self.iniciar_compra(itens)
            return
        if car.get('itens'):  # no meio do pedido: agenda assim que este sair
            u['agendar_depois'] = dias
            self.repetir_pergunta(T.agendar_depois(dias, hora))
            return
        ped = (u.get('pedidos') or [None])[0]
        if not ped:
            self.perguntar(T.AGENDAR_SEM_PEDIDO, self._menu(), fase='pedido')
            return
        self.perguntar(T.confirmar_agendar(ped.get('resumo'), dias, hora),
                       [(f'rec:{dias}', T.quando(dias, hora).capitalize()), T.B_REC_NAO], fase='recorrencia')

    def _salvar_modelo(self, car, modelo):
        """Guarda loja + itens do carrinho como modelo do automático e esvazia o carrinho: nada é pedido."""
        u = self.u
        linhas = [{'item_id': i['item_id'], 'qtd': i['qtd'], 'opcoes': i.get('opcoes') or [], 'obs': i.get('obs'),
                   'nome': i.get('nome')} for i in car['itens']]
        resumo = ', '.join(f'{i["qtd"]}x {i["nome"]}' for i in car['itens'])
        demo = bool(self.ctx.armazem.get('cfg:demo_rapido'))
        rec = self.ctx.recorrencias.criar(
            self.wa, {'id': None, 'resumo': resumo, 'loja': car.get('loja'), 'total': car.get('subtotal'),
                      'loja_id': car.get('loja_id'), 'itens': linhas},
            modelo['dias'], hora=modelo.get('hora'), ciclo=DEMO_SEGUNDOS if demo else None)
        u.update(carrinho=None, fila=[], agendar_hora=None)
        self.perguntar(T.modelo_ok(resumo, car.get('loja'), modelo['dias'], modelo.get('hora')), self._menu(),
                       fase='pedido')
        if demo:
            self.ctx.agendar_lembrete(self.wa, rec['proximo'])

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
            self._direto = {'teto': rec.get('total')}  # o "sim" aqui é a confirmação do pedido
            self._refazer(rec.get('pedido_id'), rec.get('loja'), modelo=rec if rec.get('itens') else None)
        elif oque == 'parar':
            self.ctx.recorrencias.remover(self.wa, rid)
            self.perguntar(T.LEMBRETE_PARADO, self._menu(), fase='pedido')
        else:
            self.ctx.recorrencias.respondido(self.wa, rid)
            self.perguntar(T.LEMBRETE_ADIADO, self._menu(), fase='pedido')

    def parar_lembretes(self):
        n = self.ctx.recorrencias.remover_todas(self.wa)
        self.perguntar(T.LEMBRETE_PARADO if n else 'Você não tem lembretes ligados. 🙂', self._menu(), fase='pedido')

    def _lembrete_pendente(self):
        """Lembrete que venceu quando a janela de 24h estava fechada: mostra agora."""
        rec = self.ctx.recorrencias.vencido_sem_aviso(self.wa)
        if not rec:
            return False
        self.ctx.recorrencias.avisado(self.wa, rec['id'])
        self.perguntar(T.lembrete(rec, self.u.get('endereco')), botoes_lembrete(rec), fase='lembrete')
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
        elif 'MERCH-007' in cod or 'CPF' in str(e).upper():
            # 17/10 19h: "MERCH-007: Este restaurante obriga a digitação do CPF" caía no "Tentar de
            # novo" genérico e a pessoa batia 3x no mesmo erro. Agora pede o CPF, sem a opção "sem CPF".
            u['cpf'] = None
            if u.get('carrinho'):
                u['carrinho']['cpf_obrigatorio'] = True
            self.perguntar(T.CPF_OBRIGATORIO, [T.B_CANCELAR], fase='cpf')
        elif 'DOCUMENT' in cod:
            u['cpf'] = None
            self.perguntar(T.PEDIR_CPF, [T.B_SEM_CPF], fase='cpf')
        else:
            msg = e.para_usuario if _em_portugues(e.para_usuario) else T.ERRO  # inglês da API nunca vai pra tela
            if _falha_do_ifood(cod):  # servidor deles caiu/barrou: marca e explica como gente
                self.ctx.armazem['ifood_instavel'] = self.ctx.agora()
                msg = self._tutor('ifood_fora', msg)
            self.perguntar(msg, [T.B_TENTAR, T.B_INICIO])


def _falha_do_ifood(cod):
    """Erro de infraestrutura do iFood (fora do ar, firewall, rede), não de regra de negócio."""
    return cod.startswith('HTTP_') or cod in ('TIMEOUT', 'REDE', 'SESSAO', 'RESPOSTA_VAZIA')


def _mime_aceito(mime):
    """O WhatsApp manda áudio como 'audio/ogg; codecs=opus'; o Gemini quer só 'audio/ogg'."""
    return (mime or 'application/octet-stream').split(';')[0].strip()


LOGRADOURO = re.compile(r'\b(rua|av|avenida|travessa|praca|alameda|rodovia|estrada)\b')
NOVO_PEDIDO = re.compile(r'\b(novo pedido|outro pedido|fazer (um )?pedido|quero pedir|menu|voltar)\b')


def _parece_endereco(texto):
    """Tem número/CEP, palavra de logradouro ou pelo menos 3 palavras. Senão nem vai pro geocoder."""
    t = normalizar(texto)
    return bool(re.search(r'\d', t) or LOGRADOURO.search(t) or len(t.split()) >= 3)


def _quer_novo_pedido(texto):
    """'Quero fazer um novo pedido' na etapa do endereço: é pedido de menu, não endereço."""
    t = normalizar(texto)
    return not re.search(r'\d', t) and not LOGRADOURO.search(t) and bool(NOVO_PEDIDO.search(t))


# claramente outro assunto no meio do endereço: segue o fluxo de sempre (pedido e papo têm tratamento próprio)
OUTRO_ASSUNTO = {'cancelar', 'ajuda', 'acompanhar', 'ver_pedido', 'sair', 'apagar_dados', 'parar_lembrete'}
CEP = re.compile(r'\b\d{5}-?\d{3}\b')
PEDIDO = re.compile(r'\b(quero|queria|me ve|manda|pedir|pede|comer|beber|tomar|comprar|cancela|cancelar|ajuda)\b')
COMPLEMENTO = re.compile(r'\b(ap|apto|apartamento|bloco|bl|casa|fundos|sala|andar|torre|condominio|cond|lote'
                         r'|quadra|qd|lt|sobrado|kitnet|edificio|predio|portaria)\b')
SEM_COMPLEMENTO = {'nao', 'nao tem', 'n', 'nenhum', 'nenhuma', 'sem', 'sem complemento', 'nada', 'nao precisa',
                   'casa', 'e casa', 'so casa'}
SEM_CPF = ('nao', 'sem cpf', 'sem', 'nao quero', 'n', 'pular', 'nao tenho')


def _cara_de_etapa(texto, fase):
    """A mensagem tem cara forte do que a etapa pede (CEP ou rua/avenida no endereço; apto/bloco ou
    resposta curta no complemento; nome curto no bairro)? Aí segue direto, sem perguntar pro Gemini.
    Verbo de pedido ("quero", "manda", "comer") nunca é cara de etapa."""
    t = normalizar(texto)
    if PEDIDO.search(t):
        return False
    if fase == 'endereco':
        return bool(CEP.search(texto) or LOGRADOURO.search(t))
    if fase == 'complemento':
        return t in SEM_COMPLEMENTO or bool(COMPLEMENTO.search(t)) or len(t.split()) <= 2
    return len(t.split()) <= 3


# palavras que entregam inglês: as mensagens da API vêm em inglês, e às vezes são instrução pro agente
INGLES = re.compile(r"\b(the|this|that|not|please|again|attempt|order|error|failed|try|unable|invalid|found"
                    r"|request|cannot|could|should|must|was|were|is|are|your|you)\b", re.I)


def _em_portugues(texto):
    """Só texto em português vai pra tela: "Do not attempt to look up this Order ID again." não vai."""
    return bool(texto) and not INGLES.search(texto)


def _falta(car):
    """Quanto falta pro pedido mínimo da loja; None se já passou ou se a loja não tem mínimo."""
    falta = (car.get('minimo') or 0) - (car.get('subtotal') or 0)
    return round(falta, 2) if falta > 0.005 else None


def _termo_curto(nome):
    """Nome do iFood -> termo de busca: 'Leite Integral Italac 1L' -> 'Leite Integral',
    'Pão de forma integral' -> 'Pão de forma'."""
    p = str(nome or '').split()
    n = 3 if len(p) > 2 and normalizar(p[1]) in ('de', 'da', 'do', 'com', 'e', 'em') else 2
    return ' '.join(p[:n])


def _sugeridas(ofertas, s):
    """Sugestão: tira o que já está no carrinho e, faltando valor pro mínimo, põe na frente quem
    fecha o mínimo sozinho (do que passa menos pro que passa mais); depois o resto, do mais caro."""
    ofertas = [o for o in ofertas if o['item_id'] not in (s.get('evitar') or [])]
    if s.get('falta'):
        ofertas.sort(key=lambda o: (o['preco'] < s['falta'], abs(o['preco'] - s['falta'])))
    return ofertas
