import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RoutinesPanel, ago } from '../rotinas.jsx';
import { sayFor } from '../equipe.jsx';
import { NOW, rotinas } from './rotinas-fixture.js';

function stub(body = rotinas()) {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn(async url => { calls.push(url); return { ok: true, json: async () => body }; }));
  return calls;
}
const card = name => screen.getByRole('article', { name: new RegExp(`^${name}:`) });

afterEach(() => vi.unstubAllGlobals());

describe('O que o Maestro faz sozinho', () => {
  it('mostra cada rotina com os disparos, o que a pessoa fez depois e a passada do cron', async () => {
    const calls = stub();
    render(<RoutinesPanel source="real" period="30" now={NOW} />);
    expect(await screen.findByRole('heading', { name: 'O que o Maestro faz sozinho' })).toBeTruthy();
    expect(calls[0]).toBe('/api/rotinas?fonte=real&dias=30');
    const cutucada = card('Cutucada');
    expect(within(cutucada).getByText('8')).toBeTruthy();
    expect(within(cutucada).getByText('62,5%')).toBeTruthy();
    expect(within(cutucada).getByText(/voltaram a falar/)).toBeTruthy();
    expect(within(cutucada).getByText('Último disparo há 2 min')).toBeTruthy();
    const lembrete = card('Lembrete de recompra');
    expect(within(lembrete).getByText(/virou pedido/)).toBeTruthy();
    expect(within(lembrete).getByText(/na volta/)).toBeTruthy();
    expect(within(lembrete).getByText('Cron passou há 4 min · a cada 15 min')).toBeTruthy();
    expect(within(lembrete).getByText('8 lembretes ligados de 6 pessoas')).toBeTruthy();
    expect(within(lembrete).getByText(/próximo vence em 2 dias/)).toBeTruthy();
    expect(within(lembrete).getByText('3 esperando a pessoa voltar (janela de 24h fechada)')).toBeTruthy();
    expect(within(card('Rastreio do pedido')).getByText('Não disparou no período')).toBeTruthy();
    expect(screen.getByText(/a vitrine de boas-vindas apareceu 12 vezes/)).toBeTruthy();
  });

  it('cada disparo da lista abre a conversa', async () => {
    stub();
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<RoutinesPanel source="demo" period="7" now={NOW} onOpen={onOpen} />);
    await user.click(await screen.findByRole('button', { name: 'Dona Cida' }));
    expect(onOpen).toHaveBeenCalledWith('WA-AAA111-001');
    expect(screen.getAllByText('esperando').length).toBeGreaterThan(0);
  });

  it('passo ao vivo de uma rotina acende o cartão dela na hora', async () => {
    stub();
    render(<RoutinesPanel source="real" period="30" now={NOW} step={{ tipo: 'saida', rotina: 'lembrete', key: 'p1' }} />);
    await screen.findByRole('heading', { name: 'O que o Maestro faz sozinho' });
    expect(card('Lembrete de recompra').className).toContain('hot');
    expect(card('Cutucada').className).not.toContain('hot');
    expect(screen.getByRole('status').textContent).toContain('Lembrete de recompra agora');
  });

  it('servidor de antes da seção: ela some em vez de mostrar zeros', async () => {
    stub({ fonte: 'real', estado: 'pronto' });
    render(<RoutinesPanel source="real" period="30" now={NOW} />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole('heading', { name: 'O que o Maestro faz sozinho' })).toBeNull();
  });

  it('o Maestro do palco conta qual rotina disparou', () => {
    expect(sayFor({ tipo: 'saida', rotina: 'cutucada' }, {})).toEqual({ who: 'Maestro', text: '👋 Cutuquei quem sumiu no meio da conversa' });
    expect(sayFor({ tipo: 'saida', formato: 'Texto' }, {}).text).toBe('Respondeu (texto)');
    expect(ago(new Date(NOW - 5000).toISOString(), NOW)).toBe('agora');
    expect(ago(new Date(NOW + 3 * 3600000).toISOString(), NOW)).toBe('em 3 h');
  });
});
