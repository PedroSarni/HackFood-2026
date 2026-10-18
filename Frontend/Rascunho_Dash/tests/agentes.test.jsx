import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../app.jsx';
import { summaryUrl } from '../telemetria.js';

// Resposta de /api/mcp do jeito que src/painel/servidor.py manda (painel.resumo_mcp + índice).
const conversas = [{ id: 'WA-AAA111-001', nome: 'Dona Cida', inicio: '2026-10-17T20:00:00.000Z', fim: '2026-10-17T20:05:00.000Z', mcp: 3, ia: 2 }];
const mcp = (conversa = null) => ({
  fonte: 'real', estado: 'pronto', conversa, conversasLista: conversas, total: conversa ? 3 : 4, conversas: conversa ? 1 : 2,
  tools: [
    { tool: 'searchOffers', dominio: 'offer_discovery_mcp', chamadas: 3, pct: 75, erros: 1, pctErro: 33.3, msMedio: 500, msMax: 1200, conversas: 2, erroComum: 'TIMEOUT' },
    { tool: 'createCart', dominio: 'cart_mcp', chamadas: 1, pct: 25, erros: 0, pctErro: 0, msMedio: 300, msMax: 300, conversas: 1, erroComum: null },
  ],
  nunca: [{ tool: 'submitOrder', dominio: 'cart_mcp', soNaDoc: false }, { tool: 'listItemTaxonomy', dominio: 'offer_discovery_mcp', soNaDoc: true }],
  sequencia: conversa ? [
    { at: '2026-10-17T20:00:01.000Z', tool: 'searchOffers', ok: true, ms: 200, erro: null },
    { at: '2026-10-17T20:00:02.000Z', tool: 'searchOffers', ok: false, ms: 1200, erro: 'TIMEOUT' },
    { at: '2026-10-17T20:00:03.000Z', tool: 'createCart', ok: true, ms: 300, erro: null },
  ] : null,
});

function stubFetch(responder) {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn(async url => { calls.push(url); return { ok: true, json: async () => responder(new URL(url, 'http://x')) }; }));
  return calls;
}
const mount = path => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

afterEach(() => vi.unstubAllGlobals());

describe('Uso do MCP', () => {
  it('monta a URL só com o recorte: o diário inteiro nunca vem pro navegador', () => {
    expect(summaryUrl('mcp', { source: 'demo', period: '7', conversation: 'WA-1' })).toBe('/api/mcp?fonte=demo&dias=7&conversa=WA-1');
    expect(summaryUrl('mcp', { source: 'real', period: '30' })).toBe('/api/mcp?fonte=real&dias=30');
  });

  it('mostra uso por tool, erro, latência e as tools nunca chamadas', async () => {
    const calls = stubFetch(() => mcp());
    mount('/mcp');
    expect(await screen.findByRole('heading', { name: 'Uso por tool' })).toBeTruthy();
    expect(calls[0]).toBe('/api/mcp?fonte=real&dias=30');
    const row = screen.getByRole('cell', { name: 'searchOffers' }).closest('tr');
    expect(within(row).getByText('Ofertas')).toBeTruthy();
    expect(within(row).getByText('33,3%')).toBeTruthy();
    expect(within(row).getByText('1,2 s')).toBeTruthy();
    expect(screen.getByText('2 de 23')).toBeTruthy();
    expect(screen.getByText('só na doc')).toBeTruthy();
    expect(screen.getByText('submitOrder')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Sequência das chamadas' })).toBeNull();
  });

  it('filtra por conversa e mostra a sequência das chamadas na ordem', async () => {
    const user = userEvent.setup();
    const calls = stubFetch(url => mcp(url.searchParams.get('conversa')));
    mount('/mcp');
    await user.selectOptions(await screen.findByLabelText('Conversa'), 'WA-AAA111-001');
    expect(await screen.findByRole('heading', { name: 'Sequência das chamadas' })).toBeTruthy();
    expect(calls.at(-1)).toBe('/api/mcp?fonte=real&dias=30&conversa=WA-AAA111-001');
    const steps = [...document.querySelectorAll('.call-sequence li')].map(li => li.querySelector('strong').textContent);
    expect(steps).toEqual(['searchOffers', 'searchOffers', 'createCart']);
    expect(document.querySelector('.call-sequence li.failed').textContent).toContain('TIMEOUT');
  });

  it('servidor fora do ar não quebra a página', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));
    mount('/mcp');
    expect(await screen.findByText('Sem resposta do servidor do painel.')).toBeTruthy();
  });

  it('fonte de demonstração vem com o rótulo de demonstração', async () => {
    localStorage.setItem('hackfood-source', 'demo');
    stubFetch(() => ({ ...mcp(), fonte: 'demo' }));
    mount('/mcp');
    expect(await screen.findByText(/Dados simulados/)).toBeTruthy();
  });
});

