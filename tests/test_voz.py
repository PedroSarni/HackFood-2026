"""Modo áudio: só liga quando a pessoa pede, fala como atendente e desliga no fim da sessão."""
import pytest

from src.bot import textos as T
from src.bot import voz
from src.bot.fluxo import IDLE_MAX
from tests.fakes import Mundo
from tests.test_fluxo import endereco_pronto, pedido_ate_o_resumo

OGG = b'OggS-nota-de-voz'


class Locutor:
    """ElevenLabs de mentirinha: anota o que mandaram falar."""

    def __init__(self, falhar=False):
        self.falas = []
        self.falhar = falhar

    def __call__(self, texto):
        if self.falhar:
            raise RuntimeError('elevenlabs fora do ar')
        self.falas.append(texto)
        return 'audio/ogg', OGG


def mundo_com_voz(**kw):
    loc = Locutor(**kw)
    return Mundo(locutor=loc), loc


def tipos(m):
    return [t for t, _ in m.wpp.saida]


def escritos(m):
    """Só as mensagens de texto puro (as que o modo áudio deveria engolir)."""
    return [d['texto'] for t, d in m.wpp.saida if t == 'texto']


# --- quem pediu e quem não pediu -------------------------------------------------------------

PEDIDOS = ['me responde por áudio', 'Me responde por audio por favor', 'pode me responder em áudio?',
           'manda áudio', 'me manda um áudio', 'fala comigo por áudio', 'pode falar comigo por voz',
           'quero que você me responda por áudio', 'prefiro áudio', 'prefiro ouvir', 'pode ser por áudio',
           'Me responde só por áudio, não sei ler direito', 'grava um áudio pra mim',
           'Oi, pode me mandar mensagem de voz?', 'responde por voz', 'podia me responder por audio',
           'quero pão e me responde por áudio', 'manda audio pra mim']
NAO_SAO = ['posso mandar áudio?', 'vou te mandar um áudio', 'te mandei um áudio', 'mandei áudio',
           'você ouve áudio?', 'aceita áudio?', 'quero pão', 'o áudio não carregou', 'não manda áudio',
           'para de mandar áudio', 'pode escrever', 'falei no audio que quero pao', 'escutou meu áudio?',
           'deixa eu gravar um audio', 'meu audio ficou ruim', 'quero fone de ouvido', 'caixa de som',
           'posso mandar mensagem de voz?', 'audio', 'voz']


@pytest.mark.parametrize('frase', PEDIDOS)
def test_reconhece_pedido_de_resposta_em_audio(frase):
    assert voz.pediu_audio(frase)


@pytest.mark.parametrize('frase', NAO_SAO)
def test_nao_confunde_com_a_pessoa_mandando_audio(frase):
    assert not voz.pediu_audio(frase)


@pytest.mark.parametrize('frase', ['pode escrever', 'para de mandar áudio', 'não precisa de áudio',
                                   'volta a escrever', 'prefiro texto', 'responde por escrito',
                                   'não consigo ouvir áudio agora', 'manda escrito'])
def test_reconhece_pedido_de_voltar_pro_texto(frase):
    assert voz.pediu_texto(frase)


@pytest.mark.parametrize('frase,resto', [
    ('me responde por áudio', ''), ('Me responde por áudio, por favor!', ''),
    ('quero pão e me responde por áudio', 'quero pão'), ('Me responde por áudio. Quero leite', 'Quero leite'),
    ('grava um áudio pra mim', ''), ('quero leite', 'quero leite')])
def test_recorta_o_pedido_e_deixa_o_resto(frase, resto):
    assert voz.resto_do_pedido(frase, voz.PEDE_AUDIO) == resto


# --- liga só quando pede -------------------------------------------------------------------

def so_audio(m):
    """No modo áudio a pessoa só recebe nota de voz (17/10 22h: texto + áudio foi reclamação), fora
    as fotos numeradas das opções de produto (17/10 23h), que vêm antes do áudio."""
    t = tipos(m)
    return bool(t) and t[-1] == 'audio' and set(t) <= {'audio', 'imagem'} and all(d.get('legenda', '') in voz.NUMEROS.values() for k, d in m.wpp.saida if k == 'imagem')


