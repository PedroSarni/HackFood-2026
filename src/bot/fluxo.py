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

from src.bot import foto as leitor_foto
from src.bot import grupo as kit_grupo
from src.bot import melhor_loja, ranking, relevancia, tutor, vitrine, voz
from src.bot import textos as T
from src.bot.combina import complementos, ja_tem, so_o_produto
from src.bot.ifood import PrecisaLogin
from src.bot.interpretar import (cpf_em, igual_a_botao, interpretar, normalizar, numero_em, opcao_dita, pede_sugestao, pergunta_minimo,
                                 so_complemento, so_endereco,
                                 regra_rapida)
from src.bot.recorrencia import DEMO_SEGUNDOS, botoes_lembrete, categoria, preco_da_ultima_vez
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
                     'mudar', 'endereco', 'endereco_escolha', 'endereco_lista', 'complemento', 'bairro',
                     'foto', 'kit', 'grupo_pessoas', 'trocar_loja'}
# sumiu mais que isso no meio de uma pergunta aberta: o "oi" da volta não é resposta daquela etapa
IDLE_MAX = 1800
FASES_QUE_EXPIRAM = {'endereco', 'complemento', 'bairro', 'cpf', 'endereco_escolha', 'quantidade', 'opcao',
                     'tirar', 'mudar', 'foto', 'kit', 'grupo_pessoas', 'grupo_tema'}
