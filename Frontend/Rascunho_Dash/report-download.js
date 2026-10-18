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
