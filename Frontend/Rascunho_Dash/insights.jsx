import React, { useEffect, useRef, useState } from 'react';
import { ChartNoAxesColumn, Clock3, Gauge, RefreshCw, Sparkles, Target, X } from 'lucide-react';
import { groupBy, isSale, metrics, ratio } from './data.js';

// Botão de IA das páginas Conversão, Clientes e Mercado: a Sofia (src/agentes/analista.py) lê os números
// AGREGADOS da página e devolve insights por time do iFood. Nenhum nome ou telefone de cliente sai daqui.

export const INSIGHT_PAGES = { '/conversao': 'conversao', '/clientes': 'clientes', '/mercado': 'mercado' };
export const SWEEP_MS = 1700;

const TEAM_COLORS = {
  'Produto': '#7a5af8', 'Growth e CRM': '#ec4899', 'Operações': '#f97316', 'Comercial e parcerias': '#10b981',
  'Logística': '#0ea5e9', 'Atendimento': '#eab308', 'Dados e BI': '#64748b', 'Marketing': '#ef4444', 'Tecnologia': '#3b82f6',
};
const IMPACT = { alto: 'Impacto alto', 'médio': 'Impacto médio', baixo: 'Impacto baixo' };

const r1 = n => n === null || n === undefined || Number.isNaN(n) ? null : Math.round(n * 10) / 10;
const reais = cents => Math.round(cents) / 100;

function split(rows, key, label) {
  return groupBy(rows, key).sort((a, b) => b.total - a.total).slice(0, 6)
    .map(g => ({ [label]: g.name || 'não informado', conversas: g.total, conversao: r1(g.conversion), pedidos: g.orders }));
}

