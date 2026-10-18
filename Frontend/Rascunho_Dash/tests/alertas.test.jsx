import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AlertBanner, AlertBell } from '../alertas.jsx';

const semCredito = { id: 'a1', tipo: 'claude_sem_credito', nivel: 'erro', titulo: 'Acabaram os créditos do Claude',
  detalhe: 'claude-sonnet-5-5 HTTP 400 invalid_request_error: Your credit balance is too low', quando: 1760760000, ultima: 1760760600, vezes: 3, lida: false };

describe('Central de notificações', () => {
  it('o sino conta as não lidas, abre a lista e marca como lidas', () => {
    const readAll = vi.fn();
    render(<AlertBell alerts={{ alertas: [semCredito], naoLidas: 1, readAll }} />);
    fireEvent.click(screen.getByRole('button', { name: '1 notificações não lidas' }));
    expect(screen.getByText('Acabaram os créditos do Claude')).toBeTruthy();
    expect(screen.getByText(/seguiu respondendo pelo Gemini/)).toBeTruthy();
    expect(screen.getByText(/· 3x/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Marcar como lidas/ }));
    expect(readAll).toHaveBeenCalled();
  });

  it('a faixa só aparece com erro não lido', () => {
    const { container, rerender } = render(<AlertBanner alerts={{ alertas: [semCredito], naoLidas: 1, readAll: () => {} }} />);
    expect(screen.getByRole('alert').textContent).toMatch(/Acabaram os créditos do Claude/);
    rerender(<AlertBanner alerts={{ alertas: [{ ...semCredito, lida: true }], naoLidas: 0, readAll: () => {} }} />);
    expect(container.textContent).toBe('');
  });
});