VOLTOU = 'Faz um tempinho que você sumiu, recomeçamos? 🙂'
# calou no meio de uma pergunta aberta: depois disso o bot cutuca uma vez (src/app.py dispara).
# 1 min desde 18/10 (decisão do Fabio; antes 3 min)
FOLLOWUP_SEG = 60
ABANDONO_SEG = 300  # continuou calada com itens no carrinho: esquece o carrinho (decisão do Fabio)
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
        elif tipo == 'document' and str((m.get('document') or {}).get('mime_type') or '').startswith(
                ('image/', 'application/pdf')):
            d = m['document']  # foto mandada "como documento" (sem compressão) ou lista em PDF: é foto também
            saida.append(Entrada('imagem', d.get('caption', ''), mime=d.get('mime_type'), media_id=d.get('id')))
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
        self._direto = None     # "Sim, pode pedir" do lembrete: {'campo', 'teto', 'rid'} = fecha sem resumo
        self._disse = ''
        if self.ctx.armazem.pop(f'voz_fim:{wa_id}', None):
            u['voz'] = None  # o pedido chegou (src/bot/rastreio.py): acabou a sessão do modo áudio
        # o modo áudio vale pra sessão: sumiu, a próxima volta escrita. Com pedido a caminho a sessão
        # continua (os avisos do rastreio vão em áudio) até o rastreio acabar, ou 2 h no pior caso
        limite = 2 * 3600 if (u.get('voz') or {}).get('rastreando') else IDLE_MAX
        if u.get('voz') and anterior and self.ctx.agora() - float(anterior) > limite:
            u['voz'] = None
        self._gravar()
        try:
            entradas = entradas_de(msgs)
            self._disse = _sem_cpf(' / '.join(e.texto for e in entradas if e.texto))[:300]
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
                    self._mostrar_vitrine()
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
        if not u or u.get('voz'):
            return None
        # "O que mais você quer?" com itens no carrinho também é pergunta aberta
        if u.get('fase') not in FASES_FOLLOWUP and not (u.get('fase') == 'pedido' and self._tem_itens()):
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

    def _tem_itens(self):
        return bool(((self.u or {}).get('carrinho') or {}).get('itens'))

    def marca_abandono(self):
        """Depois do processar(): tem itens no carrinho? Devolve a marca pro src/app.py agendar o
        abandono (vale até no modo áudio, onde não há follow-up), ou None."""
        return ((self.u or {}).get('ultima_msg') or None) if self._tem_itens() else None

    def abandonar_carrinho(self, wa_id, marca):
        """ABANDONO_SEG depois: continuou calada (ultima_msg == marca) com itens no carrinho e ainda
        não esquecemos por essa marca? Esquece o carrinho como o cancelar(), SEM chamar o iFood, e
        volta pro menu: no resumo, um "sim" tardio nunca confirma. Não mexe em ultima_msg."""
        self.wa = wa_id
        self.u = u = self._carregar(wa_id)
        if not marca or u.get('ultima_msg') != marca or u.get('abandono_de') == marca or not self._tem_itens():
            return False
        u['abandono_de'] = marca
        u.update({'carrinho': None, 'fila': [], 'escolha': None, 'atual': None, 'pendente': None, 'grupo': None,
                  'kit': None, 'grupo_pendente': None, 'foto': None, 'fase': 'pedido'})
        try:
            self.menu(T.CARRINHO_ABANDONADO)
        finally:
            u['ultima_msg'] = marca
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
        if (self.u or {}).get('pedidos'):  # quem já pediu vê "Fazer novo pedido" ("Fazer pedido" confundia)
            botoes = [T.B_NOVO_PEDIDO if b == T.B_PEDIR else b for b in botoes]
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
            original = p.get('texto')
            self.perguntar(texto, [tuple(b) for b in p['botoes']])
            if original is not None and self.u.get('pergunta'):
                self.u['pergunta']['texto'] = original  # o aviso é de uma vez só, não vira a pergunta
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
        if prefixo and self.u.get('pergunta'):
            # o aviso ("Tudo bem, cancelei") é de uma vez só: repetir a pergunta depois não traz ele de volta
            self.u['pergunta']['texto'] = T.PERGUNTA_PEDIDO
        if not prefixo:  # o "oi": boas-vindas curtinha e a vitrine do gosto da pessoa logo embaixo
            self._mostrar_vitrine()

    # ================================================================== vitrine (src/bot/vitrine.py)

    def _mostrar_vitrine(self):
        """Carrossel de ideias montado pelos agentes. Nunca atrapalha o menu: sem endereço com
        coordenada, sem produto ou com erro, simplesmente não aparece."""
        u = self.u
        try:
            vit = u.get('vitrine') or {}
            if not vit.get('cards') or self.ctx.agora() - float(vit.get('quando') or 0) > vitrine.VALIDADE:
                end = self._endereco_pra_vitrine()
                if not end:
                    return
                api = self.ctx.ifood(self.wa)
                try:
                    recentes = [] if self.ctx.armazem.get(f'hist:{self.wa}') else api.pedidos_recentes(end)
                except ErroMCP:
                    recentes = []
                cards = vitrine.montar(api, end, self.ctx.armazem.get(f'hist:{self.wa}'), recentes,
                                       self.ctx.agora(), FOTO_PADRAO)
                vit = {'cards': cards, 'quando': self.ctx.agora()}
                u['vitrine'] = vit
            cards = vit['cards']
            if len(cards) < 2:
                return
            self.wpp.carrossel(self.wa, T.VITRINE_TOPO,
                               [(c['imagem'], T.card_vitrine(c), [(f'vit:{i}', c['botao'])]) for i, c in enumerate(cards)])
        except ErroWhatsApp as e:
            print(f'vitrine recusada: {e}')
            return
        except Exception:  # noqa: BLE001 - vitrine é bônus: o menu já foi
            traceback.print_exc()
            return
        # "lanches", "o de descontos", "até 35" falado ou escrito também escolhe o card
        p = u.get('pergunta') or {}
        p['botoes'] = (p.get('botoes') or []) + [[f'vit:{i}', c['titulo']] for i, c in enumerate(cards)]
        p['titulos'] = (p.get('titulos') or []) + [c['titulo'] for c in cards]
        u['pergunta'] = p

    def _endereco_pra_vitrine(self):
        """O endereço em uso; senão o salvo no iFood que já tem coordenada (só pra mostrar ideias,
        sem perguntar nada: a escolha de verdade continua no garantir_endereco)."""
        end = self.u.get('endereco')
        if end and end.get('lat') is not None:
            return end
        try:
            ends = self.ctx.ifood(self.wa).enderecos()
        except ErroMCP:
            return None
        return next((e for e in ends if e.get('ultimo') and e.get('lat') is not None),
                    next((e for e in ends if e.get('lat') is not None), None))

    def escolher_vitrine(self, arg):
        try:
            card = (self.u.get('vitrine') or {}).get('cards', [])[int(arg)]
        except (ValueError, IndexError, TypeError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        self.u['ultima_acao'] = ['botao', f'vit:{arg}']
        self.iniciar_compra([dict(card['pedido'])])

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
            'vit': self.escolher_vitrine, 'loja': self.trocar_loja, 'loja_fica': self.ficar_na_loja,
            'foto': self.responder_foto, 'kit': self.responder_kit, 'grupo_n': self.grupo_pessoas,
            'acomp': self.colocar_sugestao,
        }
        fn = rotas.get(acao)
        if not fn:
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if acao in ('pick', 'mais', 'qtd', 'opt', 'fim', 'ok', 'reped', 'rem', 'ent', 'pag', 'cand',
                    'end', 'loja', 'acomp') and not self.exigir_login(['botao', bid]):
            return
        fn(arg) if acao not in ('inicio', 'apagar_nao') else fn()

    def livre(self, entradas):
        u = self.u
        fase = u.get('fase')
        if fase != 'cpf':  # CPF nunca vai pra IA, nem falado: lá embaixo pede pra escrever
            entradas = [self._ouvir(e) for e in entradas]
        textos = [e.texto for e in entradas if e.tipo in ('texto', 'localizacao') and e.texto]
        texto = '\n'.join(textos).strip()
        fotos = [e for e in entradas if e.tipo == 'imagem']
        if texto and fase != 'cpf':  # "me responde por áudio" / "pode escrever"
            texto, acabou = self._pedido_de_voz(texto)
            if acabou and not fotos:
                return
        midias = [e for e in entradas if e.tipo in ('audio', 'imagem')]
        if not texto and not midias:
            self.repetir_pergunta(T.NAO_ENTENDI)
            return

        achado = _cpf_no_texto(texto) if fase != 'cpf' else None
        if achado:  # CPF dito antes da hora: guarda pra nota fiscal e tira do texto (CPF nunca vai pra IA)
            u['cpf'], texto = achado
            self.dizer(T.CPF_ANOTADO)
            if not texto and not midias:
                self.repetir_pergunta()
                return
        if fase == 'cpf':  # CPF nunca vai pra IA
            # sem nenhum número não tem CPF ali: é outro assunto ("cancelar", "tira a coca"), que segue o fluxo
            if texto and (re.search(r'\d', texto) or normalizar(texto) in SEM_CPF):
                self.receber_cpf(texto)
                return
            if midias:
                # áudio ou foto no CPF nem é ouvido nem aberto (pode ser o documento) e vale como "sem CPF":
                # quem fala nessa hora quase sempre diz "não precisa" (17/10, pedido do Fabio). Loja que
                # exige CPF: o sem_cpf pede pra escrever, sem a opção de pular.
                self.sem_cpf()
                return
        elif fotos:  # foto em qualquer etapa é pedido: comida, lista de compras ou produto
            self.receber_fotos(fotos, texto, outras=[e for e in midias if e.tipo != 'imagem'])
            return
        if not midias:
            if fase in ('complemento', 'bairro'):
                r = regra_rapida(texto)
                if r and r['acao'] in ('inicio', 'cancelar', 'ajuda', 'sair', 'apagar_dados', 'acompanhar', 'mudar'):
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
                if r and r['acao'] in ('inicio', 'cancelar', 'ajuda', 'sair', 'apagar_dados', 'acompanhar', 'mudar'):
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
            if pergunta_minimo(texto):  # "qual o valor mínimo?": é pergunta, não sugestão nem "quanto deu"
                self.acompanhar(sobre='minimo')
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
            self.dizer(T.midia_ruim(m.tipo for m in midias))
            return
        try:
            intent = interpretar(self.ctx.llm, u, partes, aviso=self._aviso_ifood())
            self._resposta = intent.get('resposta')
        except ErroLLM as e:
            print(f'LLM falhou: {e!r}')
            # sem Gemini, texto curto ainda vira busca ("pão", "leite integral"), sem o "quero ... hj" em
            # volta; frase não: "algo que complete esse valor" ia pra busca do iFood ao pé da letra
            termo = ' '.join(w for w in texto.split() if normalizar(w) not in ENCHIMENTO)
            tema = kit_grupo.tema_em(texto) if texto else None
            if tema and fase != 'kit' and kit_grupo.parece_grupo(texto):  # "pizza pra 4 dividindo" sem Gemini
                intent = {'acao': 'grupo', 'numero': kit_grupo.pessoas_em(texto), 'itens': [tema]}
            elif termo and fase in ('inicio', 'pedido', 'escolhendo', 'mais', 'grupo_tema', None) and len(termo.split()) <= 4:
                loja = 'RESTAURANTE' if categoria(termo) in DE_RESTAURANTE else 'MERCADO'
                intent = {'acao': 'comprar', 'itens': [{'termo': termo[:60], 'quantidade': None,
                                                        'tipo_loja': loja, 'observacao': None}]}
            elif midias and not texto:
                self.dizer(T.midia_ruim(m.tipo for m in midias))
                return
            else:
                self.repetir_pergunta(T.NAO_ENTENDI)
                return
        self._anotar_pagamento(intent.get('pagamento'), texto)
        # fala de verdade (passou pelo Gemini; número solto e botão não): escolha sem travar em quantidade
        # nem opção, e "pode fechar" vai direto pro fim do checkout
        self._falado = {'texto': normalizar(texto),
                        'qtd': next((i['quantidade'] for i in intent.get('itens') or [] if i.get('quantidade')), None),
                        'fechar': bool(intent.get('fechar')) or bool(FECHAR.search(normalizar(texto)))}
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
        self._disse = _sem_cpf(' / '.join(x for x in (self._disse, texto) if x))[:300]
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
            elif fase == 'grupo_pessoas' and n:  # "6" é 6 pessoas, não o 6º botão
                self.grupo_pessoas(n)
            elif fase == 'escolhendo' and (n or a == 'escolher'):
                self._escolha_por_fala(it)
            elif a == 'quantidade' and it.get('itens') and fase not in ('quantidade', 'kit'):
                # "pode colocar mais 10 leites" fora do "quantas unidades?" é pedido de produto, não o 10º
                # (nem o 2º) botão. 18/10 (QA U20): o modelo reserva chamou de quantidade, o carrinho não
                # mexeu e a fala dele ("adicionei mais 10 leites") saiu como se tivesse mexido.
                self.iniciar_compra(it['itens'])
            elif n and 1 <= n <= len(botoes):
                self.botao(botoes[n - 1][0])
            else:
                self.repetir_pergunta(self._resposta or T.NAO_ENTENDI)
        elif a == 'sim':
            if fase == 'confirmar' and u.get('sugestao_resumo') and u.get('sim_ambiguo') != u.get('resumo_de'):
                # "sim" pro café ou pro pedido? pergunta UMA vez; o "sim" seguinte (o 1º botão é o
                # "Fazer pedido assim") fecha, falado ou escrito: quem pede por áudio não toca em botão
                self._sim_ou_acompanhamento()
            elif fase == 'confirmar':
                self.botao(botoes[0][0] if botoes else 'nada')
            elif fase == 'escolhendo' and self._visiveis():  # "sim, quero esse" com os cards na tela
                self._escolha_por_fala(it)
            elif fase == 'apagar':
                self.apagar()
            elif fase == 'mais':
                self.perguntar_pedido()
            elif fase == 'login':
                self.reenviar_login()
            elif fase == 'recorrencia':
                self.definir_recorrencia('7')
            elif fase == 'foto':
                self.foto_sim()
            elif fase == 'kit':
                self.kit_ok()
            elif botoes and fase in ('endereco_lista', 'repetir_lista'):
                self.botao(botoes[0][0])
            else:
                self.perguntar_pedido()
        elif a == 'nao':
            if fase == 'mais':
                self.finalizar()
            elif fase == 'confirmar' and u.get('sugestao_resumo'):
                self._sim_ou_acompanhamento()  # "não" pode ser pro café, não pro pedido
            elif fase == 'confirmar':
                self.mudar()
            elif fase == 'complemento':
                self.sem_complemento()
            elif fase == 'recorrencia':
                self.definir_recorrencia('0')
            elif fase in ('foto', 'kit'):
                self.botao(f'{fase}:nao')
            elif fase == 'trocar_loja':
                self.ficar_na_loja()
            elif fase == 'apagar':
                self.menu()
            else:
                self.menu('Tudo bem! 🙂')
        elif a == 'comprar':
            if fase in ('grupo_tema', 'grupo_pessoas', 'kit') and it.get('itens'):
                # "pizza" quando o bot perguntou o que o grupo quer comer; "coca" com o kit na tela
                self.grupo({'acao': 'grupo', 'itens': it['itens']})
            else:
                self.iniciar_compra(it.get('itens') or [])
        elif a == 'trocar_loja':  # "tem outro mercado?", "troca de loja"; com o kit na tela é o "Outra loja" dele
            if fase == 'kit':
                self.responder_kit('outra')
            else:
                self.trocar_loja()
        elif a == 'grupo':
            self.grupo(it)
        elif a == 'sugerir':
            self.sugerir(itens=it.get('itens'))
        elif a == 'mais_opcoes':
            if u.get('lista_atual'):
                self.mais_opcoes(u['lista_atual'])
            else:
                self.perguntar_pedido()
        elif a == 'finalizar':
            if fase == 'escolhendo' and self._visiveis() and not (u.get('carrinho') or {}).get('itens'):
                if getattr(self, '_falado', None):  # "quero esse e pode fechar" com o carrinho ainda vazio
                    self._falado['fechar'] = True
                self._escolha_por_fala(it)
            elif fase == 'confirmar' and u.get('resumo_de') == _marca_resumo(u.get('carrinho') or {}):
                # "faz o pedido", "pode fechar" com o resumo deste carrinho na tela = o Confirmar. 18/10: o áudio
                # caía no "toque em Confirmar pedido" e quem pede por áudio nunca conseguia fechar
                self.confirmar(str((u.get('carrinho') or {}).get('id') or '')[:12])
            else:
                self.finalizar()
        elif a == 'ver_pedido':
            self.mostrar_carrinho()
        elif a == 'tirar_item':
            self.perguntar_tirar()
        elif a == 'cancelar':
            self.cancelar()
        elif a == 'mudar':  # "mudar" digitado (no pagamento, no CPF...): o mesmo menu do botão Mudar do resumo
            if (u.get('carrinho') or {}).get('itens'):
                self.mudar()
            elif fase in ('endereco', 'complemento', 'bairro'):
                self._voltar_pra_etapa(T.NADA_PRA_MUDAR)
            else:
                self.repetir_pergunta(T.NADA_PRA_MUDAR)
        elif a == 'acompanhar':
            self.acompanhar(sobre=it.get('sobre'))
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
        if ja.get('loja') != car.get('loja_id') or 'termos' not in ja:  # sem carrinho as duas lojas são None
            ja = {'loja': car.get('loja_id'), 'termos': []}
        tipo = (u.get('atual') or {}).get('tipo_loja') or 'MERCADO'
        nomes = [i.get('nome') or '' for i in car.get('itens') or []]
        # o que a IA propôs passa pelo mesmo crivo do código: só o produto, e nada que o carrinho já tem
        propostos = [dict(i, termo=so_o_produto(i['termo']), busca=so_o_produto(i.get('busca')) or None)
                     for i in itens or []]
        candidatos = ([{'termo': i['termo'], 'busca': i.get('busca'), 'tipo_loja': i.get('tipo_loja'),
                        'de_onde': 'combina'} for i in propostos if not ja_tem(i['termo'], nomes)]
                      # sem carrinho não tem o que acompanhar ("refrigerante" do nada não é recomendação):
                      # vale o que ela costuma levar e, por último, algo da hora do dia
                      + [{'termo': t, 'de_onde': 'combina'} for t in (complementos(nomes, tipo) if nomes else [])]
                      + [{'termo': t, 'de_onde': 'costuma'} for t in self._costuma(car)]
                      + [{'termo': t, 'de_onde': 'parecido'} for t in self._parecidos(car)]
                      + ([] if nomes else [{'termo': t, 'tipo_loja': lj, 'de_onde': 'hora'}
                                           for t, lj in _da_hora(self.ctx.agora())]))
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
        sem_carrinho = not (u.get('carrinho') or {}).get('itens')
        if sem_carrinho:
            u['plano'] = None
        if len(itens) > 1 and sem_carrinho:
            # lista nova: a loja é a que tem TUDO e sai mais em conta, escolhida antes do 1º item
            # (src/bot/melhor_loja.py); antes era a do 1º item escolhido e o resto ficava pelo caminho
            itens = self._planejar(itens)
        elif len(itens) > 1:
            self.dizer(T.lista_de_compras(itens))
        u['fila'] = list(itens[1:])
        self.buscar(itens[0])

    def _planejar(self, itens):
        """Escolhe a loja da lista e conta qual é, quanto sai e o que fica de fora. Devolve a lista na ordem
        de procurar: o que a loja tem primeiro e o que ela não tem por último (ainda tenta nela, e aí dá pra
        pular ou trocar de loja). Sem loja nenhuma perto, segue item a item como antes."""
        u = self.u
        tipos = [i.get('tipo_loja') or 'MERCADO' for i in itens]
        tipo = max(tipos, key=tipos.count)
        self.dizer(T.procurando_loja(itens, tipo))
        plano = melhor_loja.planejar(self.ctx.ifood(self.wa), self.ctx.llm, u['endereco'], itens)
        if not plano['lojas']:
            return itens
        melhor = plano['lojas'][0]
        plano.update(escolhida=melhor['loja_id'], tipo=tipo)
        u['plano'] = plano
        ordem = ([i for k, i in enumerate(itens) if k in melhor['tem']]
                 + [i for k, i in enumerate(itens) if k not in melhor['tem']])
        self.dizer(T.loja_da_lista(melhor, plano['itens'], tipo, len(plano['lojas']) > 1, ordem[0]['termo']))
        return ordem

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
        if a in ('comprar', 'sugerir', 'grupo'):
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
        # carrinho com item manda (o iFood fecha um pedido por loja); lista nova vai na loja do plano
        loja_id = car.get('loja_id') if car.get('itens') else (u.get('plano') or {}).get('escolhida')
        ofertas, proxima = self._coletar(pedido, loja_id)
        u['atual'] = pedido
        if not ofertas:
            if pedido.get('sugestao'):
                return False
            # com carrinho também dá pra pular: volta pro "quer mais alguma coisa?" em vez de travar aqui
            botoes = [T.B_PULAR, T.B_ESCREVER] if u.get('fila') or car.get('itens') else [T.B_ESCREVER, T.B_INICIO]
            if self._tem_outra_loja():  # a loja da lista não tem esse: dá pra levar tudo pra outra
                botoes.insert(1, T.B_TROCAR_LOJA)
            self.perguntar(T.nao_achei(pedido['termo'], self._nome_da_loja(loja_id) if loja_id else None), botoes,
                           fase='pedido')
            return False
        self._mostrar_lista(pedido, ofertas, proxima, loja_id, antes=antes)
        return True

    def _coletar(self, pedido, loja_id):
        """As ofertas de um pedido, já filtradas e na ordem. Devolve (ofertas, token da próxima página)."""
        # 1º o que a pessoa quer: busca desambiguada pelo Gemini ("cebola in natura", não "cebola"),
        # depois o filtro tira o que não é o produto (a busca do iFood casa com nome de loja e sabor);
        # só então a ordem do ranking. Se a busca precisa não achar nada, tenta o termo puro.
        ofertas, proxima = [], None
        for consulta in dict.fromkeys(x for x in (pedido.get('busca'), pedido['termo']) if x):
            achadas, proxima = self.ctx.ifood(self.wa).buscar(
                consulta, self.u['endereco'], pedido.get('tipo_loja') or 'MERCADO', loja_id=loja_id,
                preco_max=pedido.get('preco_max'))
            if pedido.get('so_promo'):  # card "Descontos pra você": só o que está com preço baixado
                achadas = [o for o in achadas if o.get('preco_antigo') and o['preco_antigo'] > (o.get('preco') or 0)]
            ofertas = ranking.ordenar(relevancia.filtrar(self.ctx.llm, achadas, pedido), pedido)
            if pedido.get('sugestao'):
                ofertas = _sugeridas(ofertas, pedido['sugestao'])
            if ofertas:
                pedido['consulta_usada'] = consulta
                break
        return ofertas, proxima

    def _mostrar_lista(self, pedido, ofertas, proxima, loja_id, antes=None, termo=None):
        """Guarda a lista (o "Mais opções" reaproveita) e mostra a 1ª página."""
        u = self.u
        u['contador'] = int(u.get('contador') or 0) + 1
        lid = f'L{u["contador"]}'
        u['listas'][lid] = {'termo': termo or pedido['termo'], 'ofertas': ofertas, 'pos': 0, 'proxima': proxima,
                            'loja_id': loja_id, 'tipo_loja': pedido.get('tipo_loja'), 'pedido': pedido}
        for velha in sorted(u['listas'], key=lambda k: int(k[1:]))[:-LISTAS_GUARDADAS]:
            u['listas'].pop(velha, None)
        u['lista_atual'] = lid
        if antes:
            self.dizer(antes)
        self.mostrar_pagina(lid)

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
        outra = T.B_TROCAR_LOJA if self._tem_outra_loja() else T.B_OUTRA  # lista: troca a loja, não o produto
        botoes = ([(f'mais:{lid}', T.B_MAIS)] if tem_mais else []) + [outra]
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
                    loja_id=lst.get('loja_id'), pagina=lst['proxima'],
                    preco_max=(lst.get('pedido') or {}).get('preco_max'))  # "até R$ 35" vale na página 2
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

    # ================================================================== a loja da lista

    def _tem_outra_loja(self):
        """Lista com plano e mais de uma loja: dá pra trocar de loja no meio."""
        return len((self.u.get('plano') or {}).get('lojas') or []) > 1

    def _nome_da_loja(self, loja_id):
        car = self.u.get('carrinho') or {}
        if car.get('loja_id') == loja_id and car.get('loja'):
            return car['loja']
        return next((lj['loja'] for lj in (self.u.get('plano') or {}).get('lojas') or [] if lj['loja_id'] == loja_id),
                    None)

    def trocar_loja(self, arg=None):
        """"Trocar de loja" no meio da lista: mostra as outras lojas (quem tem tudo primeiro, quanto sai e o
        tempo) e, escolhida uma, leva junto o que já está no carrinho, pelo equivalente da loja nova."""
        u = self.u
        plano = u.get('plano')
        if arg in (None, ''):
            car = u.get('carrinho') or {}
            if not plano and not car.get('itens') and not u.get('fila'):
                self.repetir_pergunta(T.SEM_LISTA_PRA_TROCAR)
                return
            termo = (u.get('atual') or {}).get('termo')
            if not plano or (termo and termo not in plano['itens']):
                plano = self._replanejar()  # item pedido depois da lista, ou carrinho que não veio de lista
            self._mostrar_lojas(plano)
            return
        try:
            nova = plano['lojas'][int(arg)]
        except (TypeError, ValueError, IndexError):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        self._mudar_de_loja(plano, nova)

    def _mostrar_lojas(self, plano):
        u = self.u
        plano = plano or {}
        outras = [(k, lj) for k, lj in enumerate(plano.get('lojas') or [])
                  if lj['loja_id'] != plano.get('escolhida')][:9]
        if not outras:
            self.repetir_pergunta(T.SEM_OUTRA_LOJA)
            return
        if u.get('fase') != 'trocar_loja':  # pra voltar pro mesmo ponto, na troca e no "Continuar aqui"
            u['troca_de'] = {'fase': u.get('fase'), 'pergunta': u.get('pergunta')}
        n = len(plano['itens'])
        self.perguntar(T.qual_loja([lj for _, lj in outras], n),
                       [(f'loja:{k}', lj['loja'], T.linha_loja(lj, n)) for k, lj in outras] + [T.B_FICAR_NA_LOJA],
                       fase='trocar_loja', rotulo='Ver lojas')

    def ficar_na_loja(self, _arg=None):
        """"Continuar aqui" (ou "não") na escolha de loja: volta pra pergunta de onde veio."""
        u = self.u
        volta = u.pop('troca_de', None) or {}
        if volta.get('pergunta'):
            u['fase'], u['pergunta'] = volta.get('fase'), volta['pergunta']
            self.repetir_pergunta('Beleza, seguimos aqui. 🙂')
        else:
            self._proximo_da_fila()

    def _mudar_de_loja(self, plano, nova):
        """Leva a lista pra outra loja: o carrinho vai junto (o equivalente de cada item lá, mesma quantidade
        e opções) e a lista segue de onde estava, agora na loja nova."""
        u = self.u
        api = self.ctx.ifood(self.wa)
        car = u.get('carrinho') or {}
        levados, ficaram = [], []
        if car.get('itens'):
            linhas, ficaram = self._equivalentes(api, car['itens'], nova['loja_id'])
            novo = api.criar_carrinho(nova['loja_id'], u['endereco']['id'], linhas) if linhas else None
            if novo:
                novo['loja'] = novo.get('loja') or nova['loja']
                pelo_item = {lin['item_id']: lin for lin in linhas}
                for i in novo.get('itens') or []:  # as nossas anotações de cada linha vão junto
                    lin = pelo_item.get(i.get('item_id')) or {}
                    i['opcoes'], i['obs'] = lin.get('opcoes') or [], lin.get('obs')
                    i['termo'], i['tipo_loja'] = lin.get('termo'), lin.get('tipo_loja')
                levados = novo.get('itens') or []
            u['carrinho'] = novo
        plano['escolhida'] = nova['loja_id']
        u['plano'] = plano
        u['escolha'] = None
        self.dizer(T.troquei_de_loja(nova['loja'], levados, ficaram))
        de = (u.pop('troca_de', None) or {}).get('fase')
        if u.get('atual') and de in ('escolhendo', 'pedido', 'quantidade', 'opcao'):
            self.buscar(u['atual'])  # o item da vez de novo, agora na loja nova
        else:
            self._proximo_da_fila()

    def _equivalentes(self, api, itens, loja_id):
        """As linhas do carrinho na loja nova: o mesmo produto pelo nome ("Arroz branco tipo 1"), senão o mais
        parecido do que a pessoa pediu ("arroz"); mesma quantidade, e as mesmas opções quando a loja tem
        (senão as padrão dela). Uma busca por linha e um filtro do Gemini pra todas.
        Devolve (linhas pro carrinho novo, nomes do que a loja nova não tem)."""
        tipo = (self.u.get('plano') or {}).get('tipo') or 'MERCADO'
        pedidos = [{'termo': it.get('termo') or it['nome'], 'busca': it['nome'],
                    'tipo_loja': it.get('tipo_loja') or tipo} for it in itens]
        achados = melhor_loja.ofertas_de_varios(api, self.ctx.llm, self.u['endereco'], pedidos, [loja_id] * len(itens))
        linhas, ficaram = [], []
        for it, pedido, ofertas in zip(itens, pedidos, achados):
            opcoes = None
            if ofertas:
                of = melhor_loja.mais_parecida(ofertas, it['nome'])
                try:
                    item = api.item(of['item_id'], loja_id, self.u['endereco'])
                    opcoes = kit_grupo.opcoes_automaticas(item, 1, ' '.join(o.get('nome') or ''
                                                                            for o in it.get('opcoes') or []))
                except ErroMCP as e:
                    if melhor_loja.infra(e):
                        raise
                    print(f'trocar de loja: {it.get("nome")!r} sem equivalente ({e!r})')
            if opcoes is None:
                ficaram.append(it['nome'])
                continue
            linhas.append({'item_id': of['item_id'], 'qtd': it['qtd'], 'opcoes': opcoes, 'obs': it.get('obs'),
                           'termo': pedido['termo'], 'tipo_loja': pedido['tipo_loja']})
        return linhas, ficaram

    def _replanejar(self):
        """Plano de novo com o que está no carrinho + o item da vez + a fila: troca de loja com item fora do
        plano (pedido depois da lista) ou com carrinho que não veio de lista (pedido de novo, kit)."""
        u = self.u
        car = u.get('carrinho') or {}
        tipo = (u.get('atual') or {}).get('tipo_loja') or (u.get('plano') or {}).get('tipo') or 'MERCADO'
        itens = [{'termo': i.get('termo') or i['nome'], 'busca': None if i.get('termo') else i['nome'],
                  'quantidade': i.get('qtd'), 'tipo_loja': i.get('tipo_loja') or tipo, 'observacao': None}
                 for i in car.get('itens') or []]
        vistos = {normalizar(i['termo']) for i in itens}
        for p in [u.get('atual')] + list(u.get('fila') or []):
            if p and normalizar(p['termo']) not in vistos:
                vistos.add(normalizar(p['termo']))
                itens.append(p)
        if not itens:
            return None
        self.dizer(T.PROCURANDO_OUTRAS)
        plano = melhor_loja.planejar(self.ctx.ifood(self.wa), self.ctx.llm, u['endereco'], itens)
        plano.update(escolhida=car.get('loja_id') or (u.get('plano') or {}).get('escolhida'), tipo=tipo)
        u['plano'] = plano
        return plano

    # ================================================================== escolha do item

    def _escolha_por_fala(self, it):
        """"quero esse", "essa tá boa", "o de calabresa": escolhe o card pela fala, pelo mesmo caminho do
        toque em "Quero esse". Sem como saber qual, pergunta qual (em vez de "não entendi")."""
        pid = self._oferta_falada(it.get('numero'), it, self._visiveis())
        if not pid:
            self._rodape_cards('Qual deles? Diga o número ou o nome. 🙂')  # o rodapé já fala do botão
            return
        self.botao(pid)

    def _oferta_falada(self, n, it, visiveis):
        """Qual card a pessoa escolheu falando: o número; o único da tela ("quero esse"); o nome, inteiro ou
        pela palavra que só ele tem ("a de calabresa"). None = não deu pra saber."""
        if n and 1 <= n <= len(visiveis):
            return visiveis[n - 1]
        if len(visiveis) == 1:
            return visiveis[0]
        posicao = _posicao_dita(self._disse, len(visiveis))
        if posicao:
            return visiveis[posicao - 1]
        falado = normalizar(' '.join([self._disse or ''] + [i['termo'] for i in it.get('itens') or []]))
        nomes = {}
        for pid in visiveis:
            _, lid, idx = pid.split(':')
            try:
                nomes[pid] = normalizar(self.u['listas'][lid]['ofertas'][int(idx)]['nome'])
            except (KeyError, IndexError, ValueError):
                continue
        # o mesmo produto em 2 lojas na tela ("Pizza de calabresa" na Bella Napoli e na Forno a Lenha) não é
        # dúvida: fica o 1º da tela. Nomes diferentes empatados, aí sim, "Qual deles?"
        inteiros = [pid for pid, nome in nomes.items() if nome and nome in falado]
        if inteiros and len({nomes[pid] for pid in inteiros}) == 1:
            return inteiros[0]
        palavras = {w for w in falado.split() if len(w) > 2}
        pontos = {pid: len(palavras & set(nome.split())) for pid, nome in nomes.items()}
        melhor = max(pontos.values(), default=0)
        empate = [pid for pid, p in pontos.items() if p == melhor]
        return empate[0] if melhor and len({nomes[pid] for pid in empate}) == 1 else None

    def _opcoes_faladas(self, g, texto, esc, so_ditas=False):
        """Grupo de opções pela fala: as que a pessoa disse ("grande", "catupiry"). Obrigatório não dito: as
        primeiras, o padrão da loja. Opcional não dito fica de fora."""
        palavras = set(texto.split())

        def chave(op):
            return next((w for w in normalizar(op['nome']).split()
                         if w.isalpha() and len(w) > 2 and w not in ('sem', 'com')), '')
        ops = g.get('opcoes') or []
        ditas = [op for op in ops if chave(op) in palavras]
        if so_ditas:
            escolhidas = ditas[:g.get('max') or 1]
        else:
            escolhidas = (ditas + [op for op in ops if op not in ditas])[:max(1, g['min'] - esc['feitas'])]
            esc['feitas'] = g['min']
        esc['opcoes'] += [{'grupo_id': g.get('id'), 'opcao_id': op['id'], 'nome': op['nome'],
                           'preco': op.get('preco')} for op in escolhidas]

    def _anotar_pagamento(self, dito, texto):
        """"vou pagar no pix", "é no vale-refeição": vira a forma preferida e o checkout não pergunta de novo."""
        t = normalizar(texto or '')
        tipo = PAGAMENTO_DITO.get(dito) or next((tp for r, tp in PAGAMENTO_NO_TEXTO if r.search(t)), None)
        if tipo:
            self.u['pagamento_preferido'] = {'tipo': tipo, 'nome': NOME_PAGAMENTO_DITO[tipo]}

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
                        'obs': pedido.get('observacao'), 'opcoes': [], 'grupo': 0, 'feitas': 0,
                        'termo': pedido.get('termo'), 'tipo_loja': pedido.get('tipo_loja')}
        self._proximo_passo_da_escolha()

    def _proximo_passo_da_escolha(self):
        u = self.u
        esc = u['escolha']
        grupos = [g for g in esc['item'].get('grupos') or [] if g.get('min', 0) > 0]
        falado = getattr(self, '_falado', None)
        while esc['grupo'] < len(grupos):
            g = grupos[esc['grupo']]
            if esc['feitas'] < g['min']:
                if falado:  # escolha falada não trava em opção: o que a pessoa disse ("grande"), senão o padrão
                    self._opcoes_faladas(g, falado['texto'], esc)
                    continue
                self._perguntar_opcao(g, esc['feitas'] + 1, g['min'])
                return
            esc['grupo'] += 1
            esc['feitas'] = 0
        if falado and not esc.get('opcionais'):  # opcional só se ela disse ("borda de catupiry")
            esc['opcionais'] = True
            for g in esc['item'].get('grupos') or []:
                if not g.get('min'):
                    self._opcoes_faladas(g, falado['texto'], esc, so_ditas=True)
        if not esc.get('qtd'):
            if not falado:
                nome = esc['item'].get('nome') or esc['oferta']['nome']
                self.perguntar(T.quantos(nome), [('qtd:1', '1'), ('qtd:2', '2'), ('qtd:3', '3')], fase='quantidade')
                return
            esc['qtd'] = falado.get('qtd') or 1
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
                it['termo'], it['tipo_loja'] = velho.get('termo'), velho.get('tipo_loja')
            elif it.get('item_id') == of['item_id']:
                it['opcoes'], it['obs'] = esc['opcoes'], esc.get('obs')
                # o que a pessoa pediu ("arroz"): no "Trocar de loja" é o que se procura na loja nova
                it['termo'], it['tipo_loja'] = esc.get('termo'), esc.get('tipo_loja')
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
        if (getattr(self, '_falado', None) or {}).get('fechar'):  # "quero esse e pode fechar": direto pro fim
            self.finalizar()
            return
        self.perguntar(T.mais_alguma(car.get('total') or car.get('subtotal'), self._pessoas(),
                                     *_falta_minimo(car), subtotal=car.get('subtotal')),
                       [T.B_FINALIZAR, T.B_MAIS_COISAS, T.B_TIRAR], fase='mais')

    def mostrar_carrinho(self):
        car = self.u.get('carrinho') or {}
        if not car.get('itens'):  # 18/10: "mostra o meu carrinho" vazio só perguntava o que pedir, sem dizer que estava vazio
            self.perguntar(T.CARRINHO_VAZIO + '\n\n' + T.PERGUNTA_PEDIDO, self._menu(), fase='pedido')
            return
        linhas = '\n'.join(f'• {i["qtd"]}x {i["nome"]}' for i in car['itens'])
        self.perguntar(f'🧺 *Seu pedido:*\n{linhas}\n\n{T.mais_alguma(car.get("total") or car.get("subtotal"), self._pessoas(), *_falta_minimo(car), subtotal=car.get("subtotal"))}',
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
            u['carrinho'] = u['grupo'] = None
            self.dizer(f'🗑️ Tirei *{it["nome"]}*. Seu pedido ficou vazio.')
            self.perguntar_pedido()
            return
        novo = api.remover(car['id'], it['cart_item_id'])
        if not novo or not novo.get('itens'):
            u['carrinho'] = u['grupo'] = None
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
        if u.get('fase') == 'confirmar' and u.get('resumo_de') == _marca_resumo(car):
            # 18/10 03h33: o fechamento demorou, a pessoa tocou Finalizar 3x e recebeu 3 resumos de uma vez.
            # O resumo do carrinho de agora já está na tela: aponta pra ele em vez de refazer tudo com o iFood.
            self.dizer(f'☝️ O resumo do pedido está aí em cima. Toque em *{T.B_CONFIRMAR}* ou me diga *pode fazer* '
                       'que eu faço o pedido.')
            return
        if not car.get('entrega') or not car.get('pagamento'):  # vai falar com a loja: são vários segundos
            self.dizer(T.FECHANDO)
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
        guardadas = {i.get('cart_item_id'): (i.get('opcoes'), i.get('obs'), i.get('termo'), i.get('tipo_loja'))
                     for i in car.get('itens') or []}
        for i in novo.get('itens') or []:
            i['opcoes'], i['obs'], i['termo'], i['tipo_loja'] = guardadas.get(i.get('cart_item_id'),
                                                                              ([], None, None, None))
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
        mais = [m for m in complementos([i.get('nome') or '' for i in car.get('itens') or []],
                                        (u.get('atual') or {}).get('tipo_loja') or 'MERCADO')
                if m != u.get('sugestao_sem_estoque')]
        # com sugestão, o resumo faz duas perguntas: "sim"/"não" digitados viram uma pergunta de volta
        u['sugestao_resumo'] = mais[0] if mais else None
        u['resumo_de'] = _marca_resumo(car)
        # fim do checkout: total, pagamento e uma sugestão do que acompanha (é só falar), sem passo a mais
        texto = T.resumo(car, u.get('endereco'), car.get('entrega'), car.get('pagamento'), car.get('cupom'),
                         pessoas=self._pessoas(), sugestao=mais[0] if mais else None)
        direto, self._direto = self._direto, None
        if direto is not None:
            # a pessoa já disse "sim" no lembrete vendo valor, endereço e pagamento: fecha na hora,
            # a não ser que o preço tenha subido mais de 10% (aí ela confere o resumo antes); compara total
            # com total, ou subtotal com subtotal quando a entrega da última vez não é conhecida
            teto = direto.get('teto')
            if not teto or (car.get(direto.get('campo') or 'total') or 0) <= teto * 1.10:
                u['fase'] = 'confirmar'
                u['via_lembrete'] = direto.get('rid') or True
                self.confirmar(car['id'][:12])
                return
            texto = T.PRECO_SUBIU + '\n\n' + texto
        self.perguntar(texto, [(f'ok:{car["id"][:12]}', T.B_CONFIRMAR), T.B_MUDAR, T.B_CANCELAR], fase='confirmar')

    def _sim_ou_acompanhamento(self):
        """O resumo perguntou do acompanhamento e do pedido: o 1º "sim" ou "não" não fecha nem abre o mudar.
        Pergunta de novo com um caminho por botão; daí o "sim" (ou "faz assim") falado fecha o pedido."""
        u = self.u
        sug = u['sugestao_resumo']
        u['sim_ambiguo'] = u.get('resumo_de')   # já perguntou deste resumo: o próximo "sim" é pro pedido
        colocar = f'➕ Colocar {sug}'
        if len(colocar) > MAX_BOTAO:
            colocar = f'➕ {sug}'[:MAX_BOTAO]
        self.perguntar(T.sim_ou_acompanhamento(sug),
                       [(f'ok:{u["carrinho"]["id"][:12]}', T.B_FAZER_ASSIM), ('acomp', colocar), T.B_MUDAR_CURTO],
                       fase='confirmar')

    def colocar_sugestao(self, _arg=None):
        """➕ Colocar <sugestão>: a melhor oferta da mesma loja entra com 1 unidade (opção obrigatória
        vai no padrão, como na escolha falada) e o resumo volta, com entrega e pagamento refeitos."""
        u = self.u
        car = u.get('carrinho') or {}
        sug = u.get('sugestao_resumo')
        if u.get('fase') != 'confirmar' or not sug or not car.get('itens'):
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        pedido = {'termo': sug, 'busca': sug, 'quantidade': 1, 'observacao': None,
                  'tipo_loja': (u.get('atual') or {}).get('tipo_loja') or 'MERCADO'}
        ofertas, _ = self._coletar(pedido, car.get('loja_id'))
        if not ofertas:
            u['sugestao_sem_estoque'] = sug  # não oferece de novo o que a loja não tem
            self.dizer(T.nao_achei(sug, car.get('loja')))
            self.mostrar_resumo()
            return
        of = ofertas[0]
        item = self.ctx.ifood(self.wa).item(of['item_id'], of['loja_id'], u['endereco'])
        item['nome'] = item.get('nome') or of['nome']
        u['escolha'] = {'oferta': of, 'item': item, 'qtd': 1, 'obs': None, 'opcoes': [], 'grupo': 0, 'feitas': 0,
                        'termo': sug, 'tipo_loja': pedido['tipo_loja']}
        self._falado = {'texto': normalizar(sug), 'qtd': 1, 'fechar': True}  # coloca e volta direto pro resumo
        self._proximo_passo_da_escolha()

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
                          'resumo': T.lista_itens(car['itens'])[:300],
                          'total': car.get('total')}] + (u.get('pedidos') or []))[:PEDIDOS_GUARDADOS]
        pessoas = self._pessoas()
        u['carrinho'] = None
        u['grupo'] = None
        u['fila'] = []
        u['escolha'] = None
        u['plano'] = None
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
        # guardados pra responder depois "qual o código de entrega?", "como eu paguei?", "pra onde vai?"
        u['pedidos'][0].update(codigo_entrega=detalhes.get('codigo_entrega'),
                               pagamento=(car.get('pagamento') or {}).get('nome'),
                               endereco=(u.get('endereco') or {}).get('texto'),
                               tempo=(car.get('entrega') or {}).get('tempo'))
        self.dizer(T.pedido_feito(detalhes.get('codigo'), (car.get('entrega') or {}).get('tempo'),
                                  detalhes.get('codigo_entrega'), (car.get('pagamento') or {}).get('tipo'),
                                  total=car.get('total'), pessoas=pessoas))
        if u.get('voz'):  # tudo áudio: os avisos do pedido a caminho também (fim = pedido entregue)
            u['voz']['rastreando'] = feito['id']
        self._salvar()  # o rastreio roda em outro processo e lê o modo áudio do armazém
        self.ctx.iniciar_rastreio(self.wa, feito['id'])
        # lembrete só quando a compra se repete (item ou categoria, de qualquer loja) ou quando a pessoa
        # pediu pra agendar: na 1ª vez de um item ninguém quer ser cobrado de rotina
        repetidos = self._registrar_compra(car['itens'])
        dias_pedidos = u.pop('agendar_depois', None)
        rid = u.pop('via_lembrete', None)
        if rid:
            u['fase'] = 'acompanhando'  # já é recorrente: não oferece de novo
            if isinstance(rid, str):
                self.ctx.recorrencias.guardar_valores(self.wa, rid, car.get('subtotal'), car.get('total'))
        elif dias_pedidos:
            self.perguntar(T.oferecer_repetir(repetidos[0] if repetidos else None),
                           [(f'rec:{dias_pedidos}', T.quando(dias_pedidos, u.get('agendar_hora')).capitalize()),
                            T.B_REC_NAO],
                           fase='recorrencia')
        elif repetidos and self.ctx.agora() >= float(u.get('rec_pausa_ate') or 0):  # "Não precisa" vale 1 semana
            self.perguntar(T.oferecer_repetir(repetidos[0]), [T.B_REC_SEMANA, T.B_REC_MES, T.B_REC_NAO],
                           fase='recorrencia')
        else:
            u['fase'] = 'acompanhando'

    def _registrar_compra(self, itens):
        """Histórico de compras NOSSO (o iFood não diz se a pessoa já comprou aquilo): hist:{wa}
        = {nome normalizado: {nome, vezes, ultima}} + {'cat:<categoria>': ...}. Chave pelo nome, não
        pelo id: pão francês de outra padaria ainda é a 2ª vez do pão; e X-Bacon de uma hamburgueria
        depois de Smash Burger de outra é a 2ª vez de hambúrguer (categoria conta 1x por pedido).
        Devolve o que chegou agora na 2ª compra (só aí o automático é oferecido: a cada pedido vira
        chatice): categoria primeiro, depois nomes."""
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
            if h['vezes'] == 2:
                repetidos.append(h['nome'])
            cat = categoria(i.get('nome'))
            if cat and cat not in cats:
                cats.append(cat)
        for cat in cats:
            h = hist.get(f'cat:{cat}') or {'nome': cat, 'vezes': 0}
            h.update(vezes=h['vezes'] + 1, ultima=self.ctx.agora())
            hist[f'cat:{cat}'] = h
            if h['vezes'] == 2:
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
        u.update({'carrinho': None, 'fila': [], 'escolha': None, 'atual': None, 'pendente': None, 'grupo': None,
                  'kit': None, 'grupo_pendente': None, 'foto': None, 'plano': None, 'troca_de': None})
        self.menu(T.CANCELADO if tinha else 'Tudo bem! 🙂')

    # ================================================================== depois do pedido

    def acompanhar(self, _arg=None, sobre=None):
        """"cadê meu pedido" e qualquer pergunta sobre o pedido feito: responde o que perguntaram (código de
        entrega, quanto deu, o que veio, pagamento, endereço), não só o status (23h02 o "qual o código de
        entrega?" ganhou status duas vezes), e a pessoa volta pra etapa em que estava."""
        if not self.exigir_login(['botao', 'meu_pedido']):
            return
        car = self.u.get('carrinho') or {}
        if sobre == 'minimo':  # o mínimo da loja, não o carrinho (18/10: "qual o mínimo?" respondia R$ 18,89)
            self._responder_e_seguir(T.minimo_da_loja(car))
            return
        if sobre == 'total' and car.get('itens'):  # "quanto deu?" montando o pedido: é o carrinho de agora
            self._responder_e_seguir(T.ate_agora(car.get('total') or car.get('subtotal'), subtotal=car.get('subtotal')))
            return
        pedidos = self.u.get('pedidos') or []
        if not pedidos:
            self.perguntar(T.SEM_PEDIDO, self._menu(), fase='pedido')
            return
        ped = pedidos[0]
        if sobre == 'codigo_entrega' and not ped.get('codigo_entrega'):  # pedido de antes deste campo: busca
            try:
                ped['codigo_entrega'] = self.ctx.ifood(self.wa).pedido(ped['id']).get('codigo_entrega')
            except ErroMCP as e:
                print(f'getOrder pro código de entrega: {e!r}')
        resposta = T.sobre_pedido(sobre, ped, (self.u.get('endereco') or {}).get('texto'))
        if resposta:
            self._responder_e_seguir(resposta)
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
        # o status inteiro: onde está, quando chega, de onde vem, o código e o que vem (23h21 "Tá chegando?"
        # e "O entregador chegou?" ganharam uma linha só e os botões de pedir de novo)
        self._responder_e_seguir(T.como_esta(st.get('codigo'), st.get('descricao'), ped,
                                             _previsao(ped, self.ctx.agora()), sobre),
                                 [T.B_ATUALIZAR, T.B_PEDIR])

    def _responder_e_seguir(self, resposta, botoes=None):
        """Responde a pergunta e devolve a pessoa pra onde estava: no meio do endereço ou de um pedido a
        pergunta da etapa volta; fora disso, os atalhos."""
        fase = self.u.get('fase')
        if fase in ('endereco', 'complemento', 'bairro'):
            self._voltar_pra_etapa(resposta)
        elif fase in NO_MEIO_DO_PEDIDO and (self.u.get('pergunta') or {}).get('botoes'):
            # a pergunta na tela já diz isso ("Seu pedido até agora" no "quanto deu?"): não fala duas vezes
            ja_diz = resposta and resposta in (self.u['pergunta'].get('texto') or '')
            self.repetir_pergunta(None if ja_diz else resposta)
        else:
            self.perguntar(resposta, botoes or [T.B_MEU_PEDIDO, T.B_PEDIR], fase='acompanhando')

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
        self.u['grupo'] = None
        linhas = '\n'.join(f'• {i["qtd"]}x {i["nome"]}' for i in car.get('itens') or [])
        self.dizer(f'🔁 Montei igual da outra vez:\n{linhas}')
        self.finalizar()

    # ================================================================== recorrência

    def definir_recorrencia(self, arg):
        dias = int(arg) if str(arg).isdigit() else 0
        hora = self.u.pop('agendar_hora', None)
        ped = (self.u.get('pedidos') or [None])[0]
        if not dias or not ped:
            if not dias:  # "Não precisa": uma semana sem oferecer automático sozinho (pedir continua valendo)
                self.u['rec_pausa_ate'] = self.ctx.agora() + 7 * 86400
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
        resumo = T.lista_itens(car['itens'])
        demo = bool(self.ctx.armazem.get('cfg:demo_rapido'))
        rec = self.ctx.recorrencias.criar(
            self.wa, {'id': None, 'resumo': resumo, 'loja': car.get('loja'), 'subtotal': car.get('subtotal'),
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
            campo, teto = preco_da_ultima_vez(rec)
            self._direto = {'campo': campo, 'teto': teto, 'rid': rid}  # o "sim" aqui é a confirmação do pedido
            self._refazer(rec.get('pedido_id'), rec.get('loja'), modelo=rec if rec.get('itens') else None)
        elif oque == 'parar':
            self.ctx.recorrencias.remover(self.wa, rid)
            self.perguntar(T.LEMBRETE_PARADO, self._menu(), fase='pedido')
        else:
            self.ctx.recorrencias.respondido(self.wa, rid)
            self.perguntar(T.lembrete_adiado(rec.get('dias')), self._menu(), fase='pedido')

    def parar_lembretes(self):
        n = self.ctx.recorrencias.remover_todas(self.wa)
        self.perguntar(T.LEMBRETE_PARADO if n else 'Você não tem lembretes ligados. 🙂', self._menu(), fase='pedido')

    def _lembrete_pendente(self):
        """Lembrete que venceu quando a janela de 24h estava fechada: mostra agora."""
        rec = self.ctx.recorrencias.vencido_sem_aviso(self.wa)
        if not rec:
            return False
        self.ctx.recorrencias.avisado(self.wa, rec['id'])
        self.perguntar(T.lembrete(rec, self.u.get('endereco'), (self.u.get('pagamento_preferido') or {}).get('nome')),
                       botoes_lembrete(rec), fase='lembrete')
        return True

    # ================================================================== foto vira pedido

    def receber_fotos(self, fotos, texto='', outras=()):
        """Foto em qualquer etapa (até como 1ª mensagem) é pedido (src/bot/foto.py): comida pergunta se
        quer algo parecido; lista de compras ou produto vira a lista do pedido; o resto é comentado e a
        conversa volta pra onde estava. Legenda, texto e áudio da mesma rajada vão junto pro Gemini."""
        u = self.u
        arquivos = []
        for e in list(fotos)[:leitor_foto.MAX_FOTOS] + list(outras)[:1]:
            try:  # o áudio que o Scribe não entendeu já chega baixado
                mime, dados = (e.mime, e.dados) if e.dados else self.ctx.baixar_midia(e.media_id)
            except Exception as erro:  # noqa: BLE001
                print(f'baixar foto falhou: {erro!r}')
                continue
            arquivos.append((_mime_aceito(e.mime or mime), dados))  # o tipo que a Meta declarou na mensagem vale
        if not any(m.startswith(('image/', 'application/pdf')) for m, _ in arquivos):
            self._voltar_com(T.FOTO_RUIM)
            return
        try:
            lido = leitor_foto.ler(self.ctx.llm, u, arquivos, [texto] + [e.texto for e in fotos if e.texto])
        except ErroLLM as erro:
            print(f'LLM falhou lendo a foto: {erro!r}')
            self._voltar_com(T.FOTO_RUIM)
            return
        tipo = lido['tipo']
        # documento ou foto pessoal não vai pro log; o resto ajuda a entender o que o bot fez
        print(f'foto {self.wa}: {tipo}' + (f' {lido["descricao"][:80]!r}' if tipo != 'outro' else ''))
        self._disse = ' / '.join(x for x in (self._disse, f'[foto: {lido["descricao"]}]' if tipo != 'outro' else '[foto]')
                                 if x)[:300]
        if tipo in ('lista', 'produto') or (tipo == 'outro' and lido['itens']):
            itens = lido['itens']  # foto de outra coisa + "quero pão" escrito: o pão ainda é o pedido
            if not itens:
                self._voltar_com(T.FOTO_ILEGIVEL)
                return
            it = {'acao': 'comprar', 'itens': itens}
            if u.get('fase') in ('endereco', 'complemento', 'bairro'):
                u['pendente'] = it  # no meio do endereço a lista espera ele terminar, como um pedido escrito
                self._voltar_pra_etapa(T.li_a_foto(itens))
                return
            if len(itens) == 1 or not self.logado():  # lista longa já vem com o "Anotei sua lista"
                self.dizer(T.li_a_foto(itens))
            self.intencao(it)
            return
        if tipo == 'comida' and lido['parecidos']:
            u['contador'] = int(u.get('contador') or 0) + 1
            u['foto'] = {'id': u['contador'], 'descricao': lido['descricao'], 'parecidos': lido['parecidos'],
                         'quantidade': lido['quantidade'], 'quando': self.ctx.agora()}
            escrito = ' '.join([texto] + [e.texto for e in fotos])
            pessoas = lido['pessoas'] or kit_grupo.pessoas_em(escrito)  # o modelo às vezes não preenche
            if (pessoas and pessoas > 1) or u.get('fase') == 'grupo_tema':  # "pizza dessas pra 5": é o kit
                self.intencao({'acao': 'grupo', 'numero': pessoas, 'itens': lido['parecidos'][:1]})
            elif lido['ja_pediu'] or QUER_ISSO.search(normalizar(escrito)):
                # "quero isso", "me vê 2 desse": não pergunta o que ela já disse
                self.foto_sim()
            else:
                fid = u['foto']['id']
                self.perguntar(T.foto_parecido(lido['descricao'], lido['resposta']),
                               [(f'{T.B_FOTO_SIM[0]}:{fid}', T.B_FOTO_SIM[1]), (f'{T.B_FOTO_NAO[0]}:{fid}', T.B_FOTO_NAO[1])],
                               fase='foto')
            return
        if u.get('fase') == 'escolhendo':
            # foto sem relação no meio dos cards: o rodapé "Gostou de algum?" sem card nenhum e o "sim" de
            # depois caindo nos cards antigos confundiam; volta pro menu sem os cards na memória
            u.update(visiveis=[], lista_atual=None)
            self.menu(T.foto_outro(lido['resposta']))
            return
        self._voltar_com(T.foto_outro(lido['resposta']))

    def _voltar_com(self, fala):
        """Responde e volta pra onde a pessoa estava: etapa escrita (endereço, bairro), pergunta com
        botões, ou o menu (sem login, o menu é o botão de entrar)."""
        u = self.u
        if u.get('fase') in ('endereco', 'bairro'):
            self._voltar_pra_etapa(fala)
        elif (u.get('pergunta') or {}).get('botoes') and u.get('fase') not in ('foto', None, 'inicio'):
            self.repetir_pergunta(fala)
        elif not self.logado():
            self.dizer(fala)
            self.pedir_login()
        else:
            self.menu(fala)

    def responder_foto(self, arg):
        oque, _, fid = str(arg).partition(':')
        atual = (self.u.get('foto') or {}).get('id')
        if fid and str(atual) != fid:  # "Sim" de uma foto antiga: não busca os parecidos da foto nova
            self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if oque == 'sim':
            self.foto_sim()
            return
        self.u['foto'] = None
        self.menu('Tudo bem! 🙂')

    def foto_sim(self, _arg=None):
        f = self.u.get('foto') or {}
        if not f.get('parecidos'):
            self.perguntar_pedido()
            return
        if not self.exigir_login(['botao', f'foto:sim:{f.get("id")}']):
            return
        if not self.garantir_endereco({'acao': 'botao', 'botao': f'foto:sim:{f.get("id")}'}):
            return
        self.buscar_parecidos(f)

    def buscar_parecidos(self, f):
        """Junta num carrossel só o que achar dos parecidos (do mais parecido pro mais genérico), no
        máximo 3 buscas. Com pedido montado, só na loja dele (um pedido é de uma loja)."""
        u = self.u
        car = u.get('carrinho') or {}
        loja_id = car.get('loja_id') if car.get('itens') else None
        juntas, primeiro, proxima = [], None, None
        for p in f['parecidos'][:3]:
            pedido = {**p, 'quantidade': f.get('quantidade'), 'observacao': p.get('observacao')}
            ofertas, prox = self._coletar(pedido, loja_id)
            ja = {o['item_id'] for o in juntas}
            novas = [o for o in ofertas if o['item_id'] not in ja]
            if novas and primeiro is None:
                primeiro, proxima = pedido, prox
            juntas += novas
            if len(juntas) >= 6:
                break
        if not juntas:
            botoes = [T.B_FINALIZAR, T.B_INICIO] if car.get('itens') else [T.B_ESCREVER, T.B_INICIO]
            self.perguntar(T.sem_parecido(f.get('descricao'), car.get('loja') if loja_id else None), botoes,
                           fase='pedido')
            return
        u['atual'] = primeiro
        self._mostrar_lista(primeiro, juntas, proxima, loja_id, antes=T.parecidos(f.get('descricao')),
                            termo='opções parecidas')

    # ================================================================== dividir com os amigos

    def _pessoas(self):
        """Quantas pessoas dividem o pedido montado (kit em grupo ou "vamos dividir em 3"); None se não divide."""
        g = self.u.get('grupo') or {}
        car = self.u.get('carrinho') or {}
        if g.get('pessoas') and car.get('itens') and car.get('loja_id') == g.get('loja_id'):
            return g['pessoas']
        return None

    def grupo(self, it):
        """"Lanchar em 5 pessoas hambúrguer" (src/bot/grupo.py). Junta o que já foi dito antes (quantas
        pessoas, o que comer) e pergunta só o que falta. Com o kit na tela, é ajuste do kit; sem comida
        dita e com pedido montado, divide o pedido que já existe."""
        u = self.u
        itens = [i for i in it.get('itens') or [] if i.get('termo')]
        pessoas = it.get('numero') if isinstance(it.get('numero'), int) and it['numero'] > 0 else None
        ajuste = (it.get('texto') or '').strip()[:200] or None
        kit = u.get('kit') if u.get('fase') == 'kit' else None
        if not pessoas and not kit:  # o Gemini não preencheu: "eu e mais 3" pela regra (no ajuste do kit, não mudou)
            pessoas = kit_grupo.pessoas_em(self._disse)
        pend = u.get('grupo_pendente') or {}
        if kit:  # ajuste do kit que está na tela
            tema, extras, anterior = kit['tema'], list(kit.get('extras') or []), kit
            if itens and kit_grupo.tema_em(itens[0]['termo']) and not _mesmo_termo(itens[0], tema):
                tema, extras, anterior = itens[0], itens[1:], None  # "na verdade quero pizza": outro kit
            else:
                extras += [i for i in itens if not _mesmo_termo(i, tema)
                           and not any(_mesmo_termo(i, e) for e in extras)]
            self._montar_kit(pessoas or kit['pessoas'], tema, extras, ajuste or kit.get('ajuste'), anterior=anterior)
            return
        car = u.get('carrinho') or {}
        if not itens and not car.get('itens'):
            # o Gemini às vezes deixa a comida só no texto ("pizza com 4 amigos" -> itens vazio): a regra acha
            dito = ' '.join(x for x in (it.get('texto'), self._disse) if x)
            tema_dito = kit_grupo.tema_em(dito)
            if tema_dito:
                itens = [tema_dito] + kit_grupo.bebidas_em(dito)
                if ajuste and normalizar(ajuste) in normalizar(self._disse):
                    ajuste = None  # era a frase inteira, não uma restrição
        if not itens and not pend.get('tema') and (pend.get('dividir') or (car.get('itens') and u.get('fase') != 'grupo_tema')):
            self._dividir_pedido(pessoas)
            return
        tema = itens[0] if itens else pend.get('tema')
        extras = itens[1:] if itens else list(pend.get('extras') or [])
        pessoas = pessoas or pend.get('pessoas')
        ajuste = ajuste or pend.get('ajuste')
        if tema:
            conhecido = kit_grupo.tema_em(tema['termo'])
            if conhecido and tema.get('tipo_loja') != conhecido['tipo_loja']:
                tema = {**tema, 'tipo_loja': conhecido['tipo_loja']}  # pizza pra galera é de restaurante
        if not tema:
            u['grupo_pendente'] = {'pessoas': pessoas, 'ajuste': ajuste}
            self.perguntar(T.grupo_o_que(pessoas), [T.B_INICIO], fase='grupo_tema')
            return
        if not pessoas or pessoas > kit_grupo.MAX_PESSOAS:
            u['grupo_pendente'] = {'tema': tema, 'extras': extras, 'ajuste': ajuste}
            self.perguntar(T.GRUPO_DEMAIS if pessoas else T.GRUPO_QUANTAS, T.B_PESSOAS, fase='grupo_pessoas')
            return
        u['grupo_pendente'] = None
        if pessoas == 1:  # "pra mim só": pedido normal
            self.iniciar_compra([tema] + extras)
            return
        self._montar_kit(pessoas, tema, extras, ajuste)

    def grupo_pessoas(self, arg):
        n = arg if isinstance(arg, int) else (int(arg) if str(arg).isdigit() else numero_em(str(arg)))
        if not n or n < 1:
            self.perguntar(T.GRUPO_QUANTAS, T.B_PESSOAS, fase='grupo_pessoas')
            return
        self.grupo({'acao': 'grupo', 'numero': n})

    def _dividir_pedido(self, pessoas):
        """"Vamos dividir em 3": o pedido que já está montado ganha o "por pessoa" no total e no resumo."""
        u = self.u
        car = u.get('carrinho') or {}
        if not car.get('itens'):
            u['grupo_pendente'] = {'pessoas': pessoas}
            self.perguntar(T.grupo_o_que(pessoas), [T.B_INICIO], fase='grupo_tema')
            return
        if not pessoas or pessoas > kit_grupo.MAX_PESSOAS:
            u['grupo_pendente'] = {'dividir': True}
            self.perguntar(T.GRUPO_DEMAIS if pessoas else T.GRUPO_QUANTAS, T.B_PESSOAS, fase='grupo_pessoas')
            return
        u['grupo_pendente'] = None
        u['grupo'] = {'pessoas': pessoas, 'loja_id': car.get('loja_id')} if pessoas > 1 else None
        self.mostrar_carrinho()

    def _montar_kit(self, pessoas, tema, extras=(), ajuste=None, anterior=None, outra_loja=False):
        u = self.u
        it = {'acao': 'grupo', 'numero': pessoas, 'itens': [tema] + list(extras), 'texto': ajuste}
        if not self.exigir_login(it):
            return
        if not self.garantir_endereco(it):
            return
        if not anterior:  # remontar é rápido; o 1º kit busca loja, cardápio e acompanhamentos
            self.dizer(T.montando_kit(pessoas, tema['termo']))
        kit, motivo = kit_grupo.montar(self.ctx.ifood(self.wa), self.ctx.llm, u['endereco'], pessoas, tema,
                                       extras, ajuste, anterior=anterior, outra_loja=outra_loja)
        if not kit:
            if motivo == 'sem_loja' and anterior:
                u['kit'] = {**anterior, 'tem_outra': False}
                self._mostrar_kit(T.KIT_SEM_OUTRA_LOJA)
                return
            u['kit'] = None
            u['grupo_pendente'] = {'pessoas': pessoas}
            self.perguntar(T.kit_sem_principal(tema['termo']), [T.B_INICIO], fase='grupo_tema')
            return
        u['contador'] = int(u.get('contador') or 0) + 1
        kit['id'] = u['contador']
        u['kit'] = kit
        self._mostrar_kit()

    def _mostrar_kit(self, prefixo=None):
        k = self.u['kit']
        car = self.u.get('carrinho') or {}
        troca = car.get('loja') if car.get('itens') and car.get('loja_id') != k['loja_id'] else None
        botoes = [(f'{b[0]}:{k.get("id")}', b[1]) for b in
                  [T.B_KIT_OK] + ([T.B_KIT_OUTRA] if k.get('tem_outra') else []) + [T.B_KIT_NAO]]
        texto = T.kit(k, troca)
        self.perguntar(f'{prefixo}\n\n{texto}' if prefixo else texto, botoes, fase='kit')

    def responder_kit(self, arg):
        k = self.u.get('kit')
        arg, _, kid = str(arg).partition(':')
        if kid and k and str(k.get('id')) != kid and arg != 'nao':
            # "Quero esse kit" de um kit antigo: mostra o kit de agora em vez de comprar o que ela não viu
            self._mostrar_kit(T.BOTAO_VELHO) if self.u.get('fase') == 'kit' else self.repetir_pergunta(T.BOTAO_VELHO)
            return
        if arg == 'nao':
            self.u['kit'] = None
            self.menu('Tudo bem! 🙂')
        elif not k or not k.get('linhas'):
            self.repetir_pergunta(T.BOTAO_VELHO) if self.u.get('fase') != 'kit' else self.perguntar_pedido()
        elif arg == 'outra':
            self._montar_kit(k['pessoas'], k['tema'], k.get('extras'), k.get('ajuste'), anterior=k, outra_loja=True)
        else:
            self.kit_ok()

    def kit_ok(self, _arg=None):
        """"Quero esse kit": só agora o carrinho é criado. Pedido montado na mesma loja ganha o kit junto;
        de outra loja é trocado (o kit avisou). Daí em diante é o pedido de sempre, com o "por pessoa"."""
        u = self.u
        k = u.get('kit')
        if not k or not k.get('linhas'):
            self.perguntar_pedido()
            return
        if not self.exigir_login(['botao', f'kit:ok:{k.get("id")}']):
            return
        if not self.garantir_endereco({'acao': 'botao', 'botao': f'kit:ok:{k.get("id")}'}):
            return
        car = u.get('carrinho') or {}
        linhas = [{'item_id': lin['item_id'], 'qtd': lin['qtd'], 'opcoes': lin['opcoes'], 'obs': None}
                  for lin in k['linhas']]
        if car.get('itens') and car.get('loja_id') == k['loja_id']:
            linhas = [{'item_id': i['item_id'], 'qtd': i['qtd'], 'opcoes': i.get('opcoes') or [],
                       'obs': i.get('obs')} for i in car['itens']] + linhas
        novo = self.ctx.ifood(self.wa).criar_carrinho(k['loja_id'], u['endereco']['id'], linhas)
        novo['loja'] = novo.get('loja') or k['loja']
        # o iFood não devolve as opções escolhidas: guardamos por linha pra conseguir refazer o carrinho depois
        fila = {}
        for lin in linhas:
            fila.setdefault(lin['item_id'], []).append((lin['opcoes'], lin['obs']))
        for i in novo.get('itens') or []:
            guardadas = fila.get(i.get('item_id')) or []
            i['opcoes'], i['obs'] = guardadas.pop(0) if guardadas else ([], None)
        u.update(carrinho=novo, fila=[], escolha=None, kit=None, grupo_pendente=None,
                 grupo={'pessoas': k['pessoas'], 'loja_id': k['loja_id']})
        self.dizer(T.kit_no_pedido(novo['loja']))
        self._proximo_da_fila()

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


def _mesmo_termo(a, b):
    return normalizar((a or {}).get('termo')) == normalizar((b or {}).get('termo'))


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
# legenda da foto que já é o pedido: "quero isso", "me vê 2 desse", "acha um igual"
QUER_ISSO = re.compile(r'\b(quero|queria|me ve|manda|pede|pedir|acha|procura|tem esse|tem essa|desse|dessa|igual)\b')
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


# o que vem em volta do produto quando o Gemini cai ("quero jantar pizza hj" -> "pizza")
ENCHIMENTO = {'quero', 'queria', 'quer', 'gostaria', 'pode', 'me', 've', 'manda', 'traz', 'pede', 'pedir',
              'comer', 'jantar', 'almocar', 'lanchar', 'tomar', 'beber', 'hoje', 'hj', 'agora', 'ja', 'pra',
              'para', 'mim', 'eu', 'um', 'uma', 'uns', 'umas', 'o', 'a', 'por', 'favor', 'pf', 'pfv', 'ai',
              'aqui', 'oi', 'ola'}
# categoria (recorrencia.categoria) que só restaurante vende: sem Gemini, a busca vai pra vertical certa
DE_RESTAURANTE = {'hambúrguer', 'pizza', 'açaí', 'sushi', 'pastel', 'esfiha', 'marmita', 'lanche', 'frango',
                  'sorvete'}
# "quero esse e pode fechar", "é só isso": a escolha falada vai direto pro fim do checkout
FECHAR = re.compile(r'\b(pode fechar|ja fecha|fecha (o pedido|ai|isso|tudo)|fechar|finaliza\w*|e so isso|so isso)\b')
# "vou pagar no pix": vira a forma preferida (o Gemini manda no campo pagamento; sem ele, pelo texto)
PAGAMENTO_DITO = {'PIX': 'PIX', 'VALE_REFEICAO': 'MEAL_VOUCHER', 'VALE_ALIMENTACAO': 'FOOD_VOUCHER'}
PAGAMENTO_NO_TEXTO = [(re.compile(r'\bpix\b'), 'PIX'), (re.compile(r'\b(vale refeicao|vr)\b'), 'MEAL_VOUCHER'),
                      (re.compile(r'\bvale alimentacao\b'), 'FOOD_VOUCHER')]
NOME_PAGAMENTO_DITO = {'PIX': 'PIX', 'MEAL_VOUCHER': 'Vale-refeição', 'FOOD_VOUCHER': 'Vale-alimentação'}


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


ORDINAIS = {'primeiro': 1, 'primeira': 1, 'segundo': 2, 'segunda': 2, 'terceiro': 3, 'terceira': 3,
            'quarto': 4, 'quarta': 4, 'quinto': 5, 'quinta': 5}
ARTIGOS = {'o', 'a', 'da', 'do', 'na', 'no', 'pela', 'pelo'}
CARDINAIS = {'um': 1, 'dois': 2, 'tres': 3, 'quatro': 4, 'cinco': 5}   # "o um", "opção dois", "foto três"
CPF_NO_TEXTO = re.compile(r'\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}\b')
CPF_ANTES = re.compile(r'(?i)\b(?:(?:o\s+)?meu\s+)?cpf\s*(?:é|e|eh|:|=)?\s*$')
ENCHIMENTO_CPF = {'meu', 'o', 'cpf', 'e', 'eh', 'na', 'nota', 'fiscal', 'pra', 'para', 'com', 'segue', 'ai',
                  'aqui', 'ta', 'esta', 'numero', 'do', 'da', 'coloca', 'poe', 'bota', 'ok'}


def _hora_br(ts):
    return time.strftime('%Hh%M', time.gmtime(ts - 3 * 3600))  # Brasília: UTC-3, sem horário de verão


def _previsao(pedido, agora):
    """"entre 23h46 e 23h56": hora do pedido + tempo de entrega da loja ("25-35 min"). Passou do fim: "até
    as 23h56". None sem os dois dados."""
    nums = [int(n) for n in re.findall(r'\d+', str(pedido.get('tempo') or ''))][:2]
    quando = pedido.get('quando')
    if not nums or not quando:
        return None
    ini, fim = float(quando) + nums[0] * 60, float(quando) + nums[-1] * 60
    if agora > fim:
        return f'até as {_hora_br(fim)}'
    if nums[0] == nums[-1]:
        return f'por volta das {_hora_br(fim)}'
    return f'entre {_hora_br(ini)} e {_hora_br(fim)}'


def _posicao_dita(disse, quantos):
    """"a primeira foto", "o segundo", "o último", "o do meio", "o um", "opção dois": a posição dita
    (1..quantos) ou None. Só com artigo (ou "opção", "número", "foto") antes, e nunca "segunda-feira",
    "primeira vez" nem "arroz tipo um"."""
    palavras = normalizar(disse or '').split()
    posicao = None
    for k, w in enumerate(palavras):
        antes = palavras[k - 1] if k else ''
        depois = palavras[k + 1] if k + 1 < len(palavras) else ''
        if antes not in ARTIGOS | {'numero', 'opcao', 'foto'} or depois in ('feira', 'vez'):
            continue
        if w in ORDINAIS:
            posicao = ORDINAIS[w]
        elif w in CARDINAIS and antes in ARTIGOS | {'numero', 'opcao', 'foto'}:
            posicao = CARDINAIS[w]
        elif w in ('ultimo', 'ultima'):
            posicao = quantos
        elif w == 'meio' and quantos % 2:
            posicao = quantos // 2 + 1
    return posicao if posicao and posicao <= quantos else None


def _sem_cpf(texto):
    """Número com cara de CPF vira [CPF]: o _disse vai pro LLM (voz e tutor)."""
    return CPF_NO_TEXTO.sub('[CPF]', texto or '')


def _cpf_no_texto(texto):
    """CPF válido no meio de qualquer mensagem ("meu cpf é 529.982.247-25"): (cpf, texto sem ele) ou None.
    O que sobra do tipo "meu cpf é" some junto."""
    for m in CPF_NO_TEXTO.finditer(texto or ''):
        cpf = cpf_em(m.group(0))
        if cpf:
            antes = CPF_ANTES.sub('', texto[:m.start()])  # "meu cpf é " colado no número sai junto
            resto = ' '.join(f'{antes} {texto[m.end():]}'.split()).strip(' ,.;:-')
            return cpf, '' if set(normalizar(resto).split()) <= ENCHIMENTO_CPF else resto
    return None


def _da_hora(agora):
    """Sugestão sem carrinho nem histórico: algo da hora do dia em Brasília (UTC-3, sem horário de verão)."""
    h = time.gmtime(agora - 3 * 3600).tm_hour
    if 5 <= h < 11:
        return [('pão francês', 'MERCADO'), ('café', 'RESTAURANTE')]
    if 11 <= h < 15:
        return [('marmita', 'RESTAURANTE'), ('lanche', 'RESTAURANTE')]
    if 15 <= h < 18:
        return [('lanche', 'RESTAURANTE'), ('pão de queijo', 'RESTAURANTE')]
    return [('pizza', 'RESTAURANTE'), ('hambúrguer', 'RESTAURANTE')]


def _marca_resumo(car):
    """Do que o resumo na tela fala: mudou item, entrega, pagamento ou valor, o resumo é outro."""
    return [car.get('id'), car.get('total'), len(car.get('itens') or []),
            (car.get('entrega') or {}).get('id'), (car.get('pagamento') or {}).get('tipo')]


def _falta_minimo(car):
    """(falta, loja) pro aviso do "Quer mais alguma coisa?": sem ele o Finalizar parecia travado à toa."""
    return (car.get('minimo') or 0) - (car.get('subtotal') or 0), car.get('loja')
