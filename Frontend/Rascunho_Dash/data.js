// Somente fixtures de demonstração. Nunca inserir registros reais neste armazenamento.
export const REFERENCE_DATE = '2026-10-17';
export const STORAGE_KEY = 'hackfood-demo-sessions-v1';
export const STATUSES = {
  completed: { label: 'Concluída', tone: 'green' },
  recovered: { label: 'Recuperada', tone: 'teal' },
  abandoned: { label: 'Carrinho abandonado', tone: 'amber' },
  active: { label: 'Em andamento', tone: 'blue' },
  payment: { label: 'Aguardando pagamento', tone: 'purple' },
  cancelled: { label: 'Cancelada', tone: 'neutral' },
  failed: { label: 'Falha', tone: 'red' },
};
export const STAGES = [
  'Conversa iniciada', 'Intenção identificada', 'Recomendação apresentada',
  'Restaurante selecionado', 'Carrinho criado', 'Carrinho confirmado',
  'Checkout iniciado', 'Pagamento selecionado', 'Pedido confirmado', 'Pedido entregue',
];
export const RESTAURANTS = ['Burger da Vila', 'Sushi Nori', 'Basilico Pizza', 'Verde & Grão'];
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

const names = ['Marina Costa', 'Pedro Almeida', 'Ana Oliveira', 'Lucas Santos', 'Beatriz Lima', 'Rafael Souza', 'Juliana Rocha', 'Bruno Ferreira', 'Camila Alves', 'Gabriel Martins', 'Luiza Ribeiro', 'Felipe Gomes'];
const statusCycle = ['completed', 'completed', 'abandoned', 'recovered', 'completed', 'active', 'payment', 'completed', 'abandoned', 'cancelled', 'failed', 'completed'];
const reasons = ['Frete elevado', 'Preço dos produtos', 'Motivo não identificado', 'Dificuldade no pagamento'];

export function createSeed() {
  const sessions = [];
  for (let day = 0; day < 60; day++) {
    for (let i = 0; i < 4 + (day % 5); i++) {
      const n = day * 9 + i;
      const status = statusCycle[(n + day) % statusCycle.length];
      const restaurant = RESTAURANTS[n % RESTAURANTS.length];
      const start = new Date(Date.UTC(2026, 9, 17 - day, 22 - i, (n * 7) % 50));
      const at = min => new Date(start.getTime() + (min + (status === 'recovered' && min >= 5 ? 30 : 0)) * 60000).toISOString();
      const stage = isSale({ status }) ? 9 + n % 2 : { abandoned: 5 + n % 3, active: 2 + n % 3, payment: 8, cancelled: 6, failed: 3 }[status];
      const amountCents = stage >= 5 ? 2990 + (n % 13) * 700 : 0;
      const reason = status === 'abandoned' ? reasons[n % reasons.length] : null;
      const entries = [message('customer', 'Oi! Quero uma sugestão para o jantar.', at(0)), event('conversation_started', 'Conversa iniciada', at(0), 1)];
      if (stage >= 3) entries.push(message('agent', `Olá! Encontrei uma opção no ${restaurant}. Quer conhecer o cardápio?`, at(1)), event('recommendations_shown', 'Primeira lista apresentada', at(1), 3));
      if (stage >= 4 && n % 4 === 0) entries.push(message('customer', 'Pode mostrar outras opções desse restaurante?', at(1.3)), message('agent', 'Claro! Separei uma segunda lista com outras combinações disponíveis.', at(1.5)), event('recommendations_shown', 'Segunda lista apresentada', at(1.5), 3));
      if (stage >= 4) entries.push(message('customer', 'Gostei dessa opção. Pode selecionar.', at(2)), event('recommendation_selected', `${restaurant} selecionado`, at(2), 4));
      if (stage >= 5) entries.push(message('agent', `Seu carrinho está pronto: ${money(amountCents)}, incluindo a entrega. Posso continuar?`, at(3)), event('cart_created', `Carrinho criado · ${money(amountCents)}`, at(3), 5));
      if (status === 'abandoned' && reason === 'Frete elevado') entries.push(message('customer', 'Achei o frete caro. Vou deixar para depois.', at(4)));
      if (status === 'recovered') entries.push(event('cart_abandoned', 'Carrinho abandonado', at(5), 5), message('agent', 'Seu carrinho ainda está disponível. Deseja retomar o pedido?', at(6)), event('followup_sent', 'Follow-up de recuperação enviado', at(6), 5), message('customer', 'Sim, quero concluir agora.', at(7)), event('followup_replied', 'Cliente retornou após o follow-up', at(7), 6));
      if (stage >= 7) entries.push(event('checkout_started', 'Checkout iniciado', at(8), 7));
      if (stage >= 8) entries.push(message('customer', 'Vou pagar com Pix.', at(9)), event('payment_selected', 'Pagamento Pix selecionado', at(9), 8));
      if (isSale({ status })) entries.push(message('agent', `Pagamento confirmado! Seu pedido no ${restaurant} foi recebido.`, at(10)), event('order_confirmed', 'Pedido confirmado', at(10), 9));
      if (status === 'recovered') entries.push(event('cart_recovered', 'Compra recuperada confirmada', at(10), 9));
      if (stage === 10) entries.push(event('order_delivered', 'Entrega confirmada', at(15), 10));
      if (status === 'cancelled') entries.push(message('customer', 'Pode cancelar, por favor.', at(10)), event('order_cancelled', 'Cancelamento solicitado pelo cliente', at(10), 6));
      if (status === 'failed') entries.push(event('agent_error', 'Falha ao consultar disponibilidade', at(10), 3));
      if (status === 'abandoned') entries.push(event('cart_abandoned', 'Carrinho sem conclusão após 30 minutos', at(34), stage));
      const latest = entries.reduce((a, b) => a.at > b.at ? a : b).at;
      sessions.push({ id: `DEMO-${String(n + 1).padStart(4, '0')}`, clientId: `CLI-${String(n % names.length + 1).padStart(3, '0')}`, name: names[n % names.length], phone: '(11) •••••-••42', city: n % 3 ? 'São Paulo' : 'Campinas', restaurant, status, stage, amountCents, startedAt: at(0), updatedAt: latest, origin: status === 'recovered' ? 'Follow-up' : 'Orgânica', campaign: status === 'recovered' ? 'Retome seu jantar' : '', input: 'Texto', latency: 1.2 + n % 8 / 10, firstAccepted: n % 4 !== 0, reason, reasonEvidence: reason === 'Frete elevado' ? 'Declarado pelo cliente' : reason && reason !== 'Motivo não identificado' ? 'Hipótese da IA' : 'Sem evidência', entries, demo: true });
    }
  }
  return sessions;
}

