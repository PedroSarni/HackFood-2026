"""Servidor LOCAL do dash: empurra as conversas pro navegador em tempo real, de duas fontes ao mesmo tempo.

    .venv/Scripts/python.exe -m src.painel.servidor

- `real`: o diário do bot de verdade (modal.Dict hackfood-painel). Precisa do login do Modal nesta máquina.
- `demo`: clientes simulados conversando com o Bot de verdade (MCP falso), com 30 dias de histórico
  e gente nova chegando ao vivo. Pra apresentação: volume alto sem tocar em dado real.
O dash troca entre as duas no seletor do topo, sem reiniciar nada.

O histórico da demo leva uns 15 s pra gerar na 1ª vez; depois fica em cache na pasta temporária
e só é "trazido pra hoje" (os horários andam junto com o relógio). `--nova-demo` gera de novo.

Depois, em Frontend/Rascunho_Dash: `npm run dev` (o Vite repassa /api pra cá).
Roda só em 127.0.0.1 de propósito: o diário real tem conversa de gente de verdade e o dash ainda
não tem login de admin.

GET /api/sessoes?fonte=real|demo  -> {fonte, estado, agora, sessions}   (foto do momento)
GET /api/stream?fonte=real|demo   -> text/event-stream                  (a foto de novo a cada mudança)
GET /api/mcp?fonte=&dias=&conversa= -> uso do MCP por tool, tools nunca chamadas, sequência da conversa
GET /api/agentes?fonte=&dias=&conversa= -> uso dos agentes de IA e das regras, linha do tempo da conversa
GET /api/equipe?fonte=             -> a ficha de cada agente (src/agentes/): persona, prompt, fila, keys mascaradas
POST /api/equipe/<agente>?fonte=   {ligado?, modelo?, limparModelo?} -> liga/desliga ou troca o modelo principal
GET /api/ao-vivo?fonte=&desde=     -> os últimos passos do time, pra animação (sem texto de ninguém)
GET /api/saude
"""
import argparse
import asyncio
import hashlib
import json
import os
import tempfile
import threading
import time

from src import agentes
from src.shared import painel

RECALCULO = 20       # s: status muda com o relógio (carrinho vira abandonado após 30 min) mesmo sem evento novo
ENVIO_MIN = 1.5      # s entre fotos no SSE: a demo tem MBs e muda toda hora
DEMO = {'dias': 30, 'conversas': 900, 'semente': 17, 'versao': 3}  # 3: a demo ganhou o rastro dos agentes
CACHE_DEMO = os.path.join(tempfile.gettempdir(), 'hackfood-painel-demo-v{versao}-{dias}d-{conversas}-{semente}.json'.format(**DEMO))


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


class FonteReal:
    nome = 'real'

    def __init__(self):
        self.dic = None
        self._armazem = None
        self.versao = object()
        self.estado = 'conectando'

    def armazem(self):
        """O armazém do bot (hackfood-estado): onde o dash liga/desliga agentes e lê a ficha do ar."""
        if self._armazem is None:
            import modal
            self._armazem = modal.Dict.from_name('hackfood-estado')
        return self._armazem

    def novos(self, vistos):
        if self.dic is None:
            import modal
            self.dic = modal.Dict.from_name(painel.NOME_DICT, create_if_missing=True)
        versao = self.dic.get('versao')
        self.estado = 'pronto'
        if versao == self.versao:
            return {}
        self.versao = versao
        if not vistos:  # 1ª carga: tudo de uma vez
            return {k: v for k, v in self.dic.items() if k.startswith('ev:')}
        chaves = [k for k in self.dic.keys() if k.startswith('ev:') and k not in vistos]
        return {k: self.dic.get(k) for k in chaves}


