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