// Resposta de /api/agentes (painel.resumo_agentes + índice).
const agentes = (conversa = null) => ({
  fonte: 'real', estado: 'pronto', conversa, conversasLista: conversas, total: 3,
  agentes: [
    { agente: 'relevancia', nome: 'Relevância e sugestão', tipo: 'ia', chamadas: 2, pct: 66.7, erros: 1, pctErro: 50, msMedio: 2600, msMax: 4000, conversas: 1, modelos: [{ modelo: 'gemini-3.1-flash-lite', n: 1 }], reserva: 1 },
    { agente: 'entendimento', nome: 'Entendimento', tipo: 'ia', chamadas: 1, pct: 33.3, erros: 0, pctErro: 0, msMedio: 800, msMax: 800, conversas: 1, modelos: [{ modelo: 'gemini-3.5-flash-lite', n: 1 }], reserva: 0 },
    { agente: 'foto', nome: 'Foto', tipo: 'ia', chamadas: 0, pct: 0, erros: 0, pctErro: 0, msMedio: null, msMax: null, conversas: 0, modelos: [], reserva: 0 },
  ],
  regras: [{ agente: 'followup', nome: 'Follow-up', tipo: 'regra', disparos: 2, conversas: 1 }, { agente: 'recorrencia', nome: 'Recorrência', tipo: 'regra', disparos: 0, conversas: 0 }, { agente: 'vitrine', nome: 'Vitrine', tipo: 'regra', disparos: 1, conversas: 1 }],
  linha: conversa ? [
    { at: '2026-10-17T20:00:00.000Z', tipo: 'mensagem', formato: 'Texto', botao: false },
    { at: '2026-10-17T20:00:01.000Z', tipo: 'ia', agente: 'entendimento', nome: 'Entendimento', modelo: 'gemini-3.5-flash-lite', reserva: false, ms: 800, ok: true, erro: null, resumo: { acao: 'comprar', itens: 1 } },
    { at: '2026-10-17T20:00:02.000Z', tipo: 'mcp', tool: 'searchOffers', ok: true, ms: 300, erro: null },
    { at: '2026-10-17T20:00:03.000Z', tipo: 'ia', agente: 'relevancia', nome: 'Relevância e sugestão', modelo: 'gemini-3.1-flash-lite', reserva: true, ms: 1200, ok: true, erro: null, resumo: { mantidas: 3 } },
    { at: '2026-10-17T20:05:00.000Z', tipo: 'regra', agente: 'followup', nome: 'Follow-up' },
    { at: '2026-10-17T20:05:00.000Z', tipo: 'resposta', formato: 'Botões', origem: 'followup' },
  ] : null,
});