class FonteDemo:
    nome = 'demo'

    def __init__(self, nova=False):
        self.dic = DictTravado()
        self.estado = 'carregando'
        self.progresso = 0.0
        self.parar = threading.Event()
        threading.Thread(target=self._preparar, args=(nova,), daemon=True).start()

    def armazem(self):
        return self.dic   # na demo a config dos agentes fica no próprio dict (chave cfg:agentes)

    def _preparar(self, nova):
        from src.painel import simulador
        from src.shared import ifood_mcp
        ifood_mcp.INTERVALO_MIN = 0   # MCP falso: o freio de ~3 chamadas/s só atrasaria
        clientes = None
        if not nova and self._carregar_cache():
            print(f'demo: histórico do cache ({len(self.dic) - 1} eventos), trazido pra hoje')
        else:
            print(f'demo: gerando {DEMO["conversas"]} conversas em {DEMO["dias"]} dias (só na 1ª vez)...')

            def avancar(n, total):
                self.progresso = n / total
            clientes = simulador.preencher_historico(self.dic, dias=DEMO['dias'], conversas=DEMO['conversas'],
                                                     semente=DEMO['semente'], progresso=avancar)
            self._salvar_cache()
            print(f'demo: {len(self.dic.novos(set()))} eventos gerados')
        self.estado = 'pronto'
        if clientes is None:
            clientes = [simulador._cliente(self.dic, n) for n in range(len(simulador.NOMES))]
        simulador.rodar_ao_vivo(self.dic, self.parar, clientes)

    def _carregar_cache(self):
        try:
            with open(CACHE_DEMO, encoding='utf-8') as f:
                cache = json.load(f)
        except (OSError, ValueError):
            return False
        desvio = time.time() - cache['gerado']
        for ev in cache['eventos'].values():
            ev['ts'] += desvio
        self.dic.update(cache['eventos'])
        return True

    def _salvar_cache(self):
        try:
            with open(CACHE_DEMO, 'w', encoding='utf-8') as f:
                json.dump({'gerado': time.time(), 'eventos': self.dic.novos(set())}, f, ensure_ascii=False)
        except OSError as e:
            print(f'demo: não deu pra guardar o cache: {e!r}')

    def novos(self, vistos):
        if self.estado != 'pronto':
            return {}   # enquanto gera, não recalcula a cada evento (seriam milhares de fotos)
        return self.dic.novos(vistos)


