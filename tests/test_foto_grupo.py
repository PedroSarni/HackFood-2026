"""Foto vira pedido e o kit pra dividir com os amigos, do jeito que a pessoa usaria."""
import math
import re

from src.bot import grupo
from src.bot import textos as T
from src.shared.whatsapp import tamanho
from tests.fakes import Mundo
from tests.test_fluxo import endereco_pronto


def ids(m):
    return m.wpp.todos_ids()


def textos(m):
    return ' '.join(m.wpp.textos())


def pronto(m):
    """Endereço cadastrado e a tela limpa."""
    endereco_pronto(m)
    m.wpp.limpar()
    return m


def reais(texto):
    """'R$ 1.234,56' -> 1234.56"""
    return float(texto.replace('R$', '').replace('.', '').replace(',', '.').strip())


# --- foto: comida ------------------------------------------------------------------------

def test_foto_de_comida_pergunta_se_quer_algo_parecido():
    m = pronto(Mundo())
    m.enviar(('foto', 'foto1'))
    assert 'Quer que eu procure algo parecido' in textos(m) and '[fala] Que delícia' in textos(m)
    assert {i.rsplit(':', 1)[0] for i in ids(m)} >= {'foto:sim', 'foto:nao'}
    assert m.estado()['fase'] == 'foto'
    assert not m.mcp.chamadas_de('searchOffers')[1:]  # só a busca do pão do endereco_pronto: perguntou antes


def test_sim_na_foto_mostra_os_parecidos_num_carrossel_so():
    m = pronto(Mundo())
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar(('foto', 'foto1'))
    m.tocar('foto:sim')
    buscas = m.mcp.chamadas_de('searchOffers')[antes:]
    assert [b['query'] for b in buscas][:1] == ['x-bacon'] and len(buscas) <= 3
    nomes = ' '.join(c['texto'] for c in m.wpp.cards())
    assert 'X-Bacon' in nomes and [t for t, _ in m.wpp.saida].count('carrossel') == 1
    assert 'parecidas com *hambúrguer com bacon*' in textos(m)
    m.tocar('pick:')  # o card escolhido segue o caminho normal (quantidade, carrinho)
    assert m.estado()['fase'] == 'quantidade'


def test_sim_escrito_na_foto_tambem_busca():
    m = pronto(Mundo())
    m.enviar(('foto', 'foto1'))
    m.enviar('sim')
    assert m.wpp.cards()


def test_nao_na_foto_volta_pro_menu_sem_buscar():
    m = pronto(Mundo())
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar(('foto', 'foto1'))
    m.tocar('foto:nao')
    assert len(m.mcp.chamadas_de('searchOffers')) == antes
    assert m.estado()['fase'] == 'pedido' and 'pedir' in ids(m)


def test_foto_com_legenda_quero_isso_busca_direto():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'comida', 'descricao': 'pizza de calabresa', 'ja_pediu': True, 'quantidade': 2,
                  'parecidos': [{'termo': 'pizza de calabresa', 'busca': 'pizza calabresa', 'tipo_loja': 'RESTAURANTE'}]}
    m.enviar(('foto', 'foto1', 'quero 2 dessa'))
    assert not any(i.startswith('foto:') for i in ids(m)) and m.wpp.cards()
    assert 'quero 2 dessa' in m.llm.prompts[-2][1] or any('quero 2 dessa' in t for _, t in m.llm.prompts)
    m.tocar('pick:')  # pizza: pergunta o tamanho, e a quantidade (2) já veio da legenda
    m.tocar('opt:0')
    assert 'Coloquei *2x' in textos(m)


def test_foto_de_comida_como_1a_mensagem_sem_login_pergunta_e_retoma_depois_de_entrar():
    m = Mundo(logado=False)
    m.enviar(('foto', 'foto1'))
    assert any(i.startswith('foto:sim:') for i in ids(m))  # entende a foto antes de pedir login
    m.tocar('foto:sim')
    assert m.wpp.saida[-1][0] == 'link'  # agora sim, entrar no iFood
    m.wpp.limpar()
    m.logar()
    assert 'Pra onde eu mando' in textos(m)
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.tocar('compl_nao')
    assert m.wpp.cards() and m.mcp.chamadas_de('searchOffers')[0]['query'] == 'x-bacon'