// Resposta de /api/equipe (src/agentes.fichas) e /api/ao-vivo (servidor.Painel.ao_vivo).
const ficha = (id, nome, cargo, extra = {}) => ({
  id, nome, cargo, emoji: '🤖', cor: '#7a5af8', bordao: `Sou ${nome}.`, faz: `${nome} trabalha.`, planoB: `Plano B de ${nome}.`,
  arquivos: [`src/agentes/${id}.py`, `src/bot/${id}.py`], tipo: 'ia', essencial: false, ligado: true, modeloEscolhido: null,
  modelos: [{ modelo: 'gemini-3.5-flash-lite', prazo: 6, pensamento: '' }, { modelo: 'gemini-3.8-flash', prazo: 9, pensamento: 'low' }],
  modelosNoAr: null, keys: [{ nome: 'GEMINI_API_KEY', secret: 'hackathon-gemini', configurada: true, final: '····a91F' }], keysDoAr: true,
  prompts: [`PROMPT DE ${nome.toUpperCase()}`], versaoPrompt: 'abc12345', versaoNoAr: 'abc12345', ...extra,
});
const equipe = (cfg = {}) => ({
  fonte: 'real', agora: 1, conhecidos: ['gemini-3.5-flash-lite', 'gemini-3.8-flash'], arQuando: 1,
  agentes: [ficha('entendimento', 'Lia', 'Intérprete', { essencial: true, ...cfg.entendimento }), ficha('relevancia', 'Duda', 'Curadora', cfg.relevancia),
    ficha('foto', 'Íris', 'Leitora de fotos', cfg.foto), ficha('ouvido', 'Otto', 'Ouvinte', { tipo: 'servico', prompts: [], ...cfg.ouvido })],
});
const passos = [{ ts: 100, tipo: 'entrada', conversa: 'aa', formato: 'Texto' }, { ts: 101, tipo: 'ia', conversa: 'aa', agente: 'relevancia', ok: true, ms: 900, mantidas: 3 }];

function stubTeam({ conversa = false } = {}) {
  const posts = [];
  let cfg = {};
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    const u = new URL(url, 'http://x');
    let body;
    if (options.method === 'POST') {
      const id = u.pathname.split('/').pop(), pedido = JSON.parse(options.body);
      posts.push([id, pedido]);
      cfg = { ...cfg, [id]: { ...(cfg[id] || {}), ...('ligado' in pedido ? { ligado: pedido.ligado } : {}), ...(pedido.modelo ? { modeloEscolhido: pedido.modelo } : {}) } };
      body = equipe(cfg);
    } else if (u.pathname === '/api/equipe') body = equipe(cfg);
    else if (u.pathname === '/api/ao-vivo') body = { agora: 200, passos: u.searchParams.get('desde') ? [] : passos };
    else if (u.pathname === '/api/mcp') body = mcp();
    else body = agentes(conversa ? u.searchParams.get('conversa') : null);
    return { ok: true, json: async () => body };
  }));
  return posts;
}

