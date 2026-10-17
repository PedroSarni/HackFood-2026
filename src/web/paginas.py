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
/* login concluído no visual do app do iFood: fundo branco sempre, vermelho só na ação */
body.ifood { --fundo:#ffffff; --texto:#3e3e3e; --suave:#717171; --marca:#ea1d2c; --borda:#f2f2f2;
             background:#ffffff; color:#3e3e3e; }
body.ifood main { max-width: 440px; padding: 24px 20px 40px; }
.topo { display:flex; align-items:center; justify-content:center; gap:12px; padding:8px 0 20px;
        border-bottom:1px solid #f2f2f2; }
.topo svg { width:72px; height:auto; color:#ea1d2c; }
.topo .x { color:#a6a6a6; font-size:.9em; }
.topo img { width:36px; height:36px; border-radius:10px; }
.check { width:88px; height:88px; margin:36px auto 0; border-radius:50%; background:#ea1d2c;
         display:flex; align-items:center; justify-content:center; box-shadow:0 8px 24px rgba(234,29,44,.25); }
.check svg { width:44px; height:44px; }
body.ifood h1 { text-align:center; font-size:1.5em; font-weight:700; color:#3e3e3e; margin:24px 0 8px; }
body.ifood .sub { text-align:center; color:#717171; margin:0 0 24px; }
.cartao { background:#f7f7f7; border-radius:12px; padding:16px; display:flex; gap:12px; align-items:center; }
.cartao .bola { flex:none; width:40px; height:40px; border-radius:50%; background:#fff; display:flex;
                align-items:center; justify-content:center; }
.cartao .bola svg { width:28px; color:#ea1d2c; }
.cartao b { display:block; color:#3e3e3e; font-size:.95em; }
.cartao span { color:#717171; font-size:.85em; }
body.ifood a.botao { border-radius:8px; font-size:1.05em; font-weight:600; padding:16px; margin-top:24px;
                     box-shadow:0 4px 12px rgba(234,29,44,.2); }
body.ifood .rodape { text-align:center; color:#a6a6a6; font-size:.8em; margin-top:20px; }
"""


def _pagina(titulo, corpo, classe=''):
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title><style>{_ESTILO}</style></head>
<body class="{classe}"><main>{corpo}</main></body></html>"""


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


def login_demo(continuar_url, voltar_url, logo_url='/logo.png'):
    """Tela de login do MODO DEMONSTRAÇÃO. Parece um consentimento de OAuth (dá a impressão de
    conectar a conta), mas é a NOSSA página: não pede senha, não imita a tela do iFood e não
    manda nada pro iFood. O botão só segue o fluxo da demo."""
    return _pagina(f'Entrar · {NOME}', f"""
<div style="max-width:420px;margin:0 auto">
  <div style="text-align:center;margin-top:16px">
    <img src="{html.escape(logo_url)}" alt="" width="72" height="72"
         style="border-radius:18px;vertical-align:middle">
  </div>
  <p style="text-align:center;font-size:.8em;letter-spacing:.08em;text-transform:uppercase;color:var(--suave);
            margin:18px 0 0">Modo demonstração</p>
  <h1 style="text-align:center;font-size:1.35em;margin:6px 0 4px">Conectar sua conta iFood</h1>
  <p style="text-align:center;color:var(--suave);margin:0 0 20px">
     Para <b>{html.escape(NOME)}</b> montar e acompanhar seus pedidos.</p>

  <div style="border:1px solid var(--borda);border-radius:14px;padding:4px 18px">
    <p style="margin:14px 0;color:var(--suave)">🏠 &nbsp;Ver e salvar seus endereços de entrega</p>
    <p style="margin:14px 0;color:var(--suave);border-top:1px solid var(--borda);padding-top:14px">
       🛒 &nbsp;Montar o carrinho e fazer pedidos que você confirmar</p>
    <p style="margin:14px 0;color:var(--suave);border-top:1px solid var(--borda);padding-top:14px">
       🛵 &nbsp;Acompanhar a entrega</p>
  </div>

  <a class="botao" href="{html.escape(continuar_url)}">Permitir e entrar</a>
  <p style="text-align:center;margin:14px 0 0">
     <a href="{html.escape(voltar_url)}" style="color:var(--suave)">Agora não</a></p>

  <p style="text-align:center;font-size:.82em;color:var(--suave);margin-top:28px;line-height:1.5">
     ⚠️ Demonstração do hackathon. Esta tela é do nosso sistema, não do iFood.
     Não pedimos sua senha e nada é enviado ao iFood.</p>
</div>""")


def tela(icone, titulo, texto, botao=None, link=None):
    """Tela de uma mensagem só (login concluído, link vencido...)."""
    acao = (f'<a class="botao" href="{html.escape(link)}">{html.escape(botao)}</a>'
            if botao and link else '')
    return _pagina(titulo, f"""
<div class="icone">{icone}</div>
<p class="grande"><b>{html.escape(titulo)}</b></p>
<p style="text-align:center">{html.escape(texto)}</p>
{acao}""")


# logo oficial do iFood (Wikimedia Commons, IFood_logo.svg) com a cor herdada do CSS
LOGO_IFOOD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1004 530.58" role="img" aria-label="iFood">'
              '<g transform="translate(4 -224.71)" fill="currentColor">'
              '<path d="M-4,529.31H72.41l42.46-211.2H38.45ZM42.66,292.92h76.73L132,229.73H55.3Zm59.47,295.82h76.42l46.69'
              '-228.18h57.31L291,318.11H234.79l2.13-9.55c3.18-18,9.55-38.21,38.2-38.21,17,0,32.91,1.06,48.82,8.49l8.5-44'
              '.57a167.8,167.8,0,0,0-55.19-9.56c-61.56,0-104,36.09-119.93,93.4H130.79l-8.49,42.45h26.53Z"/>'
              '<path d="M344.11,533.56c90.21,0,152.83-81.73,152.83-148.59,0-49.88-45.64-71.11-90.21-71.11C308,313.86,253.9'
              ',402,253.9,462.45c0,49.88,46.7,71.11,90.21,71.11m242,0c90.21,0,152.83-81.73,152.83-148.59,0-49.88-46.7-71'
              '.11-91.28-71.11-98.7,0-152.82,88.09-152.82,148.59,0,49.88,47.76,71.11,91.27,71.11m277-4.25h75.35L1000,229'
              'H923.59l-18.05,89.15-31.84-3.18c-74.29,0-142.21,95.51-142.21,163.44,0,27.59,18,55.19,48.82,55.19,43.51,0'
              ',74.29-21.23,87-42.46h4.24ZM627.48,687.45a295,295,0,0,1-212.26,66.86c-100.83-6.37-173-83.85-185.73-165.57'
              'h4.24c23.35,51,79.6,98.71,148.59,106.13,70,8.49,153.89-23.34,199.52-66.86L530.9,588.74H684.79l-34,163.45'
              '-22.29-63.68Z"/></g></svg>')
_CHECK = ('<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" '
          'stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>')


def logou(texto, botao, link, logo_url='/logo.png'):
    """Tela de login concluído no visual do app do iFood. É a NOSSA página (domínio nosso, não
    pede nada): a logo do iFood aparece como a conta que foi conectada, ao lado da nossa."""
    return _pagina('Pronto, você entrou!', f"""
<div class="topo">{LOGO_IFOOD}<span class="x">+</span>
  <img src="{html.escape(logo_url)}" alt="{html.escape(NOME)}"></div>
<div class="check">{_CHECK}</div>
<h1>Pronto, você entrou!</h1>
<p class="sub">{html.escape(texto)}</p>
<div class="cartao"><div class="bola">{LOGO_IFOOD}</div>
  <div><b>Conta iFood conectada</b><span>{html.escape(NOME)} já pode montar seus pedidos.</span></div></div>
<a class="botao" href="{html.escape(link)}">{html.escape(botao)}</a>
<p class="rodape">Pra desconectar, é só escrever <b>sair</b> no WhatsApp.</p>""", classe='ifood')