class Painel:
    def __init__(self, fonte, intervalo=1.0):
        self.fonte = fonte
        self.intervalo = intervalo
        self.eventos = {}
        self.versao = 0
        self.erro = None
        self._recalculo = 0
        self._sessoes = None
        self.foto = self._fotografar([])
        self._base = ([], {}, [], 0)   # (eventos, rótulos, sessões, carimbo): trocado inteiro, as rotas leem sem trava
        self._cache = {}
        self._equipe = (0, None)

    def _fotografar(self, sessoes):
        return json.dumps({'fonte': self.fonte.nome, 'estado': self.fonte.estado, 'erro': self.erro,
                           'progresso': getattr(self.fonte, 'progresso', None), 'agora': time.time(),
                           'sessions': sessoes}, ensure_ascii=False)

    def girar(self):
        """Busca o que chegou; recalcula as sessões se chegou algo (ou o relógio pediu)."""
        estado_antes = (self.fonte.estado, self.erro, getattr(self.fonte, 'progresso', None))
        try:
            novos = self.fonte.novos(self.eventos.keys())
            self.erro = None
        except Exception as e:  # noqa: BLE001 - Modal fora do ar ou sem login: segue servindo a última foto
            if not self.erro:
                print(f'painel {self.fonte.nome}: ler o diário falhou: {e!r}')
            self.erro = str(e)[:300] or type(e).__name__
            self.fonte.estado = 'erro'
            novos = {}
        novos = {k: v for k, v in novos.items() if isinstance(v, dict)}
        estado_mudou = estado_antes != (self.fonte.estado, self.erro, getattr(self.fonte, 'progresso', None))
        if not novos and not estado_mudou and time.time() - self._recalculo < RECALCULO:
            return False
        self.eventos.update(novos)
        self._recalculo = time.time()
        eventos, rotulos = list(self.eventos.values()), {}
        sessoes = painel.montar_sessoes(eventos, demo=self.fonte.nome == 'demo', rotulos=rotulos)
        mudou = sessoes != self._sessoes or estado_mudou
        self._sessoes = sessoes
        self._base = (eventos, rotulos, sessoes, self._recalculo)
        self.foto = self._fotografar(sessoes)
        if mudou:
            self.versao += 1
        return mudou

    def consulta(self, nome, dias=None, conversa=None):
        """Agregado pronto pro dash (`mcp` ou `agentes`), em cache até o próximo recálculo: o navegador nunca
        recebe o diário inteiro, só o resumo e a conversa aberta."""
        eventos, rotulos, sessoes, carimbo = self._base
        chave = (carimbo, nome, dias, conversa)
        if chave not in self._cache:
            if len(self._cache) > 64 or any(c[0] != carimbo for c in self._cache):
                self._cache = {}
            de = time.time() - float(dias) * 86400 if dias else None
            dados = {'fonte': self.fonte.nome, 'estado': self.fonte.estado, 'agora': time.time(),
                     'conversa': conversa, 'conversasLista': painel.indice_conversas(eventos, rotulos, sessoes, de)}
            resumo = painel.resumo_agentes if nome == 'agentes' else painel.resumo_mcp
            dados.update(resumo(eventos, rotulos, de, conversa))
            self._cache[chave] = json.dumps(dados, ensure_ascii=False)
        return self._cache[chave]

    def equipe(self):
        """A ficha de cada agente (src/agentes/) com o interruptor e o que está no ar. Lida no máx. a cada 3 s."""
        agora = time.time()
        if agora - self._equipe[0] > 3:
            arm = self.fonte.armazem()
            cfg, ar = agentes.config(arm), None
            try:
                ar = arm.get(agentes.CHAVE_AR)
            except Exception:  # noqa: BLE001 - sem a foto do ar, mostra o que dá pra ver daqui
                pass
            dados = agentes.fichas(cfg, ar)
            dados.update({'fonte': self.fonte.nome, 'agora': agora})
            self._equipe = (agora, json.dumps(dados, ensure_ascii=False))
        return self._equipe[1]

    def definir(self, agente_id, ligado=None, modelo=None, limpar_modelo=False):
        agentes.definir(self.fonte.armazem(), agente_id, ligado=ligado, modelo=modelo, limpar_modelo=limpar_modelo)
        self._equipe = (0, None)
        return self.equipe()

    def ao_vivo(self, desde=None, limite=80):
        """Os últimos passos do time (de todas as conversas), pra animação: quem agiu, ok/erro, quanto demorou.
        Sem texto de ninguém: conversa vira um apelido curto e o resumo da IA só tem contagens."""
        eventos = self._base[0]
        desde = float(desde) if desde else time.time() - 90
        saida = []
        for ev in reversed(eventos):     # o diário chega em ordem de tempo: para no primeiro mais velho
            ts = ev.get('ts', 0)
            if ts <= desde:
                if ts < desde - 10:
                    break
                continue
            tipo = ev.get('tipo')
            if tipo not in ('entrada', 'saida', 'ia', 'mcp'):
                continue
            item = {'ts': ts, 'tipo': tipo, 'conversa': hashlib.sha1(str(ev.get('wa')).encode()).hexdigest()[:6]}
            for k in ('agente', 'tool', 'ok', 'ms', 'erro', 'formato', 'reserva', 'modelo', *painel._RESUMO_IA):
                if ev.get(k) is not None:
                    item[k] = ev[k]
            saida.append(item)
            if len(saida) >= limite:
                break
        saida.sort(key=lambda e: e['ts'])
        return json.dumps({'agora': time.time(), 'passos': saida}, ensure_ascii=False)

    def rodar(self):
        while True:
            self.girar()
            time.sleep(self.intervalo)


