"""Junta a rajada de mensagens de cada pessoa antes de responder.

Quem tem pouca intimidade com o celular manda "oi", "quero", "pao", "e leite" em quatro
mensagens, e continua mandando enquanto o bot ainda pensa. Responder cada uma separado
vira uma bagunça de respostas cruzadas. Desenho:

- o webhook põe cada mensagem na fila da pessoa (uma partição por wa_id), grava
  `ult:{wa_id}` = seq dela e dispara uma rodada pra essa seq;
- a rodada espera um silêncio curto (`espera_para`). Se nesse meio tempo chegou outra
  mensagem (ult mudou), ela sai sem fazer nada: a rodada da mensagem mais nova cuida de tudo;
- só uma rodada por pessoa processa por vez (trava atômica no dicionário). Quem chega com a
  trava ocupada espera ela soltar e aí pega o que sobrou na fila. Mensagem que chega durante
  o processamento vira a rodada seguinte, nunca uma resposta duplicada.

Fila e dicionário são injetados: em produção modal.Queue/modal.Dict, nos testes um fake.
"""
import time

# segundos de silêncio esperados depois de cada tipo de mensagem
ESPERA_BOTAO = 0.6     # toque é deliberado; o respiro só pega toque duplo
ESPERA_AUDIO = 1.8
ESPERA_FOTO = 2.5      # costuma vir legenda ou outra mensagem logo atrás
ESPERA_CURTA = 4.0     # "oi", "quero", "boa tarde": quase sempre tem continuação
ESPERA_TEXTO = 2.5
ESPERA_MAX = 9.0       # teto contado desde a primeira mensagem ainda não respondida
TRAVA_VELHA = 300      # trava mais velha que isso é de container que morreu
TRAVA_ESPERA = 600     # quanto uma rodada aceita esperar a anterior terminar


def espera_para(msg):
    tipo = msg.get('type')
    if tipo in ('interactive', 'button'):
        return ESPERA_BOTAO
    if tipo == 'audio':
        return ESPERA_AUDIO
    if tipo in ('image', 'document', 'sticker', 'video'):
        return ESPERA_FOTO
    if tipo == 'text':
        corpo = ((msg.get('text') or {}).get('body') or '').strip()
        return ESPERA_CURTA if len(corpo) <= 12 else ESPERA_TEXTO
    return ESPERA_TEXTO


class Caixa:
    """Caixa de entrada por pessoa."""

    def __init__(self, fila, dic, relogio=time.time, dormir=time.sleep):
        self.fila = fila
        self.dic = dic
        self.relogio = relogio
        self.dormir = dormir

    def guardar(self, wa_id, msg):
        """Chamado pelo webhook. Devolve a seq que a rodada deve receber."""
        seq = time.time_ns()
        self.fila.put(msg, partition=wa_id)
        self.dic.put(f'prim:{wa_id}', self.relogio(), skip_if_exists=True)
        self.dic[f'ult:{wa_id}'] = seq
        return seq

    def ainda_e_a_ultima(self, wa_id, seq):
        return self.dic.get(f'ult:{wa_id}') == seq

    def aguardar_silencio(self, wa_id, seq, espera):
        """Dorme o silêncio pedido (respeitando o teto) e diz se esta rodada continua dona."""
        prim = self.dic.get(f'prim:{wa_id}') or self.relogio()
        limite = prim + ESPERA_MAX - self.relogio()
        self.dormir(max(0.0, min(espera, limite)))
        return self.ainda_e_a_ultima(wa_id, seq)

    def pegar_trava(self, wa_id, seq):
        """True quando conseguiu. False quando desistiu porque chegou mensagem mais nova
        (a rodada dela é que vai esperar) ou porque esperou demais."""
        chave = f'trava:{wa_id}'
        inicio = self.relogio()
        while True:
            if self.dic.put(chave, {'seq': seq, 'ts': self.relogio()}, skip_if_exists=True):
                return True
            atual = self.dic.get(chave)
            if atual and self.relogio() - atual.get('ts', 0) > TRAVA_VELHA:
                self.dic.pop(chave, None)
                continue
            if not self.ainda_e_a_ultima(wa_id, seq) or self.relogio() - inicio > TRAVA_ESPERA:
                return False
            self.dormir(0.4)

    def soltar_trava(self, wa_id, seq):
        chave = f'trava:{wa_id}'
        atual = self.dic.get(chave)
        if atual and atual.get('seq') == seq:
            self.dic.pop(chave, None)

    def retirar(self, wa_id):
        """Tudo que está na fila da pessoa, na ordem de chegada."""
        msgs = []
        while True:
            lote = self.fila.get_many(100, block=False, partition=wa_id)
            if not lote:
                break
            msgs.extend(lote)
        self.dic.pop(f'prim:{wa_id}', None)
        # a Meta às vezes entrega fora de ordem; o timestamp dela manda
        msgs.sort(key=lambda m: int(m.get('timestamp') or 0))
        return msgs