def test_foto_de_pizza_pra_5_pessoas_ja_vira_kit():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'comida', 'descricao': 'pizza', 'pessoas': 5,
                  'parecidos': [{'termo': 'pizza', 'busca': 'pizza', 'tipo_loja': 'RESTAURANTE'}]}
    m.enviar(('foto', 'foto1', 'uma dessa pra 5'))
    assert 'Kit pra 5 pessoas' in textos(m) and m.estado()['fase'] == 'kit'


# --- foto: lista, produto, outra coisa ---------------------------------------------------

LISTA = {'tipo': 'lista', 'descricao': 'lista de mercado', 'itens': [
    {'termo': 'pão francês', 'busca': 'pão francês', 'tipo_loja': 'MERCADO', 'quantidade': None},
    {'termo': 'leite', 'busca': 'leite', 'tipo_loja': 'MERCADO', 'quantidade': 2}]}


def test_foto_de_lista_de_compras_vira_a_lista_do_pedido():
    m = pronto(Mundo())
    m.llm.foto = LISTA
    m.enviar(('foto', 'lista1'))
    assert 'Anotei sua lista' in textos(m) and 'pão francês' in textos(m)
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'pão francês'
    assert [i['termo'] for i in m.estado()['fila']] == ['leite']


def test_foto_de_produto_vira_pedido_dele():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'produto', 'descricao': 'caixa de dipirona', 'itens': [
        {'termo': 'dipirona 500 mg', 'busca': 'dipirona', 'tipo_loja': 'FARMACIA'}]}
    m.enviar(('foto', 'caixa1'))
    assert 'Li sua foto' in textos(m) and 'dipirona' in textos(m)
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'dipirona' and m.wpp.cards()


def test_foto_de_lista_sem_login_anota_e_retoma_depois_de_entrar():
    m = Mundo(logado=False)
    m.llm.foto = LISTA
    m.enviar(('foto', 'lista1'))
    assert 'Li sua foto' in textos(m) and m.wpp.saida[-1][0] == 'link'
    assert m.estado()['pendente']['itens'][0]['termo'] == 'pão francês'


def test_lista_ilegivel_pede_outra_foto_ou_escrever():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'lista', 'descricao': 'papel borrado', 'itens': []}
    m.enviar(('foto', 'lista1'))
    assert 'não consegui ler' in textos(m)
    assert m.estado()['fase'] == 'escolhendo' and 'Quero esse' in textos(m)  # volta pros cards que estavam na tela


def test_foto_de_outra_coisa_comenta_e_pede_o_pedido():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'outro', 'descricao': 'documento', 'resposta': '[fala] Recebi sua foto! 🙂'}
    m.enviar(('foto', 'doc1'))
    assert '[fala] Recebi sua foto' in textos(m) and 'lista de compras' in textos(m)
    assert m.estado()['fase'] == 'pedido'  # sem relação com os cards: volta pro menu (U8)


def test_foto_de_outra_coisa_no_comeco_vai_pro_menu():
    m = Mundo()
    m.llm.foto = {'tipo': 'outro', 'descricao': 'paisagem', 'resposta': '[fala] Que vista linda! 😍'}
    m.enviar(('foto', 'praia1'))
    assert '[fala] Que vista linda' in textos(m) and m.estado()['fase'] == 'pedido' and 'pedir' in ids(m)


def test_foto_no_meio_do_endereco_espera_o_endereco_e_nao_vai_pro_geocoder():
    m = Mundo()
    m.enviar('quero pao')  # pediu o endereço
    m.llm.foto = LISTA
    criar = len(m.mcp.chamadas_de('createAddress'))
    m.enviar(('foto', 'lista1'))
    assert len(m.mcp.chamadas_de('createAddress')) == criar
    assert 'Li sua foto' in textos(m) and 'Pra onde eu mando' in textos(m)
    assert m.estado()['pendente']['itens'][1]['termo'] == 'leite'
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.tocar('compl_nao')
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'pão francês'  # a lista da foto, não o pão escrito


def test_foto_na_etapa_do_cpf_nem_abre_nem_vai_pra_ia():
    m = Mundo()
    m.armazem[f'u:{m.wa}'] = {**(m.armazem.get(f'u:{m.wa}') or {}), 'fase': 'cpf'}
    antes = m.llm.chamadas
    m.enviar(('foto', 'rg1'))
    # nem abre, nem vai pra IA, e vale como "sem CPF" (17/10, pedido do Fabio)
    assert m.llm.chamadas == antes and m.estado().get('cpf') == ''