def test_opcoes_de_produto_chegam_como_fotos_numeradas_e_depois_o_audio():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('me responde por áudio')
    m.wpp.limpar()
    m.enviar('quero leite')
    fotos = [d for k, d in m.wpp.saida if k == 'imagem']
    assert len(fotos) == 3 and [d['legenda'] for d in fotos] == ['1️⃣', '2️⃣', '3️⃣']
    assert tipos(m) == ['imagem', 'imagem', 'imagem', 'audio']  # nada de card, botão ou texto
    assert 'Te mandei as fotos' in loc.falas[-1] or 'foto' in loc.falas[-1].lower()


def test_sem_pedido_nunca_manda_audio():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('quero leite')
    assert 'audio' not in tipos(m) and not loc.falas
    assert not m.estado().get('voz')


def test_pedido_de_audio_responde_so_com_audio():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio')
    assert m.estado()['voz']
    assert so_audio(m) and len(m.wpp.saida) == 1 and m.wpp.saida[0][1]['voz'] is True  # UMA nota de voz
    assert len(loc.falas) == 1 and 'áudio ou escrevendo' in loc.falas[0]
    assert m.wpp.midias and b'audio/ogg' in m.wpp.midias[0]  # subiu o ogg pra Meta
    assert m.estado()['pergunta']['botoes']  # a pergunta continua valendo pra resposta falada


def test_audio_nunca_fala_de_botao_nem_de_tela():
    m, loc = mundo_com_voz()
    m.llm.falhar = True  # roteiro simples: é o caminho que mais carrega texto de tela ("Toque em...")
    m.enviar('me responde por áudio')
    m.llm.falhar = False
    endereco_pronto_falando(m)
    m.llm.falhar = True
    m.enviar('o primeiro')
    for fala in loc.falas:
        assert not voz._TELA.search(fala), fala


def endereco_pronto_falando(m):
    """O mesmo cadastro de endereço de test_fluxo, mas respondendo de boca (sem botão na tela)."""
    m.enviar('quero pao')
    m.enviar('Rua das Flores, 120, São Carlos')
    assert m.estado()['fase'] == 'endereco_escolha'
    m.enviar('é no centro')      # frase falada com o nome do bairro: casa com a opção "1 · Centro"
    assert m.estado()['fase'] == 'complemento'
    m.enviar('não tem')


def test_pedido_inteiro_so_falando():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio')
    endereco_pronto_falando(m)
    assert m.estado()['fase'] == 'escolhendo'
    assert len(m.estado()['visiveis']) == 3                 # 3 opções por vez: dá pra guardar de ouvido
    assert 'o primeiro' in loc.falas[-1] and 'o terceiro' in loc.falas[-1]  # as opções foram ditas
    m.enviar('o segundo')
    assert m.estado()['fase'] == 'quantidade'
    m.enviar('10')
    m.enviar('finalizar pedido')                             # o texto da opção, dito
    if m.estado()['fase'] == 'pagamento':
        m.enviar('pix')
    assert m.estado()['fase'] == 'cpf'
    m.enviar('529.982.247-25')
    assert m.estado()['fase'] == 'confirmar'
    m.wpp.limpar()
    m.enviar('sim')
    assert len(m.mcp.chamadas_de('submitOrder')) == 1
    assert so_audio(m)                                       # até o "pedido feito" é só áudio
    assert 'Pedido feito' in loc.falas[-1] or 'pedido feito' in loc.falas[-1].lower()
    # 17/10: os avisos do pedido a caminho também são áudio; a sessão acaba quando ele chega
    assert m.estado()['voz']['rastreando'] == m.rastreios[-1]
    from src.bot.rastreio import acompanhar
    m.wpp.limpar()
    fim = acompanhar(m.ctx, m.wa, m.rastreios[-1], dormir=lambda s: None)
    assert fim == 'DELIVERED'
    assert tipos(m) and set(tipos(m)) == {'audio'}           # "confirmou", "saiu", "chegou": tudo falado
    assert 'entregue' in loc.falas[-1].lower()
    m.wpp.limpar()
    m.enviar('oi')                                           # acabou a sessão, acabou o áudio
    assert not m.estado().get('voz') and 'audio' not in tipos(m)


