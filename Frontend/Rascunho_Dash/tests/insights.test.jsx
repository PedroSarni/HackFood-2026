import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../app.jsx';

const insights = { resumo: 'Muita gente para no pagamento.', modelo: 'gemini-3.8-flash', segundos: 3.2, insights: [
  { titulo: 'Pagamento derruba o funil', time: 'Produto', evidencia: '52 de 140 abandonos no pagamento', acao: 'Testar Pix como 1ª opção', impacto: 'alto', prazo: 'esta semana', metrica: 'abandono no pagamento' },
  { titulo: 'Lembrete no dia seguinte', time: 'Growth e CRM', evidencia: 'R$ 5.372 em carrinhos parados', acao: 'Mandar lembrete em 24h', impacto: 'médio', prazo: 'este mês', metrica: 'recuperação' },
] };

function stubInsights(resposta = () => ({ ok: true, body: insights })) {
  const posts = [];
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    if (options.method === 'POST') {
      posts.push({ url, body: JSON.parse(options.body) });
      const r = resposta(posts.length);
      return { ok: r.ok, json: async () => r.body };
    }
    throw new Error('offline');
  }));
  return posts;
}
const mount = path => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
afterEach(() => vi.unstubAllGlobals());

describe('Insights com IA', () => {
  it('o botão só aparece em Conversão, Clientes e Mercado', () => {
    localStorage.setItem('hackfood-mode', 'advanced');
    mount('/dinheiro');
    expect(screen.queryByRole('button', { name: /Gerar insights com IA/ })).toBeNull();
  });

  it('varre a página, manda só agregados e mostra os insights por time', async () => {
    localStorage.setItem('hackfood-mode', 'advanced');
    const user = userEvent.setup();
    const posts = stubInsights();
    mount('/conversao');
    await user.click(screen.getByRole('button', { name: 'Gerar insights com IA desta página' }));
    expect(document.querySelector('.ai-overlay')).toBeTruthy();                  // a varredura começou
    expect(screen.getByRole('dialog', { name: 'Insights da IA' }).getAttribute('aria-busy')).toBe('true');
    const card = await screen.findByText('Pagamento derruba o funil', {}, { timeout: 4000 });
    const panel = screen.getByRole('dialog', { name: 'Insights da IA' });
    expect(within(panel).getByText('Produto')).toBeTruthy();
    expect(within(panel).getByText('Testar Pix como 1ª opção')).toBeTruthy();
    expect(within(panel).getByText(/gemini-3.8-flash/)).toBeTruthy();
    expect(card).toBeTruthy();
    const { url, body } = posts[0];
    expect(url).toBe('/api/insights?fonte=real');
    expect(body.pagina).toBe('conversao');
    expect(body.dados.funil.length).toBe(10);
    expect(JSON.stringify(body)).not.toContain('Marina');                       // nome de cliente não sai do navegador
    await user.click(within(panel).getByRole('button', { name: /Gerar de novo/ }));
    expect(posts[1].body.novo).toBe(true);
  });

  it('com a Sofia desligada, avisa e deixa tentar de novo', async () => {
    localStorage.setItem('hackfood-mode', 'advanced');
    const user = userEvent.setup();
    stubInsights(() => ({ ok: false, body: { erro: 'desligado' } }));
    mount('/clientes');
    await user.click(screen.getByRole('button', { name: 'Gerar insights com IA desta página' }));
    expect(await screen.findByText('A Sofia está de folga', {}, { timeout: 4000 })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Tentar de novo/ })).toBeTruthy();
  });

  it('mercado manda cidades e lojas, não clientes', async () => {
    localStorage.setItem('hackfood-mode', 'advanced');
    const user = userEvent.setup();
    const posts = stubInsights();
    mount('/mercado');
    await user.click(screen.getByRole('button', { name: 'Gerar insights com IA desta página' }));
    await screen.findByText('Pagamento derruba o funil', {}, { timeout: 4000 });
    const dados = posts[0].body.dados;
    expect(dados.cidades.length).toBeGreaterThan(0);
    expect(dados.lojasQueMaisVendem[0]).toHaveProperty('loja');
    expect(Object.keys(dados)).not.toContain('clientes');
  });
});
