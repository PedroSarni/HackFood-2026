// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createAnalyticsPdf, reportContext } from '../pdf-report.js';
import { filterSessions, setReferenceDate, metrics, money, percent, groupBy } from '../data.js';
import { createSeed, FIXTURE_DATE } from './fixtures.js';

setReferenceDate(FIXTURE_DATE);

const logo = new Uint8Array(readFileSync(new URL('../images/icone-ifood-sorriso-quadrado-vermelho-png.png', import.meta.url)));
const content = doc => doc.internal.pages.flat().join('\n');
const plainMoney = cents => money(cents).replace(/[\u00a0\u202f]/g, ' ');

describe('Relatórios PDF', () => {
  it('identifica apenas os filtros efetivos, inclusive no modo básico', () => {
    const filters = { period: '7', city: 'Campinas', restaurant: 'Burger da Vila', origin: 'Follow-up' };
    expect(reportContext(filters, false)).toEqual({ period: '11/10/2026 a 17/10/2026', filters: 'Todas as cidades | Todos os restaurantes | Todas as origens' });
    expect(reportContext(filters, true).filters).toContain('Campinas | Burger da Vila | Origem: Follow-up');
  });

  it('gera PDF A4 com indicadores e sem registros individuais', () => {
    const filters = { period: '30' };
    const rows = filterSessions(createSeed(), filters);
    const doc = createAnalyticsPdf({ rows, filters, logo });
    const bytes = new Uint8Array(doc.output('arraybuffer'));
    expect(Buffer.from(bytes.slice(0, 5)).toString()).toBe('%PDF-');
    expect(doc.getNumberOfPages()).toBeGreaterThan(3);
    expect(Math.round(doc.internal.pageSize.getWidth())).toBe(210);
    expect(Math.round(doc.internal.pageSize.getHeight())).toBe(297);
    expect(rows.length).toBe(180);
    const text = content(doc);
    for (const section of ['Visão geral', 'Conversão e resultados', 'Follow-ups e clientes', 'Vendas por cidade', 'Restaurantes em destaque', 'Financeiro e inteligência']) expect(text).toContain(section);
    expect(text).not.toContain('Conversas do período');
    for (const row of rows) {
      expect(text).not.toContain(row.id);
      expect(text).not.toContain(row.clientId);
      expect(text).not.toContain(row.name);
      expect(text).not.toContain(row.phone);
    }
  });

  it('exporta recorte vazio sem falhar ou produzir página de tabela em branco', () => {
    const doc = createAnalyticsPdf({ rows: [], filters: { period: '1' }, logo });
    expect(doc.getNumberOfPages()).toBe(6);
    expect(doc.output('arraybuffer').byteLength).toBeGreaterThan(1000);
    expect(content(doc)).toContain('Nenhum resultado neste recorte.');
    expect(content(doc)).not.toMatch(/NaN|Infinity/);
  });

  it('usa os mesmos indicadores e rankings do dashboard no recorte filtrado', () => {
    const filters = { period: '7', city: 'Campinas', origin: 'Follow-up' };
    const rows = filterSessions(createSeed(), filters, true);
    const previous = filterSessions(createSeed(), filters, true, true);
    const data = metrics(rows);
    const doc = createAnalyticsPdf({ rows, previous, filters, advanced: true, source: 'demo' });
    const text = content(doc);
    for (const value of [data.gmv, data.ticket, data.recoveredGmv, data.abandonedValue]) expect(text).toContain(plainMoney(value));
    for (const value of [data.conversion, data.recovery, data.repurchase, data.acceptance, data.failureRate]) expect(text).toContain(percent(value));
    for (const stage of data.stages) expect(text).toContain(`${stage.count} | ${percent(stage.count / data.total * 100)}`);
    for (const group of groupBy(rows, 'restaurant')) {
      expect(text).toContain(group.name);
      expect(text).toContain(plainMoney(group.gmv));
      expect(text).toContain(`${group.orders} pedidos | ${percent(group.conversion)}`);
    }
    expect(text).toContain('Campinas | Todos os restaurantes | Origem: Follow-up');
  });

  it('preserva fonte e data da exportação, inclusive com dados reais vazios', () => {
    const filters = { period: '1' };
    const real = content(createAnalyticsPdf({ rows: [], filters, source: 'real', referenceDate: '2026-10-16' }));
    expect(real).toContain('DADOS REAIS');
    expect(real).not.toContain('DADOS SIMULADOS');
    expect(real).toContain('16/10/2026 a 16/10/2026');
    expect(content(createAnalyticsPdf({ rows: [], filters, source: 'demo' }))).toContain('DADOS SIMULADOS');
  });

  it('pagina rankings extensos sem adicionar listas de clientes', () => {
    const base = createSeed()[0];
    const rows = Array.from({ length: 19 }, (_, i) => ({ ...base, restaurant: `Restaurante ${String(i).padStart(2, '0')}` }));
    const doc = createAnalyticsPdf({ rows, filters: { period: '30' } });
    expect(doc.getNumberOfPages()).toBe(8);
    for (const row of rows) expect(content(doc)).toContain(row.restaurant);
    expect(content(doc)).not.toContain(base.clientId);
  });
});