def test_sem_modo_audio_o_rastreio_continua_escrito():
    m, loc = mundo_com_voz()
    pedido_ate_o_resumo(m)
    m.tocar('ok:')
    from src.bot.rastreio import acompanhar
    m.wpp.limpar()
    acompanhar(m.ctx, m.wa, m.rastreios[-1], dormir=lambda s: None)
    assert tipos(m) and set(tipos(m)) == {'texto'} and not loc.falas


def test_rastreio_com_voz_fora_do_ar_manda_escrito():
    m, loc = mundo_com_voz()
    pedido_ate_o_resumo(m)
    m.enviar('me responde por áudio')  # liga no resumo (no modo áudio não tem botão pra tocar)
    m.enviar('sim')
    assert m.estado()['voz']['rastreando']
    loc.falhar = True
    from src.bot.rastreio import acompanhar
    m.wpp.limpar()
    acompanhar(m.ctx, m.wa, m.rastreios[-1], dormir=lambda s: None)
    assert tipos(m) and set(tipos(m)) == {'texto'}           # ninguém fica sem a notícia


def test_pedido_de_audio_junto_com_o_pedido_de_compra():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar('quero leite e me responde por áudio')
    assert m.estado()['voz']
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'leite'  # o resto seguiu o fluxo
    assert so_audio(m)


def test_pedido_falado_tambem_liga():
    m = Mundo(locutor=Locutor(), transcritor=lambda mime, dados: 'me responde por áudio, por favor')
    m.enviar(('audio', 'midia1'))
    assert m.estado()['voz'] and so_audio(m)


def test_quem_pergunta_se_pode_mandar_audio_continua_no_texto():
    m, loc = mundo_com_voz()
    m.enviar('posso mandar áudio?')
    assert not m.estado().get('voz') and 'audio' not in tipos(m)


def test_pedido_no_meio_do_endereco_repete_a_pergunta_do_endereco():
    m, loc = mundo_com_voz()
    m.enviar('quero pão')  # sem endereço: pede o endereço
    assert m.estado()['fase'] == 'endereco'
    m.enviar('me responde por áudio')
    assert m.estado()['fase'] == 'endereco'  # não jogou pro menu
    assert 'Pra onde eu mando' in loc.falas[-1]


def test_login_e_a_unica_coisa_que_aparece_na_tela():
    loc = Locutor()
    m = Mundo(logado=False, locutor=loc)
    m.enviar('me responde por áudio')
    assert tipos(m) == ['link', 'audio']  # sem o link não dá pra entrar; o resto é falado


def test_ligar_com_conversa_junto_nao_vira_nao_entendi():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio, não enxergo bem')  # o fake diz nao_entendi pro resto
    assert m.estado()['voz'] and so_audio(m)
    assert T.NAO_ENTENDI not in ' '.join(loc.falas) and 'Desculpe' not in loc.falas[-1]


# --- plano B --------------------------------------------------------------------------------

def test_voz_fora_do_ar_manda_as_mensagens_normais():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('me responde por áudio')
    loc.falhar = True  # soluço da ElevenLabs no meio da conversa
    m.wpp.limpar()
    m.enviar('quero leite')
    assert 'audio' not in tipos(m)
    assert 'carrossel' in tipos(m) or m.wpp.cards()        # o que foi segurado saiu, com as opções
    assert any('Entregando em' in t for t in escritos(m))
    assert m.estado()['voz']                                # já tinha falado antes: a próxima tenta de novo


def test_primeiro_audio_falhou_nao_promete_audio():
    m, loc = mundo_com_voz(falhar=True)  # key sem permissão de text_to_speech, por exemplo
    m.enviar('me responde por áudio')
    assert T.VOZ_INDISPONIVEL in escritos(m) and T.VOZ_LIGADA not in escritos(m)
    assert m.wpp.ultimos_botoes()                           # o menu saiu, com botões
    assert not m.estado().get('voz')                        # não fica tentando (e falhando) a cada mensagem


