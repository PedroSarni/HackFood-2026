"""Quando algo dá errado, o Gemini explica como gente, olhando o que a pessoa disse.

"Ops, deu um probleminha" deixa quem tem pouca prática com celular sem saber o que fazer.
Aqui a mensagem responde ao que a pessoa falou, diz em palavras simples o que houve e qual
o próximo passo. Se o Gemini falhar, devolve None e o fluxo usa o texto fixo de sempre.
"""

SITUACOES = {
    'ifood_fora': 'O servidor do iFood está instável ou fora do ar agora. Não é culpa da pessoa nem do '
                  'pedido dela; costuma voltar em alguns minutos. Ela pode tocar em "Tentar de novo" daqui '
                  'a pouco ou voltar ao início.',
    'erro_nosso': 'Deu um erro inesperado do nosso lado (do assistente), não do iFood nem da pessoa. '
                  'Ela pode tocar em "Tentar de novo" ou voltar ao início.',
}

SISTEMA = """\
Você é o atendente de um assistente de compras do iFood pelo WhatsApp. Quem conversa são, em \
geral, pessoas idosas ou com pouca prática com celular. Algo não saiu como esperado e você vai \
escrever UMA mensagem curta (no máximo 3 frases, até 300 caracteres) que:
- responde primeiro ao que a pessoa disse, como uma pessoa de verdade responderia \
("oi, vc tá aí?" -> "Tô aqui sim! 😊 ...");
- explica o que aconteceu em palavras simples, sem termos técnicos, sem códigos de erro;
- diz exatamente o que ela pode fazer agora (os botões que vão aparecer embaixo);
- tem 1 ou 2 emojis, tom calmo e acolhedor, português do Brasil informal.
Nunca prometa prazos exatos, nunca invente que o pedido foi feito, nunca peça senha ou cartão.
Responda só o JSON do esquema."""

ESQUEMA = {'type': 'OBJECT', 'properties': {'texto': {'type': 'STRING'}}, 'required': ['texto']}


def falar(llm, situacao, disse='', etapa='', pergunta=''):
    """Mensagem de tutor pra situação, ou None se o Gemini não ajudar."""
    contexto = [f'Situação: {SITUACOES.get(situacao, situacao)}',
                f'Etapa da conversa: {etapa or "inicio"}.']
    if pergunta:
        contexto.append(f'Última pergunta que o assistente fez: {pergunta[:200]}')
    contexto.append(f'O que a pessoa acabou de mandar: {disse[:300] if disse else "(tocou num botão)"}')
    try:
        dados, _modelo, _seg = llm(SISTEMA, [('texto', '\n'.join(contexto))], ESQUEMA)
    except Exception as e:  # noqa: BLE001 - tutor é bônus: sem ele vai o texto fixo
        print(f'tutor falhou: {e!r}')
        return None
    texto = ' '.join(str((dados or {}).get('texto') or '').split()) if isinstance(dados, dict) else ''
    return texto[:400] or None
