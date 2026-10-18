import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../app.jsx';
import { downloadAnalyticsPdf } from '../report-download.js';
import { filterSessions } from '../data.js';
import { createSeed, FIXTURE_DATE } from './fixtures.js';

vi.mock('../report-download.js', () => ({ downloadAnalyticsPdf: vi.fn() }));
const mount = (path = '/dinheiro') => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
beforeEach(() => vi.clearAllMocks());

describe('Exportação de relatórios na interface', () => {
  it('oferece PDF e CSV no básico e usa o período selecionado', async () => {
    downloadAnalyticsPdf.mockResolvedValue(undefined);
    const user = userEvent.setup(); mount();
    await user.selectOptions(screen.getByLabelText('Período'), '7');
    await user.click(screen.getByText('Exportar', { selector: 'summary span' }));
    expect(screen.getByRole('button', { name: /Planilha CSV/ })).toBeTruthy();
    await user.click(screen.getByRole('button', { name: /Relatório PDF/ }));
    await waitFor(() => expect(downloadAnalyticsPdf).toHaveBeenCalledTimes(1));
    const request = downloadAnalyticsPdf.mock.calls[0][0];
    expect(request.filters.period).toBe('7');
    expect(request.advanced).toBe(false);
    expect(request.rows.length).toBe(39);
    expect(request.previous).toEqual(filterSessions(createSeed(), request.filters, false, true));
    expect(request.referenceDate).toBe(FIXTURE_DATE);
    expect(screen.getByRole('status').textContent).toContain('PDF gerado');
    expect(document.querySelector('.export-dropdown').open).toBe(false);
  });

  it('leva o mesmo filtro de restaurante ao PDF na página de Relatórios', async () => {
    localStorage.setItem('aifood-mode', 'advanced');
    downloadAnalyticsPdf.mockResolvedValue(undefined);
    const user = userEvent.setup(); mount('/relatorios');
    await user.selectOptions(screen.getByLabelText('Restaurante'), 'Sushi Nori');
    await user.click(screen.getByRole('button', { name: 'Baixar relatório PDF' }));
    await waitFor(() => expect(downloadAnalyticsPdf).toHaveBeenCalledTimes(1));
    const request = downloadAnalyticsPdf.mock.calls[0][0];
    expect(request.advanced).toBe(true);
    expect(request.rows.length).toBeGreaterThan(0);
    expect(request.rows.every(s => s.restaurant === 'Sushi Nori')).toBe(true);
    expect(request.previous.every(s => s.restaurant === 'Sushi Nori')).toBe(true);
    expect(screen.getByRole('button', { name: 'Exportar CSV' })).toBeTruthy();
  });

  it('envia a fonte selecionada para identificar corretamente o relatório', async () => {
    downloadAnalyticsPdf.mockResolvedValue(undefined);
    const user = userEvent.setup(); mount();
    await user.selectOptions(screen.getByLabelText('Fonte dos dados'), 'demo');
    await user.click(screen.getByText('Exportar', { selector: 'summary span' }));
    await user.click(screen.getByRole('button', { name: /Relatório PDF/ }));
    await waitFor(() => expect(downloadAnalyticsPdf).toHaveBeenCalledTimes(1));
    expect(downloadAnalyticsPdf.mock.calls[0][0].source).toBe('demo');
  });

  it('trata falhas e permite uma nova tentativa sem perder os filtros', async () => {
    localStorage.setItem('aifood-mode', 'advanced');
    downloadAnalyticsPdf.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined);
    const user = userEvent.setup(); mount('/relatorios');
    await user.selectOptions(screen.getByLabelText('Cidade'), 'Campinas');
    await user.click(screen.getByRole('button', { name: 'Baixar relatório PDF' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Não foi possível gerar o PDF'));
    expect(screen.getByLabelText('Cidade').value).toBe('Campinas');
    await user.click(screen.getByRole('button', { name: 'Baixar relatório PDF' }));
    await waitFor(() => expect(downloadAnalyticsPdf).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('status').textContent).toContain('PDF gerado');
  });

  it('evita exportações duplicadas enquanto o documento está sendo gerado', async () => {
    localStorage.setItem('aifood-mode', 'advanced');
    let resolve;
    downloadAnalyticsPdf.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const user = userEvent.setup(); mount('/relatorios');
    await user.click(screen.getByRole('button', { name: 'Baixar relatório PDF' }));
    expect(screen.getByRole('button', { name: 'Gerando PDF...' }).disabled).toBe(true);
    await user.click(screen.getByRole('button', { name: 'Gerando PDF...' }));
    expect(downloadAnalyticsPdf).toHaveBeenCalledTimes(1);
    resolve();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Baixar relatório PDF' }).disabled).toBe(false));
  });
});
