"""Confere os prompts da foto e do kit em grupo contra o Gemini DE VERDADE (os testes usam um fake).

Só chama o Gemini (secret `hackathon-gemini`): nenhuma chamada ao iFood, nada de produção.
    modal run scripts/validar_foto_grupo.py
No Windows: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 antes, senão o modal quebra imprimindo emoji.
"""
import json

import modal

app = modal.App('hackfood-validar-foto-grupo')
imagem = (modal.Image.debian_slim(python_version='3.12')
          .pip_install('httpx==0.28.1', 'pillow==11.3.0')
          .add_local_python_source('src'))

FRASES = [  # (frase, estado da conversa, ação esperada, pessoas esperadas)
    ('quero lanchar em 5 pessoas hamburguer', {}, 'grupo', 5),
    ('hoje vai ser pizza aqui em casa, somos em 4', {}, 'grupo', 4),
    ('eu e mais 3 vamos rachar uma pizza', {}, 'grupo', 4),
    ('pizza com 4 amigos', {}, 'grupo', 4),
    ('eu estou com 13 amigos e a gente quer churrasco', {}, 'grupo', 13),
    ('monta um kit pra galera, somos 6, esfiha e coca', {}, 'grupo', 6),
    ('vamos dividir em 3', {'fase': 'mais', 'carrinho': {'itens': [{'qtd': 2, 'nome': 'X-Burger'}]}}, 'grupo', 3),
    ('quero 2 pizzas de calabresa', {}, 'comprar', None),
    ('sem refri', {'fase': 'kit', 'kit': {'pessoas': 5, 'tema': {'termo': 'hambúrguer'},
                                          'linhas': [{'qtd': 5, 'nome': 'X-Burger'},
                                                     {'qtd': 2, 'nome': 'Coca-Cola 2 litros'}]}}, 'grupo', None),
    ('agora somos 6', {'fase': 'kit', 'kit': {'pessoas': 5, 'tema': {'termo': 'hambúrguer'},
                                              'linhas': [{'qtd': 5, 'nome': 'X-Burger'}]}}, 'grupo', 6),
    ('pode ser, fechou', {'fase': 'kit', 'kit': {'pessoas': 5, 'tema': {'termo': 'hambúrguer'},
                                                 'linhas': [{'qtd': 5, 'nome': 'X-Burger'}]}}, 'sim', None),
]
CANDIDATOS = [  # como o grupo.candidatos monta, com preços do mock
    {'nome': 'X-Burger', 'unit': 22.90, 'papel': 'principal', 'termo': 'hambúrguer'},
    {'nome': 'X-Salada', 'unit': 24.90, 'papel': 'principal', 'termo': 'hambúrguer'},
    {'nome': 'X-Bacon', 'unit': 25.90, 'papel': 'principal', 'termo': 'hambúrguer'},
    {'nome': 'Refrigerante lata 350 ml', 'unit': 6.50, 'papel': 'bebida', 'termo': 'refrigerante'},
    {'nome': 'Coca-Cola 2 litros', 'unit': 12.90, 'papel': 'bebida', 'termo': 'refrigerante'},
    {'nome': 'Batata frita (porção)', 'unit': 14.90, 'papel': 'acompanhamento', 'termo': 'batata frita'},
    {'nome': 'Suco natural de laranja', 'unit': 9.90, 'papel': 'bebida', 'termo': 'suco'},
]
FOTO_COMIDA = 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=640&q=70'


def _lista_escrita():
    """Uma 'lista de compras' desenhada (sem foto de verdade à mão, serve pra ver se ele lê tudo)."""
    import io

    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (700, 520), (250, 246, 228))
    d = ImageDraw.Draw(img)
    fonte = ImageFont.load_default(size=44)
    for i, linha in enumerate(['Lista mercado', '- 2 leite', '- arroz 5kg', '- feijao', '- 1 duzia ovos', '- cafe']):
        d.text((40, 30 + i * 78), linha, fill=(30, 30, 120), font=fonte)
    b = io.BytesIO()
    img.save(b, 'JPEG')
    return b.getvalue()


@app.function(image=imagem, secrets=[modal.Secret.from_name('hackathon-gemini')], timeout=300)
def validar():
    import httpx

    from src.bot import foto, grupo
    from src.bot.interpretar import interpretar
    from src.shared.llm import gerar_json
    ok = True
    print('== intenção (interpretar) ==')
    for frase, estado, acao, pessoas in FRASES:
        it = interpretar(gerar_json, estado, [('texto', frase)])
        certo = it['acao'] == acao and (pessoas is None or it.get('numero') == pessoas)
        if acao == 'grupo' and estado.get('fase') != 'kit' and not estado.get('carrinho'):
            certo &= bool(it.get('itens'))  # a comida em itens (o fluxo ainda tem a regra se vier vazio)
        ok &= certo
        print(('OK ' if certo else 'ERRO'), repr(frase), '->', it['acao'], it.get('numero'),
              [i['termo'] for i in it.get('itens') or []], it.get('texto'))
    print('== kit (compor) ==')
    for pessoas, ajuste in ((5, None), (5, 'sem refri'), (2, None), (12, 'mais barato')):
        escolha, fala, _falta = grupo.compor(gerar_json, pessoas, {'termo': 'hambúrguer'}, CANDIDATOS, ajuste)
        print(pessoas, ajuste, '->', [(CANDIDATOS[n]['nome'], q) for n, q in escolha], '|', fala)
        principais = sum(q for n, q in escolha if CANDIDATOS[n]['papel'] == 'principal')
        ok &= principais >= pessoas * 0.8 and fala is not None
        if ajuste == 'sem refri':
            ok &= not any(CANDIDATOS[n]['papel'] == 'bebida' and 'Refri' in CANDIDATOS[n]['nome'] for n, _ in escolha)
    print('== foto ==')
    lida = foto.ler(gerar_json, {}, [('image/jpeg', _lista_escrita())])
    print('lista:', json.dumps(lida, ensure_ascii=False))
    ok &= lida['tipo'] == 'lista' and len(lida['itens']) >= 4
    r = httpx.get(FOTO_COMIDA, headers={'User-Agent': 'HackFood-validacao/1.0'}, follow_redirects=True, timeout=30)
    if r.status_code == 200:
        lida = foto.ler(gerar_json, {}, [('image/jpeg', r.content)])
        print('comida:', json.dumps(lida, ensure_ascii=False))
        ok &= lida['tipo'] == 'comida' and bool(lida['parecidos'])
        lida = foto.ler(gerar_json, {}, [('image/jpeg', r.content)], ['quero 2 desse pra mim e mais 3 amigos'])
        print('comida + legenda:', json.dumps(lida, ensure_ascii=False))
        ok &= (lida['pessoas'] or grupo.pessoas_em('quero 2 desse pra mim e mais 3 amigos')) == 4  # como o fluxo faz  # "quero 2 desse" o fluxo pega pela regra (QUER_ISSO), mesmo com ja_pediu falso
    else:
        print('foto de comida não baixou:', r.status_code)
    print('TUDO CERTO' if ok else 'TEM ERRO (ver acima)')
    return ok


@app.local_entrypoint()
def main():
    validar.remote()
