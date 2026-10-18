"""Servidor LOCAL do dash: lê o diário do bot e empurra as conversas pro navegador em tempo real.

    .venv/Scripts/python.exe -m src.painel.servidor             # bot de verdade (modal.Dict hackfood-painel)
    .venv/Scripts/python.exe -m src.painel.servidor --simular   # clientes simulados, só nesta máquina

Depois, em Frontend/Rascunho_Dash: `npm run dev` (o Vite repassa /api pra cá).

Roda só em 127.0.0.1 e de propósito não vai pro Modal: o diário tem conversa de gente de
verdade, e o dash ainda não tem login de admin. Pra ler o modal.Dict basta estar logado no
Modal nesta máquina (o mesmo login do deploy).

GET /api/sessoes  -> {fonte, agora, sessions}   (foto do momento)
GET /api/stream   -> text/event-stream          (manda a foto de novo a cada mudança)
"""
import argparse
import asyncio
import json
import threading
import time

from src.shared import painel

RECALCULO = 20   # s: status muda com o relógio (carrinho vira abandonado após 30 min) mesmo sem evento novo


class DictTravado(dict):
    """dict em memória pro simulador: várias threads escrevem, o servidor lê."""

    def __init__(self):
        super().__init__()
        self.trava = threading.Lock()

    def update(self, *a, **kw):
        with self.trava:
            super().update(*a, **kw)

    def put(self, chave, valor, skip_if_exists=False):
        with self.trava:
            if skip_if_exists and chave in self:
                return False
            self[chave] = valor
            return True

    def novos(self, vistos):
        with self.trava:
            return {k: v for k, v in self.items() if k.startswith('ev:') and k not in vistos}


class FonteModal:
    nome = 'bot'

    def __init__(self):
        import modal
        self.dic = modal.Dict.from_name(painel.NOME_DICT, create_if_missing=True)
        self.versao = object()

    def novos(self, vistos):
        versao = self.dic.get('versao')
        if versao == self.versao:
            return {}
        self.versao = versao
        if not vistos:  # 1ª carga: tudo de uma vez
            return {k: v for k, v in self.dic.items() if k.startswith('ev:')}
        chaves = [k for k in self.dic.keys() if k.startswith('ev:') and k not in vistos]
        return {k: self.dic.get(k) for k in chaves}


class FonteSimulada:
    nome = 'simulado'

    def __init__(self):
        from src.painel import simulador
        from src.shared import ifood_mcp
        ifood_mcp.INTERVALO_MIN = 0   # MCP falso: o freio de ~3 chamadas/s só atrasaria
        self.dic = DictTravado()
        print('simulador: preenchendo os últimos 7 dias...')
        clientes = simulador.preencher_historico(self.dic)
        print(f'simulador: {len(self.dic.novos(set()))} eventos no histórico; agora ao vivo')
        self.parar = threading.Event()
        threading.Thread(target=simulador.rodar_ao_vivo, args=(self.dic, self.parar, clientes), daemon=True).start()

    def novos(self, vistos):
        return self.dic.novos(vistos)


class Painel:
    def __init__(self, fonte, intervalo=1.0):
        self.fonte = fonte
        self.intervalo = intervalo
        self.eventos = {}
        self.versao = 0
        self.foto = json.dumps({'fonte': fonte.nome, 'agora': time.time(), 'sessions': []})
        self.erro = None
        self._recalculo = 0
        self._sessoes = None

    def girar(self):
        """Busca o que chegou; recalcula as sessões se chegou algo (ou o relógio pediu)."""
        try:
            novos = self.fonte.novos(self.eventos.keys())
            self.erro = None
        except Exception as e:  # noqa: BLE001 - Modal fora do ar: segue servindo a última foto
            if not self.erro:
                print(f'painel: ler o diário falhou: {e!r}')
            self.erro = str(e)[:200]
            novos = {}
        novos = {k: v for k, v in novos.items() if isinstance(v, dict)}
        if not novos and time.time() - self._recalculo < RECALCULO:
            return False
        self.eventos.update(novos)
        self._recalculo = time.time()
        sessoes = painel.montar_sessoes(self.eventos.values(), demo=self.fonte.nome == 'simulado')
        mudou = sessoes != self._sessoes
        self._sessoes = sessoes
        self.foto = json.dumps({'fonte': self.fonte.nome, 'agora': time.time(), 'erro': self.erro, 'sessions': sessoes},
                               ensure_ascii=False)
        if mudou:
            self.versao += 1
            if novos:
                print(f'painel: +{len(novos)} evento(s) · {len(sessoes)} sessões')
        return mudou

    def rodar(self):
        while True:
            self.girar()
            time.sleep(self.intervalo)


def criar_api(p):
    from fastapi import FastAPI, Request
    from fastapi.responses import Response, StreamingResponse

    api = FastAPI(docs_url=None, redoc_url=None)

    @api.get('/api/sessoes')
    async def sessoes():
        return Response(p.foto, media_type='application/json')

    @api.get('/api/stream')
    async def stream(request: Request):
        async def eventos():
            visto, quieto = -1, time.time()
            while not await request.is_disconnected():
                if p.versao != visto:
                    visto, quieto = p.versao, time.time()
                    yield f'event: sessoes\ndata: {p.foto}\n\n'
                elif time.time() - quieto > 15:
                    quieto = time.time()
                    yield ': segue vivo\n\n'   # comentário SSE: mantém a conexão aberta
                await asyncio.sleep(0.4)
        return StreamingResponse(eventos(), media_type='text/event-stream',
                                 headers={'cache-control': 'no-cache', 'x-accel-buffering': 'no'})

    @api.get('/api/saude')
    async def saude():
        return {'ok': True, 'fonte': p.fonte.nome, 'eventos': len(p.eventos), 'erro': p.erro}

    return api


def main():
    import uvicorn
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--simular', action='store_true', help='clientes simulados em vez do bot de verdade')
    ap.add_argument('--porta', type=int, default=8787)
    args = ap.parse_args()
    p = Painel(FonteSimulada() if args.simular else FonteModal())
    p.girar()
    threading.Thread(target=p.rodar, daemon=True).start()
    print(f'painel: http://127.0.0.1:{args.porta}/api/sessoes ({p.fonte.nome})')
    uvicorn.run(criar_api(p), host='127.0.0.1', port=args.porta, log_level='warning')


if __name__ == '__main__':
    main()
