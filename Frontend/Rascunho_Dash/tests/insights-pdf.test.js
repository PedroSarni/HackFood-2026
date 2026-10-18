// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createInsightsPdf } from '../insights-pdf.js';
import { setReferenceDate } from '../data.js';
import { FIXTURE_DATE } from './fixtures.js';

setReferenceDate(FIXTURE_DATE);

const logo = new Uint8Array(readFileSync(new URL('../images/icone-ifood-sorriso-quadrado-vermelho-png.png', import.meta.url)));
const content = doc => doc.internal.pages.flat().join('\n');
const insight = (n, extra = {}) => ({ titulo: `Pagamento derruba o funil ${n}`, time: 'Produto', evidencia: '52 de 140 abandonos no pagamento',
  acao: 'Testar Pix como primeira opcao no bot', impacto: 'alto', prazo: 'esta semana', metrica: 'abandono no pagamento', ...extra });

describe('PDF dos insights da Sofia', () => {
  it('gera A4 com o cabeçalho do relatório, o resumo e um cartão por insight', () => {
    const data = { resumo: 'Muita gente para no pagamento.', modelo: 'gemini-3.8-flash',
      insights: [insight(1), insight(2, { time: 'Growth e CRM', impacto: 'baixo' })] };
    const doc = createInsightsPdf({ page: 'conversao', data, filters: { period: '30' }, source: 'real', teamColors: { Produto: '#7a5af8' }, logo });
    const bytes = new Uint8Array(doc.output('arraybuffer'));
    expect(Buffer.from(bytes.slice(0, 5)).toString()).toBe('%PDF-');
    expect(Math.round(doc.internal.pageSize.getWidth())).toBe(210);
    const texto = content(doc);
    for (const pedaco of ['Insights da Sofia', 'Muita gente para no pagamento.', 'Pagamento derruba o funil 1', 'Growth e CRM',
      'Testar Pix como primeira opcao no bot', 'DADOS REAIS', 'modelo gemini-3.8-flash', 'esta semana']) {
      expect(texto).toContain(pedaco);
    }
  });

  it('quebra a página quando os cartões não cabem e tira emoji que a fonte não tem', () => {
    const longa = 'Uma evidencia bem longa que ocupa varias linhas no cartao do insight. '.repeat(6);
    const data = { insights: Array.from({ length: 8 }, (_, i) => insight(i, { evidencia: longa, titulo: `🚀 Lancar combo ${i}` })) };
    const doc = createInsightsPdf({ page: 'mercado', data, filters: { period: '7' }, source: 'demo', logo });
    expect(doc.getNumberOfPages()).toBeGreaterThan(1);
    const texto = content(doc);
    expect(texto).toContain('Lancar combo 7');
    expect(texto).toContain('DADOS SIMULADOS');
    expect(texto).not.toMatch(/[\uD800-\uDFFF]/);   // o 🚀 saiu
  });
});
