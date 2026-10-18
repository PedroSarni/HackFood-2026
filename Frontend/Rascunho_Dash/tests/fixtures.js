// Base fixa SÓ pros testes (era a "base estática" do protótipo): números reproduzíveis.
// Chega no App pelo mesmo caminho dos dados de verdade, via o EventSource falso de setup.js.
import { event, isSale, message, money } from '../data.js';

export const FIXTURE_DATE = '2026-10-17';
export const RESTAURANTS = ['Burger da Vila', 'Sushi Nori', 'Basilico Pizza', 'Verde & Grão'];
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