describe('Agentes (a 1ª tela)', () => {
  it('abre no time: cada agente com desempenho, e as rotinas sem IA à parte', async () => {
    stubTeam();
    mount('/');
    const duda = await screen.findByRole('button', { name: /Abrir a ficha de Duda/ });
    expect(await within(duda).findByText('50,0%')).toBeTruthy();   // 1 erro em 2 chamadas
    expect(within(duda).getByText('2,6 s')).toBeTruthy();
    expect(screen.getByText('Follow-up · 2 disparos')).toBeTruthy();
    expect(screen.queryByText('Exportar')).toBeNull();      // a tela do time não tem exportação de vendas
    expect([...document.querySelectorAll('nav .nav-link')].map(e => e.textContent).slice(0, 3)).toEqual(['Agentes', 'Uso do MCP', 'Dinheiro']);
  });

  it('o palco conta o que o time fez, sem texto de ninguém', async () => {
    stubTeam();
    mount('/');
    expect((await screen.findAllByText('Fiquei com 3 ofertas', { exact: false }, { timeout: 4000 })).length).toBeGreaterThan(0);
    expect(document.querySelector('.stage-bubble')?.textContent).toContain('Duda');
  });

  it('filtra por situação e por tipo', async () => {
    const user = userEvent.setup();
    stubTeam();
    mount('/');
    await screen.findByRole('button', { name: /Abrir a ficha de Duda/ });
    await screen.findByText('50,0%');
    await user.selectOptions(screen.getByLabelText('Tipo de agente'), 'servico');
    expect(screen.queryByRole('button', { name: /Abrir a ficha de Duda/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Abrir a ficha de Otto/ })).toBeTruthy();
    await user.selectOptions(screen.getByLabelText('Tipo de agente'), '');
    await user.click(screen.getByRole('button', { name: 'Com erro' }));
    expect(screen.getByRole('button', { name: /Abrir a ficha de Duda/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Abrir a ficha de Íris/ })).toBeNull();
  });

  it('a ficha mostra modelo, key mascarada e prompt, e o interruptor desliga', async () => {
    const user = userEvent.setup();
    const posts = stubTeam();
    mount('/');
    await user.click(await screen.findByRole('button', { name: /Abrir a ficha de Duda/ }));
    const sheet = screen.getByRole('dialog');
    await user.click(within(sheet).getByRole('tab', { name: 'Configuração' }));
    expect(within(sheet).getByText('····a91F')).toBeTruthy();
    expect(within(sheet).getAllByText('src/agentes/relevancia.py').length).toBeGreaterThan(0);
    await user.selectOptions(within(sheet).getByRole('combobox'), 'gemini-3.8-flash');
    expect(posts.at(-1)).toEqual(['relevancia', { modelo: 'gemini-3.8-flash' }]);
    await user.click(within(sheet).getByRole('tab', { name: 'System prompt' }));
    expect(within(sheet).getByText('PROMPT DE DUDA')).toBeTruthy();
    await user.click(within(sheet).getByRole('switch'));
    expect(posts.at(-1)).toEqual(['relevancia', { ligado: false }]);
    expect(await within(sheet).findByText('Desligado')).toBeTruthy();
  });

  it('desligar um agente essencial pede confirmação antes', async () => {
    const user = userEvent.setup();
    const posts = stubTeam();
    mount('/');
    await user.click(await screen.findByRole('button', { name: /Abrir a ficha de Lia/ }));
    const sheet = screen.getByRole('dialog');
    await user.click(within(sheet).getByRole('switch'));
    expect(posts).toEqual([]);
    expect(within(sheet).getByText('Lia é essencial pra conversa.')).toBeTruthy();
    await user.click(within(sheet).getByRole('button', { name: 'Desligar mesmo assim' }));
    expect(posts).toEqual([['entendimento', { ligado: false }]]);
  });

  it('abre a linha do tempo de uma conversa: mensagem, entendimento, código chamando o iFood, resposta', async () => {
    const user = userEvent.setup();
    stubTeam({ conversa: true });
    mount('/');
    await user.selectOptions(await screen.findByLabelText('Conversa'), 'WA-AAA111-001');
    await screen.findByText('ação: comprar');
    const lanes = [...document.querySelectorAll('.agent-timeline li .lane')].map(l => l.textContent);
    expect(lanes).toEqual(['Pessoa', 'IA', 'Código → iFood', 'IA', 'Regra', 'Bot']);
  });

  it('clicar num agente do palco mostra as ações dele, e a ficha fica a um toque', async () => {
    const user = userEvent.setup();
    stubTeam();
    mount('/');
    await screen.findAllByText('Fiquei com 3 ofertas', { exact: false }, { timeout: 4000 });
    await user.click(screen.getByRole('button', { name: 'Ver as ações de Duda' }));
    const peek = screen.getByRole('dialog', { name: 'Detalhes do personagem' });
    expect(within(peek).getByText('Fiquei com 3 ofertas')).toBeTruthy();
    expect(within(peek).getByText('2,6 s')).toBeTruthy();
    await user.click(within(peek).getByRole('button', { name: 'Abrir a ficha completa' }));
    expect(within(screen.getByRole('dialog', { name: /Duda/ })).getByRole('tab', { name: 'Configuração' })).toBeTruthy();
  });

  it('o iFood do palco resume o MCP, e a faixa mostra as tools mais pedidas', async () => {
    const user = userEvent.setup();
    stubTeam();
    mount('/');
    expect(await screen.findByText('Pedidos ao iFood (MCP)')).toBeTruthy();
    const strip = await screen.findByText('O que o Maestro mais pede ao iFood');
    expect(within(strip.closest('.mcp-strip')).getByText('searchOffers')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Ver o uso do MCP do iFood' }));
    const peek = screen.getByRole('dialog', { name: 'Detalhes do personagem' });
    expect(within(peek).getByText('33,3% erro')).toBeTruthy();
    expect(within(peek).getByRole('link', { name: 'Ver o uso do MCP completo' })).toBeTruthy();
  });
});