def test_cpf_digitado_junto_com_a_foto_vale_e_a_foto_e_ignorada():
    m = Mundo()
    m.armazem[f'u:{m.wa}'] = {**(m.armazem.get(f'u:{m.wa}') or {}), 'fase': 'cpf'}
    antes = m.llm.chamadas
    m.enviar(('foto', 'rg1'), '529.982.247-25')
    assert m.llm.chamadas == antes and m.estado()['cpf'] == '52998224725'


def test_gemini_fora_explica_que_nao_viu_a_foto():
    m = pronto(Mundo())
    m.llm.falhar = True
    m.enviar(('foto', 'foto1'))
    assert 'Não consegui ver sua foto' in textos(m)


def test_foto_mandada_como_documento_tambem_e_pedido():
    m = pronto(Mundo())
    m.enviar(('documento', 'foto1', 'image/jpeg'))
    assert any(i.startswith('foto:sim:') for i in ids(m))


def test_varias_fotos_na_rajada_viram_uma_leitura_so():
    m = pronto(Mundo())
    m.llm.foto = LISTA
    antes = m.llm.chamadas
    m.enviar(('foto', 'pag1'), ('foto', 'pag2'), 'essa é minha lista')
    sistema, texto = m.llm.prompts[antes]
    assert 'fotos' in sistema and 'essa é minha lista' in texto
    assert 'Anotei sua lista' in textos(m)


# --- dividir com os amigos: o kit --------------------------------------------------------

def kit_na_tela(m):
    return m.estado()['kit']


def test_lanchar_em_5_pessoas_hamburguer_monta_kit_com_refri_e_divide():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    k = kit_na_tela(m)
    assert m.estado()['fase'] == 'kit' and k['pessoas'] == 5
    principais = sum(lin['qtd'] for lin in k['linhas'] if lin['papel'] == 'principal')
    assert principais == 5
    assert any('2 litros' in lin['nome'] for lin in k['linhas'])  # refri de 2 litros pra galera
    assert len({lin['item_id'] for lin in k['linhas']}) == len(k['linhas'])
    # a conta é do código: soma das linhas + entrega, e o por pessoa arredondado pra cima
    assert k['total'] == round(sum(lin['unit'] * lin['qtd'] for lin in k['linhas']) + k['taxa'], 2)
    assert k['por_pessoa'] * 5 >= k['total'] > (k['por_pessoa'] - 0.01) * 5
    tela = m.wpp.saida[-1][1]['texto']
    assert 'Kit pra 5 pessoas' in tela and 'por pessoa' in tela and T.reais(k['por_pessoa']) in tela
    assert {i.rsplit(':', 1)[0] for i in ids(m)} >= {'kit:ok', 'kit:outra', 'kit:nao'}
    assert not m.wpp.recusadas  # a Meta aceitaria a mensagem (texto do kit cabe em 1024)
    lojas = {o for o in [m.mcp.chamadas_de('searchOffers')[-1]['refinements'].get('merchantId')]}
    assert lojas == {k['loja_id']}  # complementos buscados na MESMA loja


def test_quero_esse_kit_vira_carrinho_e_o_resumo_mostra_quanto_fica_pra_cada():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    k = kit_na_tela(m)
    m.tocar('kit:ok')
    criar = m.mcp.chamadas_de('createCart')[-1]
    assert criar['merchantId'] == k['loja_id']
    assert sorted((i['itemId'], i['quantity']) for i in criar['items']) == sorted(
        (lin['item_id'], lin['qtd']) for lin in k['linhas'])
    assert 'Coloquei o kit' in textos(m) and 'por pessoa* (5 pessoas)' in textos(m)
    m.tocar('fim')
    m.tocar('pag:0')
    m.enviar('529.982.247-25')
    resumo = m.wpp.saida[-1][1]['texto']
    total = reais(re.search(r'\*Total: (R\$ [\d.,]+)\*', resumo).group(1))
    assert f'*{T.reais(math.ceil(round(total * 100) / 5) / 100)} por pessoa* (5 pessoas)' in resumo
    m.tocar('ok:')
    assert 'pra cada um (5 pessoas)' in textos(m)
    assert m.estado()['grupo'] is None