def criar_api(paineis):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse

    api = FastAPI(docs_url=None, redoc_url=None)

    def escolher(fonte):
        return paineis.get(fonte or 'real')

    @api.get('/api/sessoes')
    async def sessoes(fonte: str = 'real'):
        p = escolher(fonte)
        if not p:
            return JSONResponse({'erro': f'fonte desligada: {fonte}'}, status_code=404)
        return Response(p.foto, media_type='application/json')

    @api.get('/api/stream')
    async def stream(request: Request, fonte: str = 'real'):
        p = escolher(fonte)
        if not p:
            return JSONResponse({'erro': f'fonte desligada: {fonte}'}, status_code=404)

        async def eventos():
            visto, enviado = -1, 0.0
            while not await request.is_disconnected():
                agora = time.time()
                if p.versao != visto and agora - enviado >= ENVIO_MIN:
                    visto, enviado = p.versao, agora
                    yield f'event: sessoes\ndata: {p.foto}\n\n'
                elif agora - enviado > 15:
                    enviado = agora
                    yield ': segue vivo\n\n'   # comentário SSE: mantém a conexão aberta
                await asyncio.sleep(0.3)
        return StreamingResponse(eventos(), media_type='text/event-stream',
                                 headers={'cache-control': 'no-cache', 'x-accel-buffering': 'no'})

    @api.get('/api/mcp')
    async def mcp(fonte: str = 'real', dias: float | None = None, conversa: str | None = None):
        p = escolher(fonte)
        if not p:
            return JSONResponse({'erro': f'fonte desligada: {fonte}'}, status_code=404)
        return Response(p.consulta('mcp', dias, conversa or None), media_type='application/json')

    @api.get('/api/agentes')
    async def uso_dos_agentes(fonte: str = 'real', dias: float | None = None, conversa: str | None = None):
        p = escolher(fonte)
        if not p:
            return JSONResponse({'erro': f'fonte desligada: {fonte}'}, status_code=404)
        return Response(p.consulta('agentes', dias, conversa or None), media_type='application/json')

    @api.get('/api/equipe')
    async def equipe(fonte: str = 'real'):
        p = escolher(fonte)
        if not p:
            return JSONResponse({'erro': f'fonte desligada: {fonte}'}, status_code=404)
        try:
            return Response(await asyncio.to_thread(p.equipe), media_type='application/json')
        except Exception as e:  # noqa: BLE001 - Modal fora: o dash mostra o aviso
            return JSONResponse({'erro': str(e)[:200]}, status_code=503)

    @api.post('/api/equipe/{agente_id}')
    async def definir(agente_id: str, request: Request, fonte: str = 'real'):
        # só o dash local mexe: JSON (navegador manda preflight) e origem local, se vier
        origem = request.headers.get('origin', '')
        if origem and not origem.startswith(('http://127.0.0.1', 'http://localhost')):
            return JSONResponse({'erro': 'origem não permitida'}, status_code=403)
        if 'application/json' not in request.headers.get('content-type', ''):
            return JSONResponse({'erro': 'mande JSON'}, status_code=415)
        p = escolher(fonte)
        if not p or agente_id not in agentes.POR_ID:
            return JSONResponse({'erro': 'agente ou fonte desconhecidos'}, status_code=404)
        corpo = await request.json()
        modelo = corpo.get('modelo')
        if modelo and modelo not in agentes.conhecidos():
            return JSONResponse({'erro': f'modelo fora da lista: {modelo}'}, status_code=400)
        ligado = corpo.get('ligado')
        dados = await asyncio.to_thread(p.definir, agente_id, None if ligado is None else bool(ligado), modelo,
                                        bool(corpo.get('limparModelo')))
        print(f'painel {fonte}: {agente_id} -> {corpo}')
        return Response(dados, media_type='application/json')

    @api.get('/api/ao-vivo')
    async def ao_vivo(fonte: str = 'real', desde: float | None = None):
        p = escolher(fonte)
        if not p:
            return JSONResponse({'erro': f'fonte desligada: {fonte}'}, status_code=404)
        return Response(p.ao_vivo(desde), media_type='application/json')

    @api.get('/api/saude')
    async def saude():
        return {nome: {'estado': p.fonte.estado, 'eventos': len(p.eventos), 'erro': p.erro}
                for nome, p in paineis.items()}

    return api


def main():
    import uvicorn
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--porta', type=int, default=8787)
    ap.add_argument('--sem-real', action='store_true', help='não lê o Modal (sem login, sem internet)')
    ap.add_argument('--sem-demo', action='store_true', help='não sobe os clientes simulados')
    ap.add_argument('--nova-demo', action='store_true', help='ignora o cache e gera o histórico da demo de novo')
    args = ap.parse_args()
    paineis = {}
    if not args.sem_real:
        paineis['real'] = Painel(FonteReal())
    if not args.sem_demo:
        paineis['demo'] = Painel(FonteDemo(nova=args.nova_demo), intervalo=2.0)  # remontar 20 mil eventos custa ~0,5 s
    for p in paineis.values():
        threading.Thread(target=p.rodar, daemon=True).start()
    print(f'painel: http://127.0.0.1:{args.porta}/api/saude · fontes: {", ".join(paineis)}')
    uvicorn.run(criar_api(paineis), host='127.0.0.1', port=args.porta, log_level='warning')


if __name__ == '__main__':
    main()
