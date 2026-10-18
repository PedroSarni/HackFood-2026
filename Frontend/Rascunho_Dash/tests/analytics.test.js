import { describe, expect, it } from 'vitest';
import { csvExport, filterSessions, isSale, metrics, setReferenceDate } from '../data.js';
import { createSeed, FIXTURE_DATE } from './fixtures.js';

setReferenceDate(FIXTURE_DATE);

describe('Métricas compartilhadas e integridade da base de teste', () => {

  it('aplica o mesmo recorte aos cards, ao funil e às conversas', () => {
    const rows = filterSessions(createSeed(), { period: '7', city: 'Campinas', restaurant: 'Burger da Vila' });
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every(s => s.city === 'Campinas' && s.restaurant === 'Burger da Vila')).toBe(true);
    const data = metrics(rows);
    expect(data.total).toBe(rows.length);
    expect(data.stages[0].count).toBe(rows.length);
    expect(data.stages[8].count).toBe(data.orders);
    expect(data.gmv).toBe(rows.filter(isSale).reduce((sum, s) => sum + s.amountCents, 0));
  });

  it('usa períodos separados e ignora filtros avançados no modo básico', () => {
    const seed = createSeed();
    const filters = { period: '30', city: 'Campinas' };
    const current = filterSessions(seed, filters, false);
    const previous = filterSessions(seed, filters, false, true);
    expect(current.length).toBe(180);
    expect(previous.length).toBe(180);
    expect(current.some(s => s.city === 'São Paulo')).toBe(true);
    const ids = new Set(current.map(s => s.id));
    expect(previous.some(s => ids.has(s.id))).toBe(false);
  });

  it('mantém o funil decrescente e separa recuperação de abandono atual', () => {
    const data = metrics(createSeed());
    expect(data.stages.every((s, i, stages) => !i || s.count <= stages[i - 1].count)).toBe(true);
    expect(data.recovery).toBe(data.recovered / (data.recovered + data.abandoned) * 100);
    for (const session of createSeed()) {
      expect(session.entries.every(e => !e.stage || e.stage <= session.stage)).toBe(true);
      expect(Date.parse(session.updatedAt)).toBe(Math.max(...session.entries.map(e => Date.parse(e.at))));
      const abandoned = session.entries.find(e => e.type === 'cart_abandoned');
      if (abandoned) {
        const cart = session.entries.find(e => e.type === 'cart_created');
        expect(Date.parse(abandoned.at) - Date.parse(cart.at)).toBeGreaterThanOrEqual(30 * 60000);
      }
    }
  });

  it('trata recortes vazios sem NaN ou divisão por zero', () => {
    const data = metrics([]);
    expect(data.conversion).toBe(0);
    expect(data.recovery).toBe(0);
    expect(data.ticket).toBe(0);
    expect(data.stages.every(s => s.count === 0)).toBe(true);
  });


  it('identifica dados simulados no CSV, mascara cliente e neutraliza fórmulas', () => {
    const session = { ...createSeed().find(s => s.status === 'abandoned'), restaurant: '=SUM(A1:A2)' };
    const csv = csvExport([session, { ...session, demo: false }]);
    expect(csv).toContain('Simulado');
    expect(csv).toContain('Bot WhatsApp');
    expect(csv).toContain("'=SUM(A1:A2)");
    expect(csv).toContain(session.clientId);
    expect(csv).not.toContain(session.name);
    expect(csv).toContain('"0.00"');
  });
});