def test_outra_loja_troca_de_loja_sem_buscar_o_principal_de_novo():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    primeira = kit_na_tela(m)['loja']
    sem_loja = len([b for b in m.mcp.chamadas_de('searchOffers') if 'merchantId' not in b['refinements']])
    m.tocar('kit:outra')
    k = kit_na_tela(m)
    assert k['loja'] != primeira and {primeira, k['loja']} == {'Lanchonete do Bairro', 'Burger House'}
    assert len([b for b in m.mcp.chamadas_de('searchOffers') if 'merchantId' not in b['refinements']]) == sem_loja
    assert not any(i.startswith('kit:outra') for i, _ in m.wpp.ultimos_botoes())  # acabaram as lojas
    m.tocar('kit:ok')
    assert m.mcp.chamadas_de('createCart')[-1]['merchantId'] == k['loja_id']


def test_sem_refri_remonta_o_kit_na_mesma_loja():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    loja = kit_na_tela(m)['loja_id']
    m.enviar('sem refri')
    k = kit_na_tela(m)
    assert k['loja_id'] == loja and k['ajuste'] == 'sem refri'
    assert not any(lin['papel'] == 'bebida' for lin in k['linhas'])
    assert m.estado()['fase'] == 'kit'


def test_agora_somos_6_remonta_pra_6():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    m.enviar('agora somos 6')
    k = kit_na_tela(m)
    assert k['pessoas'] == 6 and sum(lin['qtd'] for lin in k['linhas'] if lin['papel'] == 'principal') == 6


def test_sem_numero_de_pessoas_pergunta_e_o_numero_digitado_e_de_pessoas():
    m = pronto(Mundo())
    m.enviar('quero pizza pra galera dividir')
    assert m.estado()['fase'] == 'grupo_pessoas' and 'grupo_n:2' in ids(m)
    m.enviar('6')  # 6 pessoas, não o "6º botão"
    k = kit_na_tela(m)
    assert k['pessoas'] == 6 and 'pizza' in k['tema']['termo']


def test_sem_comida_pergunta_o_que_comer_e_pizza_pra_4_vai_grande():
    m = pronto(Mundo())
    m.enviar('vamos lanchar em 4 pessoas')
    assert m.estado()['fase'] == 'grupo_tema' and 'O que vocês querem comer' in textos(m)
    m.enviar('pizza')
    k = kit_na_tela(m)
    # a pizzaria mais em conta (src/bot/melhor_loja.py): Forno a Lenha, R$ 39,90 + R$ 3,90 de entrega
    assert k['pessoas'] == 4 and k['loja'] == 'Pizzaria Forno a Lenha'
    pizzas = [lin for lin in k['linhas'] if lin['papel'] == 'principal']
    assert pizzas and all('Grande (8 fatias)' in lin['nome'] for lin in pizzas)  # pra 4 vai a grande
    m.tocar('kit:ok')  # o mock valida as opções obrigatórias (tamanho) no formato do carrinho
    assert m.estado()['carrinho']['itens'] and 'Coloquei o kit' in textos(m)


def test_kit_sem_login_e_sem_endereco_retoma_depois():
    m = Mundo(logado=False)
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    assert m.wpp.saida[-1][0] == 'link'
    m.logar()
    m.enviar('Rua das Flores, 120, São Carlos')
    m.tocar('cand:0')
    m.tocar('compl_nao')
    assert kit_na_tela(m)['pessoas'] == 5 and m.estado()['fase'] == 'kit'


def test_vamos_dividir_em_3_divide_o_pedido_que_ja_esta_montado():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')  # o pão da busca do endereco_pronto
    m.tocar('qtd:2')
    m.enviar('vamos dividir em 3')
    assert 'por pessoa* (3 pessoas)' in textos(m) and m.estado()['grupo']['pessoas'] == 3


def test_mais_de_30_pessoas_pede_outro_numero():
    m = pronto(Mundo())
    m.enviar('hamburguer pra 50 pessoas')
    assert m.estado()['fase'] == 'grupo_pessoas' and 'mais de 30' in textos(m)
    m.tocar('grupo_n:4')
    assert kit_na_tela(m)['pessoas'] == 4