// O que a Analista recebe de cada página: só agregados.
export function pageSummary(page, rows, previous, filters) {
  const m = metrics(rows), p = metrics(previous);
  const common = { periodoDias: Number(filters.period), conversas: m.total, conversasPeriodoAnterior: p.total,
    filtros: { cidade: filters.city || 'todas', loja: filters.restaurant || 'todas', origem: filters.origin || 'todas' } };
  if (page === 'conversao') return { ...common,
    conversao: r1(m.conversion), conversaoAnterior: r1(p.conversion), pedidos: m.orders,
    funil: m.stages.map((s, i) => ({ etapa: s.label, conversas: s.count, pctDoInicio: r1(ratio(s.count, m.total)), pctQueAvancouDaAnterior: i ? r1(ratio(s.count, m.stages[i - 1].count)) : 100, pctQueParouNaPassagem: i ? r1(100 - ratio(s.count, m.stages[i - 1].count)) : 0 })),
    carrinhos: m.carts, abandonados: m.abandoned, taxaAbandono: r1(m.abandonment), taxaAbandonoAnterior: r1(p.abandonment),
    recuperados: m.recovered, taxaRecuperacao: r1(m.recovery), valorAbandonadoReais: reais(m.abandonedValue), valorRecuperadoReais: reais(m.recoveredGmv),
    motivosAbandono: groupBy(rows.filter(s => s.status === 'abandoned'), 'reason').sort((a, b) => b.total - a.total).slice(0, 8).map(g => ({ motivo: g.name || 'não identificado', conversas: g.total })),
    aceitacaoPrimeiraLista: r1(m.acceptance), taxaFalhas: r1(m.failureRate), latenciaMediaSegundos: r1(m.averageLatency),
    porTipoDeEntrada: split(rows, 'input', 'entrada'), porOrigem: split(rows, 'origin', 'origem') };
  if (page === 'clientes') {
    const per = new Map();
    for (const s of rows) {
      const c = per.get(s.clientId) || { pedidos: 0, gmv: 0, conversas: 0 };
      c.conversas += 1; if (isSale(s)) { c.pedidos += 1; c.gmv += s.amountCents; }
      per.set(s.clientId, c);
    }
    const all = [...per.values()], buyers = all.filter(c => c.pedidos > 0).sort((a, b) => b.gmv - a.gmv);
    const topN = Math.max(1, Math.ceil(buyers.length * 0.1)), gmv = buyers.reduce((n, c) => n + c.gmv, 0);
    return { ...common,
      clientes: m.clients, compradores: m.purchasing, recorrentes: m.recurring, taxaRecompra: r1(m.repurchase), taxaRecompraAnterior: r1(p.repurchase),
      gmvReais: reais(m.gmv), ticketMedioReais: reais(m.ticket), conversasMediasPorCliente: r1(all.length ? m.total / all.length : 0),
      distribuicaoPedidosPorCliente: { nenhum: all.filter(c => !c.pedidos).length, um: all.filter(c => c.pedidos === 1).length, dois: all.filter(c => c.pedidos === 2).length, tresOuMais: all.filter(c => c.pedidos >= 3).length },
      participacaoDos10PctQueMaisCompramNoGmv: r1(ratio(buyers.slice(0, topN).reduce((n, c) => n + c.gmv, 0), gmv)),
      porOrigem: split(rows, 'origin', 'origem'), porTipoDeEntrada: split(rows, 'input', 'entrada') };
  }
  const cities = groupBy(rows, 'city'), stores = groupBy(rows, 'restaurant');
  const store = g => ({ loja: g.name, conversas: g.total, pedidos: g.orders, gmvReais: reais(g.gmv), conversao: r1(g.conversion), ticketReais: reais(g.ticket), abandonados: g.abandoned });
  const total = stores.reduce((n, g) => n + g.gmv, 0);
  return { ...common, gmvReais: reais(m.gmv), totalCidades: cities.length, totalLojas: stores.length,
    cidades: cities.slice(0, 10).map(g => ({ cidade: g.name, conversas: g.total, pedidos: g.orders, gmvReais: reais(g.gmv), conversao: r1(g.conversion), ticketReais: reais(g.ticket), abandonados: g.abandoned })),
    lojasQueMaisVendem: stores.slice(0, 10).map(store),
    lojasComPiorConversao: stores.filter(g => g.total >= 5).sort((a, b) => a.conversion - b.conversion).slice(0, 5).map(store),
    participacaoDas3MaioresLojasNoGmv: r1(ratio(stores.slice(0, 3).reduce((n, g) => n + g.gmv, 0), total)) };
}

const ERRORS = {
  desligado: ['A Sofia está de folga', 'Ela está desligada na ficha dela, na tela Agentes. Ligue lá e tente de novo.'],
  offline: ['Sem conexão com o servidor do painel', 'Confira se o servidor local está rodando e tente de novo.'],
  modal: ['Não consegui chamar a Sofia no Modal', 'Confira o login do Modal nesta máquina e tente de novo.'],
  modelo: ['O modelo não respondeu direito', 'Às vezes o Gemini engasga. Tente de novo em alguns segundos.'],
};

// A varredura de arco-íris: desce do topo ao rodapé e deixa a borda da tela brilhando enquanto a IA pensa.
function Glow({ phase }) {
  if (!phase) return null;
  return <div className={`ai-overlay ${phase}`} aria-hidden="true">
    <div className="ai-wave"><div className="ai-band" /><div className="ai-crest" /></div>
    <div className="ai-edge soft" /><div className="ai-edge crisp" />
  </div>;
}

function Card({ item, index }) {
  const color = TEAM_COLORS[item.time] || '#7a5af8';
  return <article className="ai-card" style={{ '--team': color, animationDelay: `${index * 90}ms` }}>
    <div className="ai-card-top"><span className="ai-team">{item.time}</span><span className={`ai-impact ${item.impacto === 'alto' ? 'high' : item.impacto === 'baixo' ? 'low' : ''}`}>{IMPACT[item.impacto] || item.impacto}</span></div>
    <h3>{item.titulo}</h3>
    <p className="ai-line"><ChartNoAxesColumn size={13} /><span>{item.evidencia}</span></p>
    <p className="ai-line action"><Target size={13} /><span>{item.acao}</span></p>
    <div className="ai-card-foot"><span><Gauge size={12} />{item.metrica}</span><span><Clock3 size={12} />{item.prazo}</span></div>
  </article>;
}

