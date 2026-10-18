"""Endereço e complemento ditos como gente fala (áudio transcrito ou texto conversado).

17/10 22h21: "Pode mandar pra minha casa, que é na Rua Adolfo Catani, 676" virou o NOME da rua, e
"Eu moro no apartamento quatorze." virou o complemento, palavra por palavra.
"""
import pytest

from src.bot.interpretar import numero_falado, so_complemento, so_endereco
from tests.fakes import Mundo


@pytest.mark.parametrize('frase,endereco', [
    ('Pode mandar pra minha casa, que é na Rua Adolfo Catani, 676', 'Rua Adolfo Catani, 676'),
    ('Rua Adolfo Catani, 676', 'Rua Adolfo Catani, 676'),
    ('moro na Av. Trabalhador São-carlense, 400.', 'Av. Trabalhador São-carlense, 400'),
    ('entrega na avenida são carlos 2500', 'avenida são carlos 2500'),
    ('13560-000', '13560-000'),  # só CEP: segue como veio (o geocoder resolve)
])
def test_endereco_falado_vira_so_o_endereco(frase, endereco):
    assert so_endereco(frase) == endereco


@pytest.mark.parametrize('frase,complemento', [
    ('Eu moro no apartamento quatorze.', 'Apto 14'),
    ('apto 12', 'Apto 12'),
    ('bloco b, apartamento trinta e dois', 'Bloco B, Apto 32'),
    ('ap 12 bloco c', 'Apto 12, Bloco C'),
    ('apartamento 302, torre 2', 'Apto 302, Torre 2'),
    ('sala cento e quatro', 'Sala 104'),
    ('fica no segundo andar', '2º andar'),
    ('casa 2', 'Casa 2'),
    ('é o 14 B', '14 B'),
    ('perto da padaria', 'perto da padaria'),  # sem peça conhecida: vai como veio
])
def test_complemento_falado_vira_so_o_complemento(frase, complemento):
    assert so_complemento(frase) == complemento


def test_numero_por_extenso():
    assert [numero_falado(x) for x in ('quatorze', 'trinta e dois', 'cento e quatro', 'mil e vinte', 'pão')] == \
        [14, 32, 104, 1020, None]


def test_endereco_e_complemento_falados_no_fluxo():
    m = Mundo(transcritor=lambda mime, dados: m.proxima_fala)
    m.enviar('quero pao')
    m.proxima_fala = 'Pode mandar pra minha casa, que é na Rua das Flores, 120, São Carlos'
    m.enviar(('audio', 'a1'))
    geo = m.mcp.chamadas_de('createAddress')  # o passo 1 (geocode) também é createAddress
    assert not any('Pode mandar' in str(c) for c in geo)        # a frase não vai pro iFood
    assert m.estado()['fase'] == 'endereco_escolha'
    m.tocar('cand:0')
    m.proxima_fala = 'Eu moro no apartamento quatorze.'
    m.enviar(('audio', 'a2'))
    salvos = [c for c in m.mcp.chamadas_de('createAddress') if c.get('candidateId')]
    assert salvos[-1]['complement'] == 'Apto 14'


def test_foto_com_gemini_fora_nao_fala_de_audio():
    """17/10 23h: mandou foto, o Gemini estourou e o bot disse "não consegui ouvir seu áudio"."""
    from src.bot import textos as T
    m = Mundo()
    m.llm.falhar = True
    m.enviar(('foto', 'f1'))
    textos = ' '.join(m.wpp.textos())
    assert T.FOTO_RUIM in textos and 'ouvir' not in textos