def test_kit_com_pedido_de_outra_loja_avisa_que_troca():
    m = Mundo()
    endereco_pronto(m)
    m.tocar('pick:')
    m.tocar('qtd:1')  # pão no carrinho (mercado)
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    assert 'troca o pedido que você estava montando' in m.wpp.saida[-1][1]['texto']
    m.tocar('kit:ok')
    car = m.estado()['carrinho']
    assert car['loja_id'] == m.estado()['grupo']['loja_id'] and not any('Pão' in i['nome'] for i in car['itens'])


def test_cancelar_com_kit_esquece_tudo():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    m.enviar('cancelar')
    e = m.estado()
    assert e['kit'] is None and e['grupo'] is None and e['fase'] == 'pedido'


def test_hamburguer_com_coca_pedida_entra_no_kit():
    m = pronto(Mundo())
    m.enviar('lanchar em 4 pessoas hamburguer com coca')
    k = kit_na_tela(m)
    assert any(lin['papel'] == 'pedido' and 'Coca' in lin['nome'] for lin in k['linhas'])


def test_gemini_fora_o_kit_sai_pela_regra_fixa():
    m = pronto(Mundo())
    m.llm.falhar = True
    m.enviar('quero lanchar em 5 pessoas hamburguer dividindo')
    k = kit_na_tela(m)
    assert k['pessoas'] == 5 and k['explicacao'] is None
    assert sum(lin['qtd'] for lin in k['linhas'] if lin['papel'] == 'principal') == 5
    assert any('2 litros' in lin['nome'] and lin['qtd'] == 2 for lin in k['linhas'])   # 5 pessoas = 2 garrafas
    assert any('Batata' in lin['nome'] and lin['qtd'] == 2 for lin in k['linhas'])     # 5 pessoas = 2 porções


def test_kit_que_o_gemini_errou_cai_na_regra_fixa_e_dinheiro_na_fala_some():
    m = pronto(Mundo())
    m.llm.kit = {'itens': [{'n': 99, 'qtd': 3}], 'explicacao': 'Fica R$ 10,00 pra cada'}
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    k = kit_na_tela(m)
    assert k['explicacao'] is None and sum(lin['qtd'] for lin in k['linhas'] if lin['papel'] == 'principal') == 5


def test_comida_que_nao_tem_perto_explica_e_pergunta_outra():
    m = pronto(Mundo())
    m.enviar('sushi pra 4 pessoas dividir')
    assert 'Não achei' in textos(m) and m.estado()['fase'] == 'grupo_tema'


# --- peças -------------------------------------------------------------------------------

def test_pessoas_conta_quem_esta_escrevendo():
    casos = {'quero lanchar em 5 pessoas hamburguer': 5, 'eu e mais 3 vamos pedir pizza': 4,
             'pizza com 4 amigos': 4, 'com mais 4 amigos': 5, 'estou com 13 amigos': 13, 'eu e 2 amigos': 3, 'pizza pra 4': 4, 'somos 6 aqui': 6,
             'eu e minha esposa': 2, 'um casal': 2, 'familia de 4': 4, 'cinco pessoas': 5,
             'quero 2 desse pra mim e mais 3 amigos': 4, 'quero 2 pizzas': None, 'pão e leite': None}
    for texto, n in casos.items():
        assert grupo.pessoas_em(texto) == n, texto


def test_por_pessoa_arredonda_pra_cima_no_centavo():
    assert grupo.por_pessoa(100, 3) == 33.34
    assert grupo.por_pessoa(182.09, 5) == 36.42
    assert grupo.por_pessoa(90, 3) == 30.0
    assert grupo.por_pessoa(0, 3) is None


def test_opcoes_automaticas_escolhem_o_tamanho_grande_pra_grupo():
    item = {'grupos': [{'id': 'g1', 'nome': 'Tamanho', 'min': 1, 'opcoes': [
        {'id': 'm', 'nome': 'Média (6 fatias)', 'preco': 0}, {'id': 'g', 'nome': 'Grande (8 fatias)', 'preco': 12.0}]},
        {'id': 'g2', 'nome': 'Borda', 'min': 0, 'opcoes': [{'id': 'b', 'nome': 'Catupiry', 'preco': 8}]}]}
    assert [o['opcao_id'] for o in grupo.opcoes_automaticas(item, 4)] == ['g']
    assert [o['opcao_id'] for o in grupo.opcoes_automaticas(item, 2)] == ['m']
    sabor = {'grupos': [{'id': 's', 'nome': 'Sabor', 'min': 1, 'opcoes': [
        {'id': '1', 'nome': 'Guaraná'}, {'id': '2', 'nome': 'Coca-Cola'}]}]}
    assert [o['opcao_id'] for o in grupo.opcoes_automaticas(sabor, 5, preferir='coca cola')] == ['2']
    assert grupo.opcoes_automaticas({'grupos': [{'id': 'x', 'nome': 'X', 'min': 2, 'opcoes': [{'id': 'a', 'nome': 'A'}]}]},
                                    3) is None