export function readSessions() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (Array.isArray(stored)) {
      const demos = stored.filter(s => s?.demo === true && s.id?.startsWith('PITCH-') && Number.isInteger(s.stage) && s.stage >= 1 && s.stage <= 10 && STATUSES[s.status] && Number.isFinite(s.amountCents) && s.amountCents >= 0 && Array.isArray(s.entries) && typeof s.name === 'string' && typeof s.clientId === 'string' && !Number.isNaN(Date.parse(s.startedAt)) && !Number.isNaN(Date.parse(s.updatedAt)));
      return [...demos.slice(0, 20), ...createSeed()];
    }
  } catch { /* Armazenamento indisponível: usar somente fixtures em memória. */ }
  return createSeed();
}

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

export function createPitchSession() {
  const at = '2026-10-17T20:00:00-03:00';
  return { id: `PITCH-${Date.now()}`, clientId: 'CLI-PITCH', name: 'Você · demonstração', phone: '(11) •••••-••00', city: 'São Paulo', restaurant: 'Burger da Vila', status: 'active', stage: 1, amountCents: 0, startedAt: at, updatedAt: at, origin: 'Orgânica', campaign: '', input: 'Texto', latency: 1.4, firstAccepted: true, demo: true, pitchStep: 0, entries: [message('customer', 'Oi! Quero um hambúrguer para o jantar, até R$ 50.', at), event('conversation_started', 'Conversa registrada no Analytics', at, 1)] };
}

export const PITCH_STEPS = [
  { label: 'Receber recomendação', stage: 3, status: 'active', text: 'Encontrei o Burger da Vila: cheeseburger + batata por R$ 39,90. Com a entrega, fica R$ 46,90. Gostou?', role: 'agent', type: 'recommendations_shown', event: 'Intenção identificada e primeira lista apresentada' },
  { label: 'Montar carrinho', stage: 5, status: 'active', amountCents: 4690, text: 'Perfeito! Quero esse combo, por favor.', role: 'customer', type: 'cart_created', event: 'Restaurante selecionado · carrinho de R$ 46,90 criado' },
  { label: 'Confirmar checkout', stage: 7, status: 'active', text: 'Seu combo está no carrinho. Confirma o total de R$ 46,90 para seguir ao pagamento?', role: 'agent', type: 'checkout_started', event: 'Carrinho confirmado · checkout iniciado' },
  { label: 'Escolher pagamento', stage: 8, status: 'payment', text: 'Confirmo! Vou pagar com Pix.', role: 'customer', type: 'payment_selected', event: 'Pix selecionado · aguardando confirmação' },
  { label: 'Simular confirmação', stage: 9, status: 'completed', text: 'Pagamento confirmado! Seu pedido foi recebido pelo Burger da Vila. Previsão de entrega: 30–40 minutos.', role: 'agent', type: 'order_confirmed', event: 'Pedido confirmado · R$ 46,90 registrados no GMV' },
];

export function advancePitch(session) {
  const step = PITCH_STEPS[session.pitchStep];
  if (!step) return session;
  const at = new Date(Date.parse(session.startedAt) + (session.pitchStep + 1) * 60000).toISOString();
  return { ...session, stage: step.stage, status: step.status, amountCents: step.amountCents ?? session.amountCents, updatedAt: at, pitchStep: session.pitchStep + 1, entries: [...session.entries, message(step.role, step.text, at), event(step.type, step.event, at, step.stage)] };
}

export function csvExport(sessions) {
  const escape = value => `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"`;
  const rows = [['Origem dos dados', 'Conversa', 'Cliente', 'Início', 'Status', 'Restaurante', 'Carrinho BRL', 'Compra confirmada BRL'], ...sessions.map(s => ['Simulado', s.id, s.clientId, s.startedAt, STATUSES[s.status].label, s.restaurant, (s.amountCents / 100).toFixed(2), (isSale(s) ? s.amountCents / 100 : 0).toFixed(2)])];
  return '\uFEFF' + rows.map(r => r.map(escape).join(';')).join('\r\n');
}
