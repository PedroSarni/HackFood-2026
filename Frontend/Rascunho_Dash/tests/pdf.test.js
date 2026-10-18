// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createAnalyticsPdf, reportContext } from '../pdf-report.js';
import { filterSessions, setReferenceDate } from '../data.js';
import { createSeed, FIXTURE_DATE } from './fixtures.js';

setReferenceDate(FIXTURE_DATE);

const logo = new Uint8Array(readFileSync(new URL('../images/icone-ifood-sorriso-quadrado-vermelho-png.png', import.meta.url)));

describe('Relatórios PDF', () => {
  it('identifica apenas os filtros efetivos, inclusive no modo básico', () => {
    const filters = { period: '7', city: 'Campinas', restaurant: 'Burger da Vila', origin: 'Follow-up' };
    expect(reportContext(filters, false)).toEqual({ period: '11/10/2026 a 17/10/2026', filters: 'Todas as cidades | Todos os restaurantes | Todas as origens' });
    expect(reportContext(filters, true).filters).toContain('Campinas | Burger da Vila | Origem: Follow-up');
  });

  it('gera PDF A4 paginado com a imagem original e todos os dados do recorte', () => {
    const filters = { period: '30' };
    const rows = filterSessions(createSeed(), filters);
    const doc = createAnalyticsPdf({ rows, filters, logo });
    const bytes = new Uint8Array(doc.output('arraybuffer'));
    expect(Buffer.from(bytes.slice(0, 5)).toString()).toBe('%PDF-');
    expect(doc.getNumberOfPages()).toBeGreaterThan(3);
    expect(Math.round(doc.internal.pageSize.getWidth())).toBe(210);
    expect(Math.round(doc.internal.pageSize.getHeight())).toBe(297);
    expect(rows.length).toBe(180);
  });

  it('exporta recorte vazio sem falhar ou produzir página de tabela em branco', () => {
    const doc = createAnalyticsPdf({ rows: [], filters: { period: '1' }, logo });
    expect(doc.getNumberOfPages()).toBe(3);
    expect(doc.output('arraybuffer').byteLength).toBeGreaterThan(1000);
  });
});