def test_texto_do_kit_cabe_na_mensagem_com_botoes_mesmo_cheio():
    linhas = [{'nome': 'Pizza de frango com catupiry muito recheada (Grande (8 fatias), Borda de catupiry)',
               'qtd': 12, 'total': 999.9, 'papel': 'principal'}] * 8
    k = {'pessoas': 30, 'loja': 'Pizzaria Bella Napoli do Centro da Cidade', 'linhas': linhas, 'taxa': 6.9,
         'total': 8006.1, 'explicacao': 'x' * 200, 'faltou': ['coca-cola', 'guaraná']}
    assert tamanho(T.kit(k, troca='Supermercado Central')) <= 1024


def test_quero_esse_kit_de_um_kit_antigo_nao_compra_o_kit_novo():
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    velho = next(i for i in ids(m) if i.startswith('kit:ok:'))
    m.enviar('agora somos 6')
    m.enviar(('botao', velho))
    assert not m.mcp.chamadas_de('createCart') and 'conversa antiga' in textos(m)
    assert m.estado()['fase'] == 'kit' and m.estado()['kit']['pessoas'] == 6
    m.tocar('kit:ok:')
    assert m.mcp.chamadas_de('createCart')


def test_sim_de_uma_foto_antiga_nao_busca_a_foto_nova():
    m = pronto(Mundo())
    m.enviar(('foto', 'foto1'))
    velho = next(i for i in ids(m) if i.startswith('foto:sim:'))
    m.llm.foto = {'tipo': 'comida', 'descricao': 'pizza',
                  'parecidos': [{'termo': 'pizza', 'busca': 'pizza', 'tipo_loja': 'RESTAURANTE'}]}
    m.enviar(('foto', 'foto2'))
    antes = len(m.mcp.chamadas_de('searchOffers'))
    m.enviar(('botao', velho))
    assert len(m.mcp.chamadas_de('searchOffers')) == antes and 'conversa antiga' in textos(m)


def test_foto_de_outra_coisa_com_pedido_escrito_nao_perde_o_pedido():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'outro', 'descricao': 'gato', 'itens': [
        {'termo': 'ração para gatos', 'busca': 'ração gatos', 'tipo_loja': 'PET'}]}
    m.enviar(('foto', 'gato1', 'quero ração pra ele'))
    assert m.mcp.chamadas_de('searchOffers')[-1]['query'] == 'ração gatos'


def test_comida_digitada_quando_pergunta_quantas_pessoas_continua_no_grupo():
    m = pronto(Mundo())
    m.enviar('quero pizza pra galera dividir')
    m.enviar('quero pizza')  # respondeu a comida de novo em vez do número: continua no grupo
    assert m.estado()['fase'] == 'grupo_pessoas'
    m.tocar('grupo_n:4')
    assert m.estado()['kit']['pessoas'] == 4


def test_comida_que_o_gemini_deixou_so_no_texto_ainda_vira_o_kit():
    m = pronto(Mundo())
    resposta = {'acao': 'grupo', 'numero': 5, 'itens': [], 'texto': 'pizza com 4 amigos e coca'}
    original = m.llm.__call__

    def gemini(sistema, partes, esquema, **kw):  # só a interpretação vem "errada", o resto segue o fake
        if 'acao' in esquema['properties']:
            return resposta, 'fake', 0.01
        return original(sistema, partes, esquema, **kw)
    m.ctx._gerar_json = gemini
    m.enviar('pizza com 4 amigos e coca')
    k = m.estado()['kit']
    assert k['pessoas'] == 5 and k['tema']['termo'] == 'pizza' and [e['termo'] for e in k['extras']] == ['coca-cola']
    assert k['ajuste'] is None  # a frase inteira não vira "restrição" do kit


