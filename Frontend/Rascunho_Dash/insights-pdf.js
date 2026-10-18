import { jsPDF } from 'jspdf';
import { COLORS, pdfText, reportContext } from './pdf-report.js';

// O PDF dos insights da Sofia (insights.jsx): o mesmo cabeçalho do relatório (pdf-report.js) e um cartão por
// insight com o time dono, a evidência, a ação, o impacto, o prazo e a métrica. Só o que a tela mostra: os
// insights saem de números agregados, nenhum nome ou telefone de cliente entra aqui.

export const PAGE_LABELS = { conversao: 'Conversão', clientes: 'Clientes', mercado: 'Mercado' };
const IMPACT = { alto: 'Impacto alto', 'médio': 'Impacto médio', baixo: 'Impacto baixo' };
const MARGIN = 16;
const WIDTH = 178;
const BOTTOM = 272;
const TOP = 40;

const rgb = hex => {
  const n = parseInt(String(hex || '#7a5af8').replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
// a fonte do PDF não tem emoji nem aspas curvas: o que o modelo escrever assim vira texto simples
const clean = value => pdfText(value ?? '').replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/…/g, '...')
  .replace(/•/g, '-').replace(/[^\x00-\xFF]/g, '').replace(/ {2,}/g, ' ').trim();

export function createInsightsPdf({ page, data, filters = {}, source, teamColors = {}, generatedAt = new Date(), logo, referenceDate }) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
  const label = PAGE_LABELS[page] || page;
  const sourceLabel = source === 'demo' ? 'Demonstração' : 'Dados reais';
  const context = reportContext(filters, true, referenceDate);
  const generated = generatedAt.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' });
  doc.setProperties({ title: `HackFood Analytics - Insights da Sofia - ${label}`, author: 'HackFood Analytics',
    subject: `Insights por time do iFood - ${sourceLabel}`, keywords: 'HackFood, insights, Sofia' });
  doc.setCreationDate(generatedAt);

  const text = (value, x, y, size = 10, color = COLORS.ink, bold = false, options) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    doc.setTextColor(...color);
    doc.text(Array.isArray(value) ? value.map(clean) : clean(value), x, y, options);
  };
  const wrap = (value, width, size, bold = false) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    return doc.splitTextToSize(clean(value), width);
  };
  const header = () => {
    doc.setFillColor(...COLORS.red);
    doc.rect(0, 0, 210, 3, 'F');
    if (logo) doc.addImage(logo, 'PNG', 16, 12, 13, 13, 'brand-smile');
    text('hackfood', logo ? 33 : 16, 18, 17, COLORS.ink, true);
    text('A N A L Y T I C S', logo ? 33 : 16, 24, 7, COLORS.muted);
    doc.setFillColor(...COLORS.blush);
    doc.roundedRect(151, 14, 43, 8, 2, 2, 'F');
    text(source === 'demo' ? 'DADOS SIMULADOS' : 'DADOS REAIS', 172.5, 19.3, 8, COLORS.red, true, { align: 'center' });
    doc.setDrawColor(...COLORS.line);
    doc.line(16, 31, 194, 31);
  };
  let y;
  const room = height => {   // não cabe no que sobrou da página: página nova com o mesmo cabeçalho
    if (y + height <= BOTTOM) return;
    doc.addPage();
    header();
    y = TOP;
  };

  header();
  text(`Insights da Sofia: ${label}`, MARGIN, 45, 21, COLORS.ink, true);
  text(`Período: ${context.period}`, MARGIN, 54, 10, COLORS.muted);
  text(context.filters, MARGIN, 60, 9, COLORS.muted);
  text(`Emitido em ${generated} | ${data.modelo ? `modelo ${data.modelo}` : 'Analista'} | America/Sao_Paulo`, MARGIN, 66, 8, COLORS.muted);
  // o aviso fica em cima: no fim ele empurrava uma página inteira só pra uma linha
  const aviso = wrap(`${source === 'demo' ? 'Feito com os dados simulados da demonstração.' : `Feito só com os números agregados da página ${label}.`} Os insights são da IA: confira antes de agir.`, WIDTH, 8);
  text(aviso, MARGIN, 71, 8, COLORS.muted);
  y = 71 + aviso.length * 3.6 + 4;
  if (data.resumo) {
    const resumo = wrap(data.resumo, WIDTH - 12, 10);
    const height = resumo.length * 4.6 + 10;
    doc.setFillColor(...COLORS.blush);
    doc.roundedRect(MARGIN, y, WIDTH, height, 2, 2, 'F');
    text(resumo, MARGIN + 6, y + 8, 10, COLORS.ink);
    y += height + 7;
  }

  (data.insights || []).forEach((item, i) => {
    const cor = rgb(teamColors[item.time]);
    const titulo = wrap(`${i + 1}. ${item.titulo}`, WIDTH - 14, 11, true);
    const evidencia = wrap(`Evidência: ${item.evidencia}`, WIDTH - 14, 9);
    const acao = wrap(`Ação: ${item.acao}`, WIDTH - 14, 9);
    // cada linha a partir da anterior (mm até a linha de base); 3 a 5 insights cabem numa página
    const oTitulo = 11.5;
    const oEvidencia = oTitulo + titulo.length * 4.8 + 0.8;
    const oAcao = oEvidencia + evidencia.length * 4.1;
    const oTraco = oAcao + (acao.length - 1) * 4.1 + 3.2;
    const oMetrica = oTraco + 4.3;
    const height = oMetrica + 3.6;
    room(height + 4.5);
    doc.setFillColor(...COLORS.light);
    doc.roundedRect(MARGIN, y, WIDTH, height, 2, 2, 'F');
    doc.setFillColor(...cor);
    doc.rect(MARGIN, y + 3, 1.6, height - 6, 'F');
    text(item.time || 'Time', MARGIN + 7, y + 6, 8, cor, true);
    text(IMPACT[item.impacto] || item.impacto || '', MARGIN + WIDTH - 5, y + 6, 8, item.impacto === 'alto' ? COLORS.red : COLORS.muted,
      true, { align: 'right' });
    text(titulo, MARGIN + 7, y + oTitulo, 11, COLORS.ink, true);
    text(evidencia, MARGIN + 7, y + oEvidencia, 9, COLORS.muted);
    text(acao, MARGIN + 7, y + oAcao, 9, COLORS.ink);
    doc.setDrawColor(...COLORS.line);
    doc.line(MARGIN + 7, y + oTraco, MARGIN + WIDTH - 5, y + oTraco);
    text(`Métrica: ${item.metrica || '-'}   |   Prazo: ${item.prazo || '-'}`, MARGIN + 7, y + oMetrica, 8, COLORS.muted);
    y += height + 4.5;
  });

  const pages = doc.getNumberOfPages();
  for (let n = 1; n <= pages; n++) {
    doc.setPage(n); doc.setDrawColor(...COLORS.line); doc.setLineWidth(.2); doc.line(16, 280, 194, 280);
    text(`HackFood Analytics | Insights da Sofia | ${sourceLabel} | America/Sao_Paulo`, MARGIN, 286, 7, COLORS.muted);
    text(`${n} / ${pages}`, 194, 286, 8, COLORS.muted, false, { align: 'right' });
  }
  return doc;
}
