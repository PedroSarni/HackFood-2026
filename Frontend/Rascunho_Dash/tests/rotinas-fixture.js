// Resposta de /api/rotinas do jeito que src/painel/servidor.py manda (painel.resumo_rotinas).
export const NOW = Date.parse('2026-10-18T12:00:00-03:00');
const iso = seconds => new Date(NOW + seconds * 1000).toISOString();

export const rotinas = () => ({
  fonte: 'real', estado: 'pronto', agora: NOW / 1000, conversa: null,
  rotinas: [
    { id: 'cutucada', nome: 'Cutucada', quando: 'Aos 3 min sem resposta no meio de uma pergunta, repete a pergunta uma vez.',
      disparos: 8, conversas: 7, ultimo: iso(-90), serie: [0, 1, 2, 0, 5], resultados: { voltou: 5, 'sem resposta': 3 }, canais: null,
      destaque: { rotulo: 'voltaram a falar', n: 5, de: 8, pct: 62.5 } },
    { id: 'abandono', nome: 'Carrinho esquecido', quando: 'Aos 5 min calada com itens no carrinho, esvazia o carrinho e volta pro menu.',
      disparos: 3, conversas: 3, ultimo: iso(-3600), serie: [1, 0, 0, 2, 0], resultados: { comprou: 1, 'sem resposta': 2 }, canais: null,
      destaque: { rotulo: 'compraram em 24h', n: 1, de: 3, pct: 33.3 } },
    { id: 'lembrete', nome: 'Lembrete de recompra', quando: 'O cron procura lembrete vencido. Na janela de 24h manda os botões; fora dela, mostra quando a pessoa voltar.',
      disparos: 4, conversas: 4, ultimo: iso(-2 * 86400), serie: [2, 0, 1, 1, 0], resultados: { comprou: 2, 'hoje não': 1, parou: 1 },
      canais: { 'na volta': 3, 'na janela': 1 }, destaque: { rotulo: 'viraram pedido', n: 2, de: 4, pct: 50 } },
    { id: 'rastreio', nome: 'Rastreio do pedido', quando: 'Depois do pedido, consulta o iFood no ritmo dele e avisa cada mudança de status.',
      disparos: 0, conversas: 0, ultimo: null, serie: [0, 0, 0, 0, 0], resultados: {}, canais: null,
      destaque: { rotulo: 'pedidos entregues', n: 0, de: 0, pct: null } },
  ],
  serie: { baldes: 5, tamanho: 'dia' },
  disparos: [
    { at: iso(-90), rotina: 'cutucada', resultado: 'esperando', conversa: 'WA-AAA111-001', nome: 'Dona Cida' },
    { at: iso(-3600), rotina: 'abandono', resultado: 'comprou', conversa: 'WA-BBB222-001', nome: 'Seu Zé' },
    { at: iso(-2 * 86400), rotina: 'lembrete', resultado: 'comprou', conversa: null, nome: null },
  ],
  varredura: { ultima: iso(-240), aCada: 900, execucoes: 96, avisados: 1, erros: 0, esperando: 3, ativos: 8, pessoas: 6, proximo: iso(2 * 86400) },
  pedidosAcompanhados: 0, lembretesLigados: 2, vitrine: 12,
});