def test_legenda_me_ve_2_desse_busca_direto_mesmo_com_o_gemini_dizendo_que_nao():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'comida', 'descricao': 'x-bacon', 'ja_pediu': False, 'quantidade': 2,
                  'parecidos': [{'termo': 'x-bacon', 'busca': 'x-bacon', 'tipo_loja': 'RESTAURANTE'}]}
    m.enviar(('foto', 'f1', 'me vê 2 desse'))
    assert not any(i.startswith('foto:') for i in ids(m)) and m.wpp.cards()


def test_legenda_pra_mim_e_mais_3_vira_kit_mesmo_sem_o_gemini_contar_as_pessoas():
    m = pronto(Mundo())
    m.llm.foto = {'tipo': 'comida', 'descricao': 'hambúrguer', 'pessoas': None,
                  'parecidos': [{'termo': 'hambúrguer', 'busca': 'hamburguer', 'tipo_loja': 'RESTAURANTE'}]}
    m.enviar(('foto', 'f1', 'quero desse pra mim e mais 3 amigos'))
    assert m.estado()['kit']['pessoas'] == 4


def test_ajuste_que_so_tira_mantem_os_lanches_do_kit():
    # 18/10 04h18: "quero esse mesmo pedido so que sem a batata e sem o refri" trocou X-Bacon por X-Salada
    m = pronto(Mundo())
    m.enviar('quero lanchar em 5 pessoas hamburguer')
    antes = kit_na_tela(m)
    lanches = sorted((lin['item_id'], lin['qtd']) for lin in antes['linhas'] if lin['papel'] == 'principal')
    cands = antes['candidatos']
    fora = [i for i, c in enumerate(cands) if c['papel'] == 'principal'
            and c['item_id'] not in {x for x, _ in lanches}]
    bebida = next(i for i, c in enumerate(cands) if c['papel'] == 'bebida')
    assert fora  # o mock tem outro lanche pra o Gemini "trocar"
    m.llm.kit = {'itens': [{'n': fora[0], 'qtd': 5}, {'n': bebida, 'qtd': 2}], 'explicacao': 'Trocado 🍔'}
    antes_llm = len(m.llm.prompts)
    m.enviar('quero esse mesmo pedido so que sem a batata e sem o refri')
    k = kit_na_tela(m)
    assert sorted((lin['item_id'], lin['qtd']) for lin in k['linhas'] if lin['papel'] == 'principal') == lanches
    assert not any(lin['papel'] == 'bebida' or 'atata' in lin['nome'] for lin in k['linhas'])
    # 18/10 08h: "sem X" é o código que aplica (src/bot/kit_ajuste.py): o modelo nem é chamado, e a fala é do código
    assert not any('Produtos da loja' in t for _, t in m.llm.prompts[antes_llm:])
    assert k['explicacao'].startswith('Tirei') and 'Batata' in k['explicacao'] and 'Coca' in k['explicacao']


def test_lista_anotada_mostra_a_quantidade_so_quando_tem():
    from src.bot import textos as T
    m = pronto(Mundo())
    m.llm.foto = LISTA
    m.enviar(('foto', 'lista1'))
    anotei = next(t for t in m.wpp.textos() if 'Anotei sua lista' in t)
    assert '1. pão francês\n' in anotei and '2. 2x leite\n' in anotei
    sem_qtd = T.lista_de_compras([{'termo': 'arroz'}, {'termo': 'feijão', 'quantidade': 3}])
    assert '1. arroz\n2. 3x feijão' in sem_qtd and 'Começando por *arroz*' in sem_qtd


def test_foto_sem_relacao_no_meio_dos_cards_limpa_os_restos():
    m = pronto(Mundo())  # os cards do pão estão na tela
    assert m.estado()['fase'] == 'escolhendo' and m.estado()['visiveis']
    m.wpp.limpar()
    m.llm.foto = {'tipo': 'outro', 'descricao': 'paisagem', 'resposta': '[fala] Que vista linda! 😍'}
    m.enviar(('foto', 'praia1'))
    assert 'Gostou de algum' not in textos(m) and 'Quero esse' not in textos(m)
    assert 'outra' not in ids(m) and 'pedir' in ids(m)  # nada de "Procurar outra" sem card
    assert m.estado()['fase'] == 'pedido' and not m.estado()['visiveis']
    m.wpp.limpar()
    m.enviar('sim')
    assert 'Qual deles' not in textos(m)  # o "sim" não cai nos cards antigos
