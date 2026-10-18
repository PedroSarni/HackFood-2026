import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../app.jsx';

const mount = (path = '/') => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe('Navegação enxuta e mais análises', () => {
  it('menu começa pelo time, depois MCP e dinheiro; mais análises revela o resto', async () => {
    const user = userEvent.setup(); mount('/dinheiro');
    const links = () => [...document.querySelectorAll('nav .nav-link')].map(a => a.textContent.replace(/\d+$/, ''));
    expect(links()).toEqual(['Agentes', 'Uso do MCP', 'Dinheiro', 'Conversas']);
    expect(screen.getByRole('heading', { name: 'Vendas por dia' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Para onde foi o dinheiro' })).toBeTruthy();
    await user.click(screen.getByRole('switch', { name: 'Mais análises' }));
    expect(links()).toEqual(['Agentes', 'Uso do MCP', 'Dinheiro', 'Conversas', 'Conversão', 'Clientes', 'Mercado', 'Relatórios']);
    expect(screen.getByLabelText('Restaurante')).toBeTruthy();
    await user.click(screen.getByRole('link', { name: 'Conversão' }));
    expect(screen.getAllByRole('button', { name: /Ver conversas/ }).length).toBe(10);
    expect(screen.getByText('Por que os clientes desistem?')).toBeTruthy();
    expect(localStorage.getItem('aifood-mode')).toBe('advanced');
    await user.click(screen.getByRole('switch', { name: 'Mais análises' }));
    expect(screen.getByRole('heading', { name: 'Agentes.' })).toBeTruthy();   // saiu da página que só existe em mais análises
    expect(localStorage.getItem('aifood-mode')).toBe('basic');
  });

  it('endereços antigos levam pras telas novas', () => {
    mount('/financeiro');
    expect(screen.getByRole('heading', { name: 'Dinheiro.' })).toBeTruthy();
  });

  it('filtra por etapa sem empilhar as páginas', async () => {
    localStorage.setItem('aifood-mode', 'advanced');
    const user = userEvent.setup(); mount('/conversao');
    await user.click(screen.getByRole('button', { name: /Pedido confirmado:.*Ver conversas/ }));
    expect(screen.getByRole('button', { name: /Alcançou: Pedido confirmado/ })).toBeTruthy();
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
    expect(within(drawer).getAllByText('AiFood · assistente').length).toBeGreaterThan(0);
    await user.click(within(drawer).getByRole('tab', { name: 'Eventos e análise' }));
    expect(within(drawer).getByText('Esta conversa virou uma compra')).toBeTruthy();
    expect(within(drawer).getByText('order_confirmed')).toBeTruthy();
    await user.click(within(drawer).getByRole('button', { name: 'Fechar conversa' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('textbox', { name: 'Buscar cliente ou conversa' }).value).toBe('Marina');
    expect(document.querySelector('tbody').textContent).toBe(before);
  });

  it('pode fechar com Escape e mostra estado vazio para pesquisa sem resultados', async () => {
    const user = userEvent.setup(); mount('/conversas');
    await user.click(screen.getAllByRole('button', { name: /Abrir conversa de/ })[0]);
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.type(screen.getByRole('textbox', { name: 'Buscar cliente ou conversa' }), 'cliente inexistente');
    expect(screen.getByText('Nenhum resultado neste recorte')).toBeTruthy();
    expect(document.querySelector('tbody')).toBeNull();
  });

  it('a fonte dos dados só tem real e demonstração', async () => {
    const user = userEvent.setup(); mount('/dinheiro');
    expect(screen.getByLabelText('Fonte dos dados').value).toBe('real');
    await user.selectOptions(screen.getByLabelText('Fonte dos dados'), 'demo');
    expect([...screen.getByLabelText('Fonte dos dados').options].map(o => o.value)).toEqual(['real', 'demo']);
  });

  it('aplica filtros globais e paginação sem alterar a fonte', async () => {
    localStorage.setItem('aifood-mode', 'advanced');
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