def test_sem_elevenlabs_avisa_e_nao_liga():
    m = Mundo()  # sem locutor
    m.enviar('me responde por áudio')
    assert not m.estado().get('voz')
    assert T.VOZ_INDISPONIVEL in escritos(m) and 'audio' not in tipos(m)


def test_sem_gemini_o_roteiro_simples_ainda_fala():
    m, loc = mundo_com_voz()
    m.llm.falhar = True
    m.enviar('me responde por áudio')
    assert so_audio(m) and loc.falas[-1].endswith(voz.CONVITE)


# --- desliga -------------------------------------------------------------------------------

def test_pode_escrever_volta_pro_texto():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio')
    m.wpp.limpar()
    m.enviar('pode escrever')
    assert not m.estado().get('voz')
    assert T.VOZ_DESLIGADA in escritos(m) and 'audio' not in tipos(m)


def test_sumiu_meia_hora_a_proxima_volta_escrita():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('me responde por áudio')
    m.agora += IDLE_MAX + 60
    m.wpp.limpar()
    m.enviar('quero leite')
    assert not m.estado().get('voz') and 'audio' not in tipos(m)


def test_no_cpf_o_audio_pede_pra_escrever():
    m, loc = mundo_com_voz()
    m.llm.falhar = True  # roteiro simples: o convite é nosso, dá pra conferir
    m.enviar('me responde por áudio')
    m.llm.falhar = False
    endereco_pronto_falando(m)
    m.enviar('o primeiro')
    m.enviar('10')
    m.llm.falhar = True
    m.enviar('finalizar pedido')
    if m.estado()['fase'] == 'pagamento':
        m.enviar('pix')
    assert m.estado()['fase'] == 'cpf'
    assert loc.falas[-1].endswith(voz.CONVITE_CPF)  # CPF escrito; áudio ali = sem CPF
    assert 'Sem CPF' not in loc.falas[-1]  # o botão "Sem CPF" não existe pra quem só ouve


# --- roteiro -------------------------------------------------------------------------------

def test_roteiro_usa_a_fala_do_gemini_limpa():
    def llm(sistema, partes, esquema, modelos=None):
        assert 'fala' in esquema['properties'] and 'Coloquei' in partes[0][1]
        assert modelos == voz.MODELOS_ROTEIRO  # fila rápida, não a do interpretar
        return {'fala': 'Pronto, coloquei os *dois* leites! 😊 Me manda um áudio ou escreve.'}, 'fake', 0.1
    fala = voz.roteiro(llm, [{'tipo': 'texto', 'texto': '✅ Coloquei *2x Leite*', 'opcoes': []}])
    assert fala == 'Pronto, coloquei os dois leites! Me manda um áudio ou escreve.'


def test_frase_que_manda_tocar_botao_e_cortada():
    def llm(sistema, partes, esquema, modelos=None):
        return {'fala': 'Poxa, não achei esfiha de carne aqui perto. Tenta de outro jeito, tá bom? '
                        'É só tocar no botão Escrever de novo ou mandar um áudio.'}, 'fake', 0.1
    fala = voz.roteiro(llm, [{'tipo': 'botoes', 'texto': 'Não achei', 'opcoes': ['Escrever de novo']}])
    assert 'botão' not in fala and 'tocar' not in fala and fala.startswith('Poxa')
    assert fala.endswith(voz.CONVITE)  # o convite pra responder voltou no lugar


def test_fala_longa_corta_no_fim_da_frase():
    longa = ' '.join(['Essa é uma frase de teste bem comprida.'] * 40)
    fala = voz._caber(longa)
    assert len(fala) <= voz.MAX_FALA and fala.endswith('comprida.')


def test_roteiro_simples_fala_dinheiro_e_opcoes_como_gente():
    fala = voz.roteiro_simples([{'tipo': 'botoes', 'texto': '🧺 Seu pedido até agora: *R$ 12,90*\n\nQuer mais?',
                                 'opcoes': ['✅ Finalizar pedido', '➕ Quero mais coisas']}])
    assert '12 reais e 90. Quer mais?' in fala and 'R$' not in fala and fala.endswith(voz.CONVITE)
    assert 'Finalizar pedido ou Quero mais coisas?' in fala
