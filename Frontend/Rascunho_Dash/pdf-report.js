import { jsPDF } from 'jspdf';
import { REFERENCE_DATE, dateKey, groupBy, metrics, money, number, percent, ratio } from './data.js';

export const COLORS = {   // o PDF dos insights (insights-pdf.js) usa as mesmas
  red: [234, 29, 44], ink: [48, 48, 57], muted: [112, 112, 124],
  line: [231, 231, 236], light: [247, 247, 249], blush: [255, 240, 241],
};
const MARGIN = 16;
const WIDTH = 178;
export const pdfText = value => String(value).replace(/[\u00a0\u202f]/g, ' ').replace(/[\u2010-\u2015]/g, '-');

export function reportContext(filters, advanced, referenceDate = REFERENCE_DATE) {
  const end = new Date(`${referenceDate}T12:00:00-03:00`);
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
export function createAnalyticsPdf({ rows, previous = [], filters, advanced = false, source, referenceDate = REFERENCE_DATE, generatedAt = new Date(), logo }) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
  const data = metrics(rows, { period: filters.period || 30, referenceDate });
  const old = metrics(previous);
  const sourceLabel = source === 'demo' || (!source && rows.length > 0 && rows.every(s => s.demo)) ? 'Demonstração' : 'Dados reais';
  const context = reportContext(filters, advanced, referenceDate);
  const headedPages = new Set();
  const generated = generatedAt.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' });
  const moneyText = value => pdfText(money(value));

  doc.setProperties({ title: 'AiFood Analytics - Relatório do canal WhatsApp', author: 'AiFood Analytics', subject: `Indicadores do dashboard - ${sourceLabel}`, keywords: 'AiFood, analytics, indicadores' });
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
    text('aifood', logo ? 33 : 16, 18, 17, COLORS.ink, true);
    text('A N A L Y T I C S', logo ? 33 : 16, 24, 7, COLORS.muted);
    doc.setFillColor(...COLORS.blush);
    doc.roundedRect(151, 14, 43, 8, 2, 2, 'F');
    text(sourceLabel === 'Demonstração' ? 'DADOS SIMULADOS' : 'DADOS REAIS', 172.5, 19.3, 8, COLORS.red, true, { align: 'center' });
    doc.setDrawColor(...COLORS.line);
    doc.line(16, 31, 194, 31);
  };
  const newPage = title => {
    doc.addPage();
    header();
    text(title, MARGIN, 43, 18, COLORS.ink, true);
    text(`Período: ${context.period}`, MARGIN, 50, 9, COLORS.muted);
  };
  // Componentes de desenho específicos deste documento; os números vêm de data.js.
  const cardsAt = (items, top, columns = 2) => {
    const gap = 5, width = (WIDTH - gap * (columns - 1)) / columns;
    items.forEach(([label, value], i) => {
      const x = MARGIN + (i % columns) * (width + gap), y = top + Math.floor(i / columns) * 32;
      doc.setFillColor(...COLORS.light); doc.roundedRect(x, y, width, 27, 2, 2, 'F');
      text(label, x + 4, y + 7, 8, COLORS.muted);
      doc.setFont('helvetica', 'bold'); doc.setFontSize(16);
      const size = Math.min(16, 16 * (width - 8) / Math.max(width - 8, doc.getTextWidth(pdfText(value))));
      text(value, x + 4, y + 20, size, COLORS.ink, true);
    });
  };
  const bar = (label, count, total, y, color = COLORS.red) => {
    text(label, MARGIN, y, 9);
    text(`${number(count)} | ${percent(ratio(count, total))}`, 194, y, 9, COLORS.muted, false, { align: 'right' });
    doc.setFillColor(...COLORS.light); doc.roundedRect(MARGIN, y + 3, WIDTH, 3, 1, 1, 'F');
    if (count && total) { doc.setFillColor(...color); doc.rect(MARGIN, y + 3, WIDTH * count / total, 3, 'F'); }
  };
  const rankings = (field, title) => {
    const groups = groupBy(rows, field);
    // Mesma ordenação por GMV da tela. Paginar sem descartar grupos.
    for (let start = 0; start < Math.max(1, groups.length); start += 8) {
      newPage(title + (start ? ' (continuação)' : ''));
      text('Mercado | compras confirmadas no mesmo recorte', MARGIN, 58, 9, COLORS.muted);
      if (!groups.length) paragraph('Nenhum resultado neste recorte.', MARGIN, 74);
      groups.slice(start, start + 8).forEach((g, i) => {
        const y = 74 + i * 24;
        doc.setFontSize(9);
        const name = doc.splitTextToSize(pdfText(`${start + i + 1}. ${g.name}`), 120);
        text(name.length > 1 ? [name[0], name[1].slice(0, 65)] : name, MARGIN, y, 9, COLORS.ink, true);
        text(moneyText(g.gmv), 194, y, 10, COLORS.red, true, { align: 'right' });
        text(`${number(g.orders)} pedidos | ${percent(g.conversion)} de conversão`, MARGIN, y + 10, 8, COLORS.muted);
        doc.setFillColor(...COLORS.light); doc.rect(MARGIN, y + 13, WIDTH, 3, 'F');
        if (g.gmv) { doc.setFillColor(...COLORS.red); doc.rect(MARGIN, y + 13, WIDTH * ratio(g.gmv, groups[0].gmv) / 100, 3, 'F'); }
      });
    }
  };

  header();
  text('Visão geral do canal WhatsApp', MARGIN, 45, 21, COLORS.ink, true);
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
    const x = MARGIN + index % 3 * 61, y = cardsTop + Math.floor(index / 3) * 33;
    doc.setFillColor(...(index === 0 ? COLORS.blush : COLORS.light));
    doc.roundedRect(x, y, 56, 28, 2, 2, 'F');
    text(label, x + 4, y + 7, 8, COLORS.muted);
    text(value, x + 4, y + 17, 14, index === 0 ? COLORS.red : COLORS.ink, true);
    if (advanced) {
      const key = ['gmv','orders','ticket','conversion','abandoned','recovered'][index];
      const diff = old[key] ? (data[key] - old[key]) / old[key] * 100 : null;
      text(diff === null ? 'Sem base de comparação' : `${diff >= 0 ? '+' : '-'}${percent(Math.abs(diff))} vs. anterior`, x + 4, y + 24, 7, COLORS.muted);
    }
  });

  const chartTop = cardsTop + 78;
  text('Evolução das vendas', MARGIN, chartTop, 12, COLORS.ink, true);
  const days = Number(filters.period || 30);
  const last = new Date(`${referenceDate}T12:00:00-03:00`);
  const dates = Array.from({ length: days }, (_, index) => new Date(last.getTime() - (days - 1 - index) * 86400000));
  const values = data.dailySales.map(day => day.amountCents / 100);
  const oldDate = dateKey(new Date(last.getTime() - days * 86400000));
  const previousValues = metrics(previous, { period: days, referenceDate: oldDate }).dailySales.map(day => day.amountCents / 100);
  const max = Math.max(100, Math.ceil(Math.max(...values, ...(advanced ? previousValues : [])) / 100) * 100);
  const chartX = 34, chartY = chartTop + 9, chartW = 160, chartH = 32;
  for (let i = 0; i < 3; i++) {
    const y = chartY + i * chartH / 2;
    doc.setDrawColor(...COLORS.line); doc.setLineWidth(.2);
    doc.line(chartX, y, chartX + chartW, y);
    text(`R$ ${number(max * (1 - i / 2))}`, 16, y + 1, 7, COLORS.muted);
  }
  const drawSeries = (series, color) => {
    const points = series.map((value, index) => [chartX + (days === 1 ? .5 : index / (days - 1)) * chartW, chartY + chartH * (1 - value / max)]);
    doc.setDrawColor(...color); doc.setFillColor(...color); doc.setLineWidth(.6);
    points.forEach(([x,y], index) => { if (index) doc.line(...points[index - 1], x, y); else if (days === 1) doc.circle(x,y,1.2,'F'); });
  };
  if (advanced) drawSeries(previousValues, COLORS.muted);
  drawSeries(values, COLORS.red);
  text(advanced ? 'Vermelho: GMV atual | Cinza: período anterior' : 'GMV diário em R$', 194, chartTop, 7, COLORS.muted, false, { align: 'right' });
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

  newPage('Conversão e resultados');
  text(advanced ? 'A jornada completa de compra' : 'Da conversa ao pedido', MARGIN, 64, 12, COLORS.ink, true);
  const indices = advanced ? data.stages.map((_, i) => i) : [0,4,8];
  indices.forEach((index, position) => {
    const stage = data.stages[index], y = 75 + position * 13;
    bar(stage.label, stage.count, data.total, y);
    if (advanced && position > 0) {
      const previousStage = data.stages[indices[position - 1]].count;
      text(`${percent(ratio(stage.count, previousStage))} avançaram da etapa anterior | ${number(previousStage - stage.count)} não avançaram`, MARGIN, y + 9, 6.5, COLORS.muted);
    }
  });
  const resultsY = advanced ? 214 : 124;
  text('Resultado das conversas', MARGIN, resultsY, 12, COLORS.ink, true);
  data.outcomes.forEach((item, i) => bar(item.label, item.count, data.total, resultsY + 10 + i * 12));
  paragraph(`Abandono não recuperado: ${percent(data.abandonment)} dos ${number(data.carts)} carrinhos criados. Funil: sessões únicas que alcançaram cada etapa, sobre o início. Concluídas inclui compras recuperadas.`, MARGIN, advanced ? 272 : 190, WIDTH, 8);

  newPage('Follow-ups e clientes');
  text('Retorno ao carrinho', MARGIN, 64, 12, COLORS.ink, true);
  cardsAt([['Follow-ups registrados', number(data.recovered)], ['Compras após follow-up', number(data.recovered)], ['GMV recuperado', moneyText(data.recoveredGmv)], ['Recuperação de carrinhos', percent(data.recovery)]], 70);
  paragraph('Mesma contagem do dashboard: follow-ups registrados correspondem às compras recuperadas. Não há amostra completa de envios nem grupo de controle; a associação temporal não comprova causalidade.', MARGIN, 139, WIDTH, 8.5);
  text('Clientes no período', MARGIN, 163, 12, COLORS.ink, true);
  cardsAt([['Clientes no período', number(data.clients)], ['Compradores recorrentes', number(data.recurring)], ['Taxa de recompra', percent(data.repurchase)]], 169, 3);
  text('Perfil de compra', MARGIN, 211, 12, COLORS.ink, true);
  bar('Recorrentes (2 ou mais compras)', data.recurring, data.clients, 223);
  bar('Primeira compra', data.purchasing - data.recurring, data.clients, 237);
  bar('Ainda sem compra', data.clients - data.purchasing, data.clients, 251);
  paragraph('Taxa de recompra: compradores recorrentes / clientes com pelo menos uma compra no período.', MARGIN, 266, WIDTH, 8);

  rankings('city', 'Vendas por cidade');
  rankings('restaurant', 'Restaurantes em destaque');

  newPage('Financeiro e inteligência');
  cardsAt([['GMV do canal', moneyText(data.gmv)], ['Ticket médio', moneyText(data.ticket)], ['GMV recuperado', moneyText(data.recoveredGmv)], ['Valor em carrinhos abandonados', moneyText(data.abandonedValue)]], 64);
  paragraph('GMV é o volume de compras confirmadas e recuperadas, sem cancelamentos; não representa lucro ou receita líquida. Receita atribuível ao iFood e custos de IA, WhatsApp e infraestrutura: não disponíveis. MRR: não se aplica à demonstração.', MARGIN, 133, WIDTH, 8.5);
  text('Inteligência artificial', MARGIN, 161, 12, COLORS.ink, true);
  cardsAt([['Conversas atendidas', number(data.total)], ['Resposta média', data.averageLatency === null ? '-' : `${data.averageLatency.toFixed(1)} s`], ['Primeira lista aceita', percent(data.acceptance)], ['Taxa de falhas', percent(data.failureRate)]], 168);
  paragraph(`Primeira lista: ${number(data.accepted)} aceitações entre ${number(data.recommended)} sessões com recomendação; ${number(data.acceptedOrders)} compras confirmadas (${percent(data.firstListConversion)} das recomendações).`, MARGIN, 236, WIDTH, 8.5);
  paragraph('Recorte dos filtros globais no instante da exportação. Pesquisa e filtros locais da tabela de Conversas não alteram os indicadores. O relatório reúne as análises agregadas das páginas do dashboard; não inclui registros individuais de clientes.', MARGIN, 253, WIDTH, 8.5);

  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page++) {
    doc.setPage(page); doc.setDrawColor(...COLORS.line); doc.setLineWidth(.2); doc.line(16, 280, 194, 280);
    text(`AiFood Analytics | ${sourceLabel} | America/Sao_Paulo`, MARGIN, 286, 7, COLORS.muted);
    text(`${page} / ${pages}`, 194, 286, 8, COLORS.muted, false, { align: 'right' });
  }
  return doc;
}