export function InsightsFab({ page, rows, previous, filters, source }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ status: 'idle' });
  const [phase, setPhase] = useState(null);
  const run = useRef(0);
  useEffect(() => { run.current += 1; setOpen(false); setState({ status: 'idle' }); setPhase(null); }, [page, source]);

  const generate = async (fresh = false) => {
    const id = ++run.current;
    setOpen(true); setState({ status: 'loading' }); setPhase('sweep');
    const sweepDone = new Promise(resolve => setTimeout(resolve, SWEEP_MS));
    setTimeout(() => { if (run.current === id) setPhase(p => p === 'sweep' ? 'thinking' : p); }, SWEEP_MS * 0.55);
    let result;
    try {
      const response = await fetch(`/api/insights?fonte=${source || 'real'}`, { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ pagina: page, dados: pageSummary(page, rows, previous, filters), novo: fresh }) });
      const data = await response.json().catch(() => ({}));
      result = response.ok ? { status: 'ready', data } : { status: 'error', code: data.erro || 'modelo' };
    } catch {
      result = { status: 'error', code: 'offline' };
    }
    await sweepDone;
    if (run.current !== id) return;
    setState(result); setPhase('leaving');
    setTimeout(() => { if (run.current === id) setPhase(null); }, 900);
  };
  const toggle = () => { if (open && state.status !== 'loading') { setOpen(false); return; } if (state.status !== 'loading') generate(); };
  const loading = state.status === 'loading';
  const error = state.status === 'error' && (ERRORS[state.code] || ERRORS.modelo);
  const data = state.data;
  return <>
    <Glow phase={phase} />
    <button type="button" className={`ai-fab ${loading ? 'busy' : ''} ${open ? 'open' : ''}`} onClick={toggle} aria-expanded={open} aria-label={open && !loading ? 'Fechar insights da IA' : 'Gerar insights com IA desta página'}>
      <span className="ai-fab-ring" aria-hidden="true" /><Sparkles size={22} /><span className="ai-fab-tip" aria-hidden="true">Insights com IA</span>
    </button>
    {open && <section className="ai-panel" role="dialog" aria-label="Insights da IA" aria-busy={loading}>
      <header className="ai-panel-head">
        <span className="ai-avatar" aria-hidden="true">📊</span>
        <div><strong>Insights da Sofia</strong><small>{loading ? 'Lendo os números desta página…' : data ? `Analista · ${data.modelo}${data.cache ? ' · guardado há pouco' : ''}` : 'Analista'}</small></div>
        <button className="icon-button" onClick={() => setOpen(false)} aria-label="Fechar insights"><X size={17} /></button>
      </header>
      <div className="ai-panel-body">
        {loading && <div className="ai-skeletons">{[0, 1, 2].map(i => <div key={i} className="ai-skeleton" style={{ animationDelay: `${i * 120}ms` }}><i /><i /><i /></div>)}</div>}
        {error && <div className="ai-error"><strong>{error[0]}</strong><p>{error[1]}</p><button className="button" onClick={() => generate(true)}><RefreshCw size={14} />Tentar de novo</button></div>}
        {data && !loading && <>
          {data.resumo && <p className="ai-summary">{data.resumo}</p>}
          {data.insights.map((item, i) => <Card key={`${item.titulo}-${i}`} item={item} index={i} />)}
        </>}
      </div>
      {data && !loading && <footer className="ai-panel-foot"><span>{source === 'demo' ? 'Feito com os dados simulados da demonstração.' : 'Feito só com os números agregados desta página.'} Confira antes de agir.</span><button className="text-button" onClick={() => generate(true)}><RefreshCw size={13} />Gerar de novo</button></footer>}
    </section>}
  </>;
}
