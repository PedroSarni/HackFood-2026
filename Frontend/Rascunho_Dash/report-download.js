import { brandImages } from './brand.js';
import { REFERENCE_DATE } from './data.js';

// O gerador e suas dependências só são carregados quando o PDF é solicitado.
export async function downloadAnalyticsPdf(options) {
  const referenceDate = options.referenceDate || REFERENCE_DATE;
  const [{ createAnalyticsPdf }, response] = await Promise.all([
    import('./pdf-report.js'), fetch(brandImages.smile),
  ]);
  if (!response.ok) throw new Error('Não foi possível carregar a imagem do relatório.');
  const logo = new Uint8Array(await response.arrayBuffer());
  const report = createAnalyticsPdf({ ...options, referenceDate, logo });
  await report.save(`hackfood-relatorio-${referenceDate}.pdf`, { returnPromise: true });
}

// Os insights da Sofia (insights.jsx), do mesmo jeito: o jsPDF só vem quando alguém toca em "Baixar PDF".
export async function downloadInsightsPdf(options) {
  const [{ createInsightsPdf }, response] = await Promise.all([
    import('./insights-pdf.js'), fetch(brandImages.smile),
  ]);
  if (!response.ok) throw new Error('Não foi possível carregar a imagem do relatório.');
  const logo = new Uint8Array(await response.arrayBuffer());
  const doc = createInsightsPdf({ ...options, logo });
  const dia = new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' });   // 2026-10-18
  await doc.save(`hackfood-insights-${options.page}-${dia}.pdf`, { returnPromise: true });
}
