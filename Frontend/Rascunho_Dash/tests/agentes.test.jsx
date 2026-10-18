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

describe('Agentes', () => {
  it('mostra a arquitetura, o uso por agente e as regras sem IA à parte', async () => {
    const calls = stubFetch(() => agentes());
    mount('/agentes');
    expect(await screen.findByRole('heading', { name: 'Uso por agente' })).toBeTruthy();
    expect(calls[0]).toBe('/api/agentes?fonte=real&dias=30');
    expect(screen.getByText('Orquestrador')).toBeTruthy();
    expect(screen.getByText(/não conversam entre si/)).toBeTruthy();
    const row = screen.getByRole('cell', { name: 'Relevância e sugestão' }).closest('tr');
    expect(within(row).getByText('66,7%')).toBeTruthy();
    expect(within(row).getByText('4,0 s')).toBeTruthy();
    expect(within(row).getByText('gemini-3.1-flash-lite (1)')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Regras sem IA' })).toBeTruthy();
    expect(within(screen.getByText('Follow-up').closest('tr')).getByText('2')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Linha do tempo da conversa' })).toBeNull();
  });

  it('abre a linha do tempo da conversa: mensagem, entendimento, código chamando o iFood, resposta', async () => {
    const user = userEvent.setup();
    const calls = stubFetch(url => agentes(url.searchParams.get('conversa')));
    mount('/agentes');
    await user.selectOptions(await screen.findByLabelText('Conversa'), 'WA-AAA111-001');
    expect(await screen.findByRole('heading', { name: 'Linha do tempo da conversa' })).toBeTruthy();
    expect(calls.at(-1)).toBe('/api/agentes?fonte=real&dias=30&conversa=WA-AAA111-001');
    const lanes = [...document.querySelectorAll('.agent-timeline li .lane')].map(l => l.textContent);
    expect(lanes).toEqual(['Pessoa', 'IA', 'Código → iFood', 'IA', 'Regra', 'Bot']);
    const timeline = document.querySelector('.agent-timeline');
    expect(within(timeline).getByText('ação: comprar')).toBeTruthy();
    expect(within(timeline).getByText('reserva')).toBeTruthy();
    expect(within(timeline).getByText('sem IA')).toBeTruthy();
  });
});
