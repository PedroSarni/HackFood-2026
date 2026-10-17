import { describe, expect, it } from 'vitest';
import { advancePitch, createPitchSession, createSeed, csvExport, filterSessions, isSale, metrics, readSessions, STORAGE_KEY } from '../data.js';

describe('Métricas compartilhadas e integridade da demonstração', () => {
  it('não confunde carrinho com GMV e registra uma única compra ao finalizar', () => {
    let session = createPitchSession();
    for (let i = 0; i < 4; i++) session = advancePitch(session);
    expect(metrics([session]).gmv).toBe(0);
    expect(metrics([session]).orders).toBe(0);
    expect(session.amountCents).toBe(4690);
    session = advancePitch(session);
    expect(metrics([session])).toMatchObject({ gmv: 4690, orders: 1, conversion: 100, ticket: 4690 });
    expect(advancePitch(session)).toBe(session);
  });

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

  it('persiste somente a base demonstrativa e recupera armazenamento inválido', () => {
    localStorage.setItem(STORAGE_KEY, 'arquivo inválido');
    expect(readSessions().length).toBe(360);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([{ ...createPitchSession(), demo: false }, createPitchSession()]));
    expect(readSessions().filter(s => s.id.startsWith('PITCH-')).length).toBe(1);
    expect(readSessions().every(s => s.demo === true)).toBe(true);
  });

  it('identifica dados simulados no CSV, mascara cliente e neutraliza fórmulas', () => {
    const session = { ...advancePitch(createPitchSession()), restaurant: '=SUM(A1:A2)' };
    const csv = csvExport([session]);
    expect(csv).toContain('Simulado');
    expect(csv).toContain("'=SUM(A1:A2)");
    expect(csv).toContain('CLI-PITCH');
    expect(csv).not.toContain(session.name);
    expect(csv).toContain('"0.00"');
  });
});
