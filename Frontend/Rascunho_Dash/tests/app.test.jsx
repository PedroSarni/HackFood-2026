import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../app.jsx';

const mount = (path = '/') => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe('Divulgação progressiva e navegação', () => {
  it('abre básico, revela detalhes no mesmo funil e preserva modo ao navegar', async () => {
    const user = userEvent.setup(); mount('/conversao');
    expect(screen.getByRole('switch', { name: 'Modo avançado' }).checked).toBe(false);
    expect(screen.getAllByRole('button', { name: /Ver conversas/ }).length).toBe(3);
    expect(screen.queryByText('Por que os clientes desistem?')).toBeNull();
    expect(document.querySelectorAll('.kpi').length).toBe(3);
    await user.click(screen.getByRole('switch', { name: 'Modo avançado' }));
    expect(screen.getAllByRole('button', { name: /Ver conversas/ }).length).toBe(10);
    expect(screen.getByText('Por que os clientes desistem?')).toBeTruthy();
    expect(screen.getByLabelText('Restaurante')).toBeTruthy();
    await user.click(screen.getByRole('link', { name: /Conversas/ }));
    expect(screen.queryByText('A jornada completa de compra')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Todas as conversas' })).toBeTruthy();
    expect(localStorage.getItem('hackfood-mode')).toBe('advanced');
    await user.click(screen.getByRole('switch', { name: 'Modo avançado' }));
    expect(screen.queryByLabelText('Restaurante')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Financeiro' })).toBeNull();
  });

  it('restaura modo avançado e retorna à visão geral ao simplificar módulo exclusivo', async () => {
    localStorage.setItem('hackfood-mode', 'advanced');
    const user = userEvent.setup(); mount('/financeiro');
    expect(screen.getByRole('heading', { name: 'Composição financeira' })).toBeTruthy();
    await user.click(screen.getByRole('switch', { name: 'Modo avançado' }));
    expect(screen.getByRole('heading', { name: 'Evolução das vendas' })).toBeTruthy();
    expect(localStorage.getItem('hackfood-mode')).toBe('basic');
  });

  it('filtra por etapa sem empilhar as páginas', async () => {
    const user = userEvent.setup(); mount('/conversao');
    await user.click(screen.getByRole('button', { name: /Pedido confirmado:.*Ver conversas/ }));
    expect(screen.getByRole('button', { name: /Alcançou: Pedido confirmado/ })).toBeTruthy();
    expect(screen.queryByText('Da conversa ao pedido')).toBeNull();
    const rows = document.querySelectorAll('tbody tr');
    expect(rows.length).toBeGreaterThan(0);
    expect([...rows].every(r => /Concluída|Recuperada/.test(r.textContent))).toBe(true);
  });
});

describe('Conversas e fonte dos dados', () => {
  it('abre drawer, exibe eventos e mantém pesquisa/status/página ao fechar', async () => {
    const user = userEvent.setup(); mount('/conversas');
    await user.type(screen.getByRole('textbox', { name: 'Buscar cliente ou conversa' }), 'Marina');
    await user.selectOptions(screen.getByLabelText('Status da conversa'), 'completed');
    const before = document.querySelector('tbody').textContent;
    await user.click(screen.getAllByRole('button', { name: 'Abrir conversa de Marina Costa' })[0]);
    const drawer = screen.getByRole('dialog');
    expect(within(drawer).getByText(/Conversa simulada/)).toBeTruthy();
    expect(within(drawer).getAllByText('HackFood · assistente').length).toBeGreaterThan(0);
    await user.click(within(drawer).getByRole('tab', { name: 'Eventos e análise' }));
    expect(within(drawer).getByText('Esta conversa virou uma compra')).toBeTruthy();
    expect(within(drawer).getByText('order_confirmed')).toBeTruthy();
    await user.click(within(drawer).getByRole('button', { name: 'Fechar conversa' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('textbox', { name: 'Buscar cliente ou conversa' }).value).toBe('Marina');
    expect(document.querySelector('tbody').textContent).toBe(before);
  });

  it('pode fechar com Escape e mostra estado vazio para pesquisa sem resultados', async () => {
    const user = userEvent.setup(); mount('/');
    await user.click(screen.getAllByRole('button', { name: /Abrir conversa de/ })[0]);
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.click(screen.getByRole('link', { name: /Conversas/ }));
    await user.type(screen.getByRole('textbox', { name: 'Buscar cliente ou conversa' }), 'cliente inexistente');
    expect(screen.getByText('Nenhum resultado neste recorte')).toBeTruthy();
    expect(document.querySelector('tbody')).toBeNull();
  });

  it('cartão de demonstração troca a fonte pra Demonstração', async () => {
    const user = userEvent.setup(); mount('/');
    expect(screen.getByLabelText('Fonte dos dados').value).toBe('real');
    expect(screen.queryByRole('button', { name: 'Simular compra' })).toBeNull();
    await user.click(screen.getByRole('button', { name: /Explorar demonstração/ }));
    expect(screen.getByLabelText('Fonte dos dados').value).toBe('demo');
    expect([...screen.getByLabelText('Fonte dos dados').options].map(o => o.value)).toEqual(['real', 'demo']);
  });

  it('aplica filtros globais e paginação sem alterar a fonte', async () => {
    localStorage.setItem('hackfood-mode', 'advanced');
    const user = userEvent.setup(); mount('/conversas');
    await user.selectOptions(screen.getByLabelText('Restaurante'), 'Burger da Vila');
    expect([...document.querySelectorAll('tbody tr')].every(r => r.textContent.includes('Burger da Vila'))).toBe(true);
    const first = document.querySelector('tbody tr').textContent;
    await user.click(screen.getByRole('button', { name: 'Próxima página' }));
    expect(document.querySelector('tbody tr').textContent).not.toBe(first);
    await user.selectOptions(screen.getByLabelText('Período'), '1');
    expect(screen.getByText(/Página 1 de/)).toBeTruthy();
  });
});
