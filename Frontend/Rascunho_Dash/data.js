// Cálculos e formatos do dash. Os dados chegam do servidor local (live.js), real ou demonstração.
// Dia de referência dos períodos: o "hoje" do servidor (App chama setReferenceDate a cada foto).
export let REFERENCE_DATE = new Date(Date.now() - 3 * 3600000).toISOString().slice(0, 10);
export const setReferenceDate = value => { REFERENCE_DATE = value; };
export const STATUSES = {
  completed: { label: 'Concluída', tone: 'green' },
  recovered: { label: 'Recuperada', tone: 'teal' },
  abandoned: { label: 'Carrinho abandonado', tone: 'amber' },
  active: { label: 'Em andamento', tone: 'blue' },
  payment: { label: 'Aguardando pagamento', tone: 'purple' },
  cancelled: { label: 'Cancelada', tone: 'neutral' },
  failed: { label: 'Falha', tone: 'red' },
  idle: { label: 'Sem carrinho', tone: 'neutral' },
};
export const STAGES = [
  'Conversa iniciada', 'Intenção identificada', 'Recomendação apresentada',
  'Restaurante selecionado', 'Carrinho criado', 'Carrinho confirmado',
  'Checkout iniciado', 'Pagamento selecionado', 'Pedido confirmado', 'Pedido entregue',
];
export const money = cents => (cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
export const number = n => n.toLocaleString('pt-BR');
export const percent = n => `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
export const ratio = (a, b) => b ? a / b * 100 : 0;
export const time = date => new Date(date).toLocaleTimeString('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit' });
export const dateTime = date => new Date(date).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
export const dateKey = date => new Date(new Date(date).getTime() - 3 * 3600000).toISOString().slice(0, 10);
export const isSale = s => ['completed', 'recovered'].includes(s.status);
export const message = (role, text, at) => ({ kind: 'message', role, text, at, type: 'Texto' });
export const event = (type, label, at, stage) => ({ kind: 'event', type, label, at, stage });

export function filterSessions(sessions, filters, advanced = true, previous = false) {
  const days = Number(filters.period || 30);
  const end = new Date(`${REFERENCE_DATE}T23:59:59.999-03:00`).getTime() - (previous ? days * 86400000 : 0);
  const start = end - days * 86400000;
  return sessions.filter(s => {
    const timestamp = Date.parse(s.startedAt);
    return timestamp > start && timestamp <= end &&
      (!advanced || !filters.city || s.city === filters.city) &&
      (!advanced || !filters.restaurant || s.restaurant === filters.restaurant) &&
      (!advanced || !filters.origin || s.origin === filters.origin);
  });
}

export function metrics(sessions) {
  const sales = sessions.filter(isSale);
  const gmv = sales.reduce((sum, s) => sum + s.amountCents, 0);
  const abandoned = sessions.filter(s => s.status === 'abandoned').length;
  const recovered = sessions.filter(s => s.status === 'recovered').length;
  const carts = sessions.filter(s => s.stage >= 5).length;
  return { gmv, orders: sales.length, ticket: sales.length ? gmv / sales.length : 0, conversion: ratio(sales.length, sessions.length), abandoned, recovered, carts, total: sessions.length, recovery: ratio(recovered, abandoned + recovered), abandonment: ratio(abandoned, carts), stages: STAGES.map((label, i) => ({ label, count: sessions.filter(s => s.stage > i).length })) };
}

export function groupBy(sessions, key) {
  const groups = new Map();
  for (const session of sessions) {
    const value = session[key];
    if (!groups.has(value)) groups.set(value, []);
    groups.get(value).push(session);
  }
  return [...groups].map(([name, rows]) => ({ name, rows, ...metrics(rows) })).sort((a, b) => b.gmv - a.gmv);
}

export function csvExport(sessions) {
  const escape = value => `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"`;
  const rows = [['Origem dos dados', 'Conversa', 'Cliente', 'Início', 'Status', 'Restaurante', 'Carrinho BRL', 'Compra confirmada BRL'], ...sessions.map(s => [s.demo ? 'Simulado' : 'Bot WhatsApp', s.id, s.clientId, s.startedAt, STATUSES[s.status].label, s.restaurant, (s.amountCents / 100).toFixed(2), (isSale(s) ? s.amountCents / 100 : 0).toFixed(2)])];
  return '\uFEFF' + rows.map(r => r.map(escape).join(';')).join('\r\n');
}
