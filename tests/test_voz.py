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

def test_sem_pedido_nunca_manda_audio():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('quero leite')
    assert 'audio' not in tipos(m) and not loc.falas
    assert not m.estado().get('voz')


def test_pedido_de_audio_responde_em_audio_e_mantem_os_botoes():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio')
    assert m.estado()['voz']
    assert tipos(m)[-1] == 'audio' and m.wpp.saida[-1][1]['voz'] is True  # nota de voz, por último
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir', 'repetir', 'meu_pedido']  # menu ainda tocável
    assert T.VOZ_LIGADA not in escritos(m)  # o "pode deixar" foi falado, não escrito
    assert len(loc.falas) == 1 and 'áudio ou escrevendo' in loc.falas[0]
    assert m.wpp.midias and b'audio/ogg' in m.wpp.midias[0]  # subiu o ogg pra Meta


def test_no_modo_audio_texto_solto_vira_fala_e_cards_continuam():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('me responde por áudio')
    m.wpp.limpar()
    m.enviar('quero leite')
    assert 'carrossel' in tipos(m) and tipos(m)[-1] == 'audio'
    assert not escritos(m)  # "Entregando em..." foi pro áudio
    fala = loc.falas[-1]
    assert 'Entregando em' in fala and 'opções com foto' in fala
    assert '*' not in fala and '👇' not in fala and '🏠' not in fala  # nada que a voz leria errado


def test_pedido_de_audio_junto_com_o_pedido_de_compra():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.wpp.limpar()
    m.enviar('quero leite e me responde por áudio')
    assert m.estado()['voz']
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'leite'  # o resto seguiu o fluxo
    assert 'carrossel' in tipos(m) and tipos(m)[-1] == 'audio'


def test_pedido_falado_tambem_liga():
    m = Mundo(locutor=Locutor(), transcritor=lambda mime, dados: 'me responde por áudio, por favor')
    m.enviar(('audio', 'midia1'))
    assert m.estado()['voz'] and tipos(m)[-1] == 'audio'


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


# --- plano B --------------------------------------------------------------------------------

def test_voz_fora_do_ar_manda_tudo_escrito():
    m, loc = mundo_com_voz(falhar=True)
    endereco_pronto(m)
    m.enviar('me responde por áudio')
    m.wpp.limpar()
    m.enviar('quero leite')
    assert 'audio' not in tipos(m)
    assert any('Entregando em' in t for t in escritos(m))  # o que ia virar fala saiu escrito


def test_primeiro_audio_falhou_nao_promete_audio():
    m, loc = mundo_com_voz(falhar=True)  # key sem permissão de text_to_speech, por exemplo
    m.enviar('me responde por áudio')
    assert T.VOZ_INDISPONIVEL in escritos(m) and T.VOZ_LIGADA not in escritos(m)
    assert not m.estado().get('voz')  # não fica tentando (e falhando) a cada mensagem


def test_falha_depois_de_ja_ter_falado_mantem_o_modo():
    m, loc = mundo_com_voz()
    endereco_pronto(m)
    m.enviar('me responde por áudio')
    loc.falhar = True  # soluço da ElevenLabs no meio da conversa
    m.enviar('quero leite')
    assert m.estado()['voz']  # a próxima tenta em áudio de novo


def test_sem_elevenlabs_avisa_e_nao_liga():
    m = Mundo()  # sem locutor
    m.enviar('me responde por áudio')
    assert not m.estado().get('voz')
    assert T.VOZ_INDISPONIVEL in escritos(m) and 'audio' not in tipos(m)


def test_sem_gemini_o_roteiro_simples_ainda_fala():
    m, loc = mundo_com_voz()
    m.llm.falhar = True
    m.enviar('me responde por áudio')
    assert tipos(m)[-1] == 'audio' and loc.falas[-1].endswith(voz.CONVITE)


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


def test_pedido_feito_fecha_em_audio_com_o_numero_escrito_e_a_sessao_seguinte_e_texto():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio')
    pedido_ate_o_resumo(m)
    assert m.estado()['voz']
    ok = next(i for i in reversed(m.wpp.todos_ids()) if i.startswith('ok:'))
    m.wpp.limpar()
    m.enviar(('botao', ok))
    assert any('Pedido feito' in t for t in escritos(m))  # número e código ficam escritos
    assert tipos(m)[-1] == 'audio'                          # e a despedida vai falada
    assert not m.estado().get('voz')                        # acabou a sessão, acabou o áudio
    m.wpp.limpar()
    m.enviar('oi')
    assert 'audio' not in tipos(m)


def test_no_cpf_o_audio_pede_pra_escrever():
    m, loc = mundo_com_voz()
    m.llm.falhar = True  # roteiro simples: o convite é nosso, dá pra conferir
    m.enviar('me responde por áudio')
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:3')
    m.tocar('fim')
    m.tocar('pag:0')
    assert m.estado()['fase'] == 'cpf'
    assert loc.falas[-1].endswith(voz.CONVITE_CPF) and 'áudio' not in loc.falas[-1]


def test_ligar_com_conversa_junto_nao_vira_nao_entendi():
    m, loc = mundo_com_voz()
    m.enviar('me responde por áudio, não enxergo bem')  # o fake diz nao_entendi pro resto
    assert m.estado()['voz']
    assert T.NAO_ENTENDI not in ' '.join(loc.falas) and 'Desculpe' not in loc.falas[-1]
    assert [i for i, _ in m.wpp.ultimos_botoes()] == ['pedir', 'repetir', 'meu_pedido']


def test_codigo_do_pedido_nem_chega_no_gemini():
    vistos = []
    def llm(sistema, partes, esquema, modelos=None):
        vistos.append(partes[0][1])
        return {'fala': 'Prontinho, pedido feito! O número tá escrito aí na mensagem.'}, 'fake', 0.1
    voz.roteiro(llm, [{'tipo': 'texto', 'texto': '🎉 *Pedido feito!*\nNúmero do pedido: *D1003*\n'
                       '🔑 Código de entrega: *4821* (fale pro entregador)', 'opcoes': [], 'fica': True}])
    assert 'D1003' not in vistos[0] and '4821' not in vistos[0] and 'fica escrito' in vistos[0]


# --- roteiro -------------------------------------------------------------------------------

def test_roteiro_usa_a_fala_do_gemini_limpa():
    def llm(sistema, partes, esquema, modelos=None):
        assert 'fala' in esquema['properties'] and 'Coloquei' in partes[0][1]
        assert modelos == voz.MODELOS_ROTEIRO  # fila rápida, não a do interpretar
        return {'fala': 'Pronto, coloquei os *dois* leites! 😊 Me manda um áudio ou escreve.'}, 'fake', 0.1
    fala = voz.roteiro(llm, [{'tipo': 'texto', 'texto': '✅ Coloquei *2x Leite*', 'opcoes': [], 'fica': False}])
    assert fala == 'Pronto, coloquei os dois leites! Me manda um áudio ou escreve.'


def test_roteiro_simples_fala_dinheiro_como_gente():
    fala = voz.roteiro_simples([{'tipo': 'botoes', 'texto': '🧺 Seu pedido até agora: *R$ 12,90*',
                                 'opcoes': ['✅ Finalizar pedido'], 'fica': False}])
    assert '12 reais e 90' in fala and 'R$' not in fala and fala.endswith(voz.CONVITE)
