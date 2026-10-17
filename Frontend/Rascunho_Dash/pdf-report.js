import { jsPDF } from 'jspdf';
import { autoTable } from 'jspdf-autotable';
import { REFERENCE_DATE, STATUSES, dateKey, dateTime, groupBy, isSale, metrics, money, number, percent, ratio } from './data.js';

const COLORS = {
  red: [234, 29, 44], ink: [48, 48, 57], muted: [112, 112, 124],
  line: [231, 231, 236], light: [247, 247, 249], blush: [255, 240, 241],
};
const MARGIN = 16;
const WIDTH = 178;
const pdfText = value => String(value).replace(/[\u00a0\u202f]/g, ' ').replace(/[\u2010-\u2015]/g, '-');

export function reportContext(filters, advanced) {
  const end = new Date(`${REFERENCE_DATE}T12:00:00-03:00`);
  const start = new Date(end.getTime() - (Number(filters.period || 30) - 1) * 86400000);
  const format = d => d.toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  return {
    period: `${format(start)} a ${format(end)}`,
    filters: [
      advanced && filters.city ? filters.city : 'Todas as cidades',
      advanced && filters.restaurant ? filters.restaurant : 'Todos os restaurantes',
      advanced && filters.origin ? `Origem: ${filters.origin}` : 'Todas as origens',
    ].join(' | '),
  };
}

