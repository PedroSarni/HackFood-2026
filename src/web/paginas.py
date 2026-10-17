"""Páginas públicas: termos, privacidade, exclusão de dados e as telas do login.

Termos e privacidade são exigidos pelo cadastro do agente no portal do iFood e pela Meta.
As telas do login são vistas no celular por quem acabou de sair do WhatsApp, então: letra
grande, uma frase, um botão.
"""
import html

NOME = 'Compras pelo WhatsApp'
ATUALIZADO = '17 de outubro de 2026'

_ESTILO = """
:root { --fundo:#ffffff; --texto:#1d1d1f; --suave:#5f6368; --marca:#1f8f4e; --borda:#e3e3e3; }
@media (prefers-color-scheme: dark) {
  :root { --fundo:#121212; --texto:#f1f1f1; --suave:#b0b0b0; --marca:#3ccf7a; --borda:#2c2c2c; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--fundo); color:var(--texto);
       font: 18px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 720px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.6em; line-height: 1.25; margin: 0 0 8px; }
h2 { font-size: 1.15em; margin: 28px 0 6px; }
p, li { color: var(--texto); }
.suave { color: var(--suave); font-size: .9em; }
.grande { font-size: 1.35em; text-align: center; margin-top: 40px; }
.icone { font-size: 72px; text-align: center; margin-top: 24px; }
a.botao { display:block; text-align:center; background:var(--marca); color:#fff; text-decoration:none;
          font-size:1.2em; font-weight:600; padding:18px; border-radius:14px; margin:28px 0 0; }
footer { margin-top: 40px; border-top: 1px solid var(--borda); padding-top: 12px; }
footer a { color: var(--marca); }
"""


def _pagina(titulo, corpo):
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title><style>{_ESTILO}</style></head>
<body><main>{corpo}</main></body></html>"""


def _rodape():
    return ('<footer class="suave">Atualizado em ' + ATUALIZADO + '. Veja também: '
            '<a href="/termos">Termos de Uso</a> · <a href="/privacidade">Privacidade</a> · '
            '<a href="/exclusao">Apagar meus dados</a></footer>')


def termos():
    return _pagina(f'Termos de Uso · {NOME}', f"""
<h1>Termos de Uso</h1>
<p class="suave">{NOME}, assistente de pedidos pela conversa do WhatsApp.</p>

<h2>1. O que é</h2>
<p>Um assistente que ajuda você a fazer pedidos de mercado, restaurante, farmácia e outras
lojas conversando no WhatsApp, com botões simples. Os pedidos são feitos na <b>sua</b> conta
iFood, só depois que você entra nela e autoriza o acesso.</p>

<h2>2. Nada é comprado sem você confirmar</h2>
<p>Antes de qualquer compra, mostramos o resumo (itens, preços, entrega, endereço e forma de
pagamento). O pedido só é enviado quando você toca em <b>Confirmar pedido</b>. Lembretes de
compra repetida também só viram pedido depois da sua confirmação.</p>

<h2>3. Preços, entrega e pagamento</h2>
<p>Preços, disponibilidade, prazos, entrega e cobrança são de responsabilidade da loja e da
plataforma onde o pedido é feito. Cancelamentos e reembolsos são tratados pelo aplicativo do
iFood; este assistente não cancela nem reembolsa pedidos.</p>

<h2>4. Uso correto</h2>
<p>O assistente serve para pedidos. Não envie dados de cartão, senhas ou documentos de outras
pessoas pela conversa. Mensagens abusivas ou automatizadas podem ser bloqueadas.</p>

<h2>5. Como sair</h2>
<p>Escreva <b>sair</b> para desconectar sua conta iFood a qualquer momento, ou
<b>apagar meus dados</b> para apagar tudo o que guardamos sobre você. Você também pode
desconectar pelo app do iFood, em <i>Contas Conectadas</i>.</p>

<h2>6. Fase de testes</h2>
<p>Este serviço está em fase de testes e pode ficar fora do ar ou mudar sem aviso.</p>

<h2>7. Contato</h2>
<p>Fale com a gente pela própria conversa do WhatsApp.</p>
{_rodape()}""")


def privacidade():
    return _pagina(f'Política de Privacidade · {NOME}', f"""
<h1>Política de Privacidade</h1>
<p class="suave">Como o {NOME} trata seus dados, em linguagem simples (LGPD, Lei 13.709/2018).</p>

<h2>Quais dados usamos</h2>
<ul>
<li><b>Do WhatsApp:</b> seu número, o nome do seu perfil e as mensagens que você manda pra
nós (texto, áudio e foto).</li>
<li><b>Da sua conta iFood, com a sua autorização:</b> nome, endereços de entrega, formas de
pagamento disponíveis, carrinho e pedidos feitos por aqui.</li>
</ul>

<h2>Para que usamos</h2>
<p>Só para entender o que você quer comprar, montar o pedido, mostrar o resumo, enviar o pedido
quando você confirmar e avisar como está a entrega. Não vendemos, não emprestamos e não usamos
seus dados para propaganda.</p>

<h2>Inteligência artificial</h2>
<p>Suas mensagens são lidas por um modelo de inteligência artificial (Google Gemini) apenas
para entender o pedido. Documentos como CPF não passam pela inteligência artificial.</p>

<h2>Por quanto tempo guardamos</h2>
<ul>
<li>A conversa e o carrinho em andamento: até 30 dias sem uso.</li>
<li>O acesso à sua conta iFood: até você escrever <b>sair</b> ou desconectar pelo app do iFood.</li>
<li>Lembretes de compra repetida: até você pedir para parar.</li>
</ul>

<h2>Seus direitos</h2>
<p>Você pode pedir para ver, corrigir ou apagar seus dados. Para apagar tudo, escreva
<b>apagar meus dados</b> na conversa. Veja também a página <a href="/exclusao">Apagar meus dados</a>.</p>

<h2>Segurança</h2>
<p>Os dados ficam em servidores com acesso restrito e as conexões são criptografadas (HTTPS).
Nunca pedimos senha nem número de cartão pela conversa.</p>
{_rodape()}""")


def exclusao():
    return _pagina(f'Apagar meus dados · {NOME}', f"""
<h1>Como apagar seus dados</h1>
<ol>
<li>Abra a conversa com o {NOME} no WhatsApp.</li>
<li>Escreva: <b>apagar meus dados</b>.</li>
<li>Toque em <b>Sim, apagar</b>. Pronto: desconectamos sua conta iFood e apagamos sua conversa,
endereços guardados e lembretes. Você recebe a confirmação na hora.</li>
</ol>
<p>Depois disso, seu número volta a ser tratado como novo.</p>
{_rodape()}""")


def tela(icone, titulo, texto, botao=None, link=None):
    """Tela de uma mensagem só (login concluído, link vencido...)."""
    acao = (f'<a class="botao" href="{html.escape(link)}">{html.escape(botao)}</a>'
            if botao and link else '')
    return _pagina(titulo, f"""
<div class="icone">{icone}</div>
<p class="grande"><b>{html.escape(titulo)}</b></p>
<p style="text-align:center">{html.escape(texto)}</p>
{acao}""")