/** Gera o documento a partir do mesmo recorte que alimenta os KPIs do site. */
export function createAnalyticsPdf({ rows, filters, advanced = false, generatedAt = new Date(), logo }) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
  const data = metrics(rows);
  const context = reportContext(filters, advanced);
  const headedPages = new Set();
  const generated = generatedAt.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' });
  const moneyText = value => pdfText(money(value));

  doc.setProperties({ title: 'HackFood Analytics - Relatório do canal WhatsApp', author: 'HackFood Analytics', subject: 'Relatório demonstrativo do canal WhatsApp', keywords: 'HackFood, analytics, demonstração' });
  doc.setCreationDate(generatedAt);

  const text = (value, x, y, size = 10, color = COLORS.ink, bold = false, options) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    doc.setTextColor(...color);
    doc.text(Array.isArray(value) ? value.map(pdfText) : pdfText(value), x, y, options);
  };
  const paragraph = (value, x, y, width = WIDTH, size = 9, color = COLORS.muted) => {
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(pdfText(value), width);
    text(lines, x, y, size, color);
    return y + lines.length * size * .41;
  };
  const header = () => {
    const page = doc.internal.getCurrentPageInfo().pageNumber;
    if (headedPages.has(page)) return;
    headedPages.add(page);
    doc.setFillColor(...COLORS.red);
    doc.rect(0, 0, 210, 3, 'F');
    if (logo) doc.addImage(logo, 'PNG', 16, 12, 13, 13, 'brand-smile');
    text('hackfood', logo ? 33 : 16, 18, 17, COLORS.ink, true);
    text('A N A L Y T I C S', logo ? 33 : 16, 24, 7, COLORS.muted);
    doc.setFillColor(...COLORS.blush);
    doc.roundedRect(151, 14, 43, 8, 2, 2, 'F');
    text('DADOS SIMULADOS', 172.5, 19.3, 8, COLORS.red, true, { align: 'center' });
    doc.setDrawColor(...COLORS.line);
    doc.line(16, 31, 194, 31);
  };
  const newPage = title => {
    doc.addPage();
    header();
    text(title, MARGIN, 43, 18, COLORS.ink, true);
    text(`Período: ${context.period}`, MARGIN, 50, 9, COLORS.muted);
  };
  const table = ({ head, body, startY, columnStyles, fontSize = 9 }) => {
    autoTable(doc, {
      startY, head: [head], body,
      margin: { top: 38, bottom: 22, left: MARGIN, right: MARGIN },
      theme: 'grid', tableWidth: WIDTH,
      styles: { font: 'helvetica', fontSize, textColor: COLORS.ink, lineColor: COLORS.line, lineWidth: .1, cellPadding: 3, overflow: 'linebreak', valign: 'middle' },
      headStyles: { fillColor: COLORS.red, textColor: [255,255,255], fontStyle: 'bold', lineColor: COLORS.red },
      alternateRowStyles: { fillColor: COLORS.light },
      columnStyles, rowPageBreak: 'avoid', showHead: 'everyPage',
      didDrawPage: header,
    });
    return doc.lastAutoTable.finalY;
  };

  header();
  text('Relatório do canal WhatsApp', MARGIN, 45, 21, COLORS.ink, true);
  text(`Período: ${context.period}`, MARGIN, 54, 10, COLORS.muted);
  const filtersEnd = paragraph(context.filters, MARGIN, 62, WIDTH, 9);
  text(`Emitido em ${generated} | America/Sao_Paulo`, MARGIN, filtersEnd + 3, 8, COLORS.muted);
  text(`${number(rows.length)} conversas na amostra`, MARGIN, filtersEnd + 9, 9, COLORS.red, true);

  const cardsTop = Math.max(84, filtersEnd + 16);
  const cards = [
    ['GMV pelo WhatsApp', moneyText(data.gmv)], ['Pedidos concluídos', number(data.orders)],
    ['Ticket médio', moneyText(data.ticket)], ['Taxa de conversão', percent(data.conversion)],
    ['Carrinhos abandonados', number(data.abandoned)], ['Carrinhos recuperados', number(data.recovered)],
  ];
  cards.forEach(([label, value], index) => {
    const x = MARGIN + index % 3 * 61, y = cardsTop + Math.floor(index / 3) * 29;
    doc.setFillColor(...(index === 0 ? COLORS.blush : COLORS.light));
    doc.roundedRect(x, y, 56, 24, 2, 2, 'F');
    text(label, x + 4, y + 7, 8, COLORS.muted);
    text(value, x + 4, y + 17, 16, index === 0 ? COLORS.red : COLORS.ink, true);
  });

  const chartTop = cardsTop + 70;
  text('Evolução das vendas', MARGIN, chartTop, 12, COLORS.ink, true);
  const days = Number(filters.period || 30);
  const last = new Date(`${REFERENCE_DATE}T12:00:00-03:00`);
  const dates = Array.from({ length: days }, (_, index) => new Date(last.getTime() - (days - 1 - index) * 86400000));
  const totals = new Map();
  for (const row of rows.filter(isSale)) {
    const day = dateKey(row.startedAt);
    totals.set(day, (totals.get(day) || 0) + row.amountCents);
  }
  const values = dates.map(date => (totals.get(dateKey(date)) || 0) / 100);
  const max = Math.max(100, Math.ceil(Math.max(...values) / 100) * 100);
  const chartX = 34, chartY = chartTop + 9, chartW = 160, chartH = 32;
  for (let i = 0; i < 3; i++) {
    const y = chartY + i * chartH / 2;
    doc.setDrawColor(...COLORS.line); doc.setLineWidth(.2);
    doc.line(chartX, y, chartX + chartW, y);
    text(`R$ ${number(max * (1 - i / 2))}`, 16, y + 1, 7, COLORS.muted);
  }
  const points = values.map((value, index) => [chartX + (days === 1 ? .5 : index / (days - 1)) * chartW, chartY + chartH * (1 - value / max)]);
  doc.setDrawColor(...COLORS.red); doc.setFillColor(...COLORS.red); doc.setLineWidth(.6);
  points.forEach(([x,y], index) => { if (index) doc.line(...points[index - 1], x, y); else if (days === 1) doc.circle(x,y,1.2,'F'); });
  const dateLabel = date => date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: 'America/Sao_Paulo' });
  text(dateLabel(dates[0]), chartX, chartY + chartH + 6, 7, COLORS.muted);
  if (days > 1) text(dateLabel(last), 194, chartY + chartH + 6, 7, COLORS.muted, false, { align: 'right' });

  const funnelY = chartY + chartH + 19;
  text('Da conversa ao pedido', MARGIN, funnelY, 12, COLORS.ink, true);
  [0,4,8].forEach((index, position) => {
    const stage = data.stages[index], y = funnelY + 9 + position * 14;
    text(stage.label, MARGIN, y, 9);
    text(`${number(stage.count)} | ${percent(ratio(stage.count, data.total))}`, 194, y, 9, COLORS.muted, false, { align: 'right' });
    doc.setFillColor(...COLORS.blush); doc.roundedRect(MARGIN, y + 3, WIDTH, 3, 1, 1, 'F');
    if (stage.count) { doc.setFillColor(...COLORS.red); doc.rect(MARGIN, y + 3, WIDTH * stage.count / data.total, 3, 'F'); }
  });

  newPage('Resultados e critérios');
  text('Desempenho por restaurante', MARGIN, 63, 12, COLORS.ink, true);
  const restaurants = groupBy(rows, 'restaurant');
  let y = table({ startY: 68, head: ['Restaurante', 'Conversas', 'Pedidos', 'Conversão', 'GMV'], body: restaurants.length ? restaurants.map(g => [g.name, number(g.total), number(g.orders), percent(g.conversion), moneyText(g.gmv)]) : [['Nenhum resultado', '0', '0', '0%', moneyText(0)]], columnStyles: { 0: { cellWidth: 59 }, 1: { halign: 'right' }, 2: { halign: 'right' }, 3: { halign: 'right' }, 4: { halign: 'right', cellWidth: 33 } } });
  text('Resultado das conversas', MARGIN, y + 13, 12, COLORS.ink, true);
  y = table({ startY: y + 18, head: ['Status', 'Conversas', 'Participação'], body: Object.entries(STATUSES).map(([key, status]) => { const count = rows.filter(row => row.status === key).length; return [status.label, number(count), percent(ratio(count, rows.length))]; }), columnStyles: { 0: { cellWidth: 100 }, 1: { halign: 'right' }, 2: { halign: 'right' } } });
  // Reservar uma seção de metodologia inteira, sem cortar texto em rodapés.
  if (y > 217) { newPage('Como ler este relatório'); y = 51; }
  text('Como ler os indicadores', MARGIN, y + 12, 12, COLORS.ink, true);
  y = paragraph('GMV: soma das compras confirmadas e recuperadas, sem cancelamentos. Não representa lucro ou receita líquida. Ticket médio: GMV dividido pelos pedidos concluídos.', MARGIN, y + 19, WIDTH, 8.5);
  y = paragraph('Conversão: sessões com compra confirmada divididas pelas sessões iniciadas no período. O funil conta sessões únicas que alcançaram cada etapa. Abandonados: carrinhos sem conclusão após 30 minutos, ainda não recuperados.', MARGIN, y + 3, WIDTH, 8.5);
  paragraph('Base integralmente simulada. Compras após follow-up indicam associação temporal, não causalidade. O relatório usa os filtros globais; pesquisa e filtros locais da tabela de Conversas não alteram este recorte.', MARGIN, y + 3, WIDTH, 8.5);

  newPage('Conversas do período');
  paragraph('Identificadores pseudonimizados. Nomes, telefones e mensagens não são exportados. Valores do carrinho e compras confirmadas aparecem separadamente.', MARGIN, 58, WIDTH, 8.5);
  const sorted = [...rows].sort((a,b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
  if (sorted.length) table({
    startY: 71, fontSize: 7.5,
    head: ['Conversa / cliente', 'Última interação', 'Status', 'Restaurante', 'Carrinho', 'Compra'],
    body: sorted.map(s => [pdfText(`${s.id}\n${s.clientId}`), dateTime(s.updatedAt), STATUSES[s.status].label, s.restaurant, moneyText(s.amountCents), moneyText(isSale(s) ? s.amountCents : 0)]),
    columnStyles: { 0: { cellWidth: 38 }, 1: { cellWidth: 28 }, 2: { cellWidth: 31 }, 3: { cellWidth: 33 }, 4: { cellWidth: 24, halign: 'right' }, 5: { cellWidth: 24, halign: 'right' } },
  }); else {
    doc.setFillColor(...COLORS.light); doc.roundedRect(MARGIN, 78, WIDTH, 28, 2, 2, 'F');
    text('Nenhuma conversa nos filtros selecionados.', 105, 94, 11, COLORS.muted, false, { align: 'center' });
  }

  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page++) {
    doc.setPage(page); doc.setDrawColor(...COLORS.line); doc.setLineWidth(.2); doc.line(16, 280, 194, 280);
    text('HackFood Analytics | Demonstração | America/Sao_Paulo', MARGIN, 286, 7, COLORS.muted);
    text(`${page} / ${pages}`, 194, 286, 8, COLORS.muted, false, { align: 'right' });
  }
  return doc;
}
