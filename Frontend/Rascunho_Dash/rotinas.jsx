import React, { useEffect, useState } from 'react';
import { CalendarClock, Timer } from 'lucide-react';
import { clock, pct, useSummary } from './telemetria.js';
import './rotinas.css';

// O que o Maestro faz sozinho, sem a pessoa pedir (src/app.py e src/bot/rastreio.py): cutuca quem calou, esquece o
// carrinho parado, manda o lembrete de recompra e avisa o status do pedido. Os números vêm de GET /api/rotinas
// (src/shared/painel.resumo_rotinas): cada disparo, o que a pessoa fez depois e a última passada do cron.

export const ROUTINES = {
  cutucada: { emoji: '👋', color: '#7a5af8', say: 'Cutuquei quem sumiu no meio da conversa' },
  abandono: { emoji: '🛒', color: '#f97316', say: 'Esvaziei um carrinho parado' },
  lembrete: { emoji: '🔔', color: '#ec4899', say: 'Mandei o lembrete de recompra' },
  rastreio: { emoji: '🛵', color: '#0ea5e9', say: 'Avisei o status do pedido' },
};

const STATUS = {
  ORDER_CREATED: 'pedido feito', PLACED: 'pedido feito', CONFIRMED: 'loja confirmou', PREPARING: 'em preparo',
  DISPATCHED: 'saiu pra entrega', ON_THE_WAY: 'a caminho', DELIVERY_ARRIVED_AT_DESTINATION: 'chegou',
  READY_TO_PICKUP: 'pronto pra retirar', DELIVERED: 'entregue', CONCLUDED: 'entregue', CANCELLED: 'cancelado', CANCELED: 'cancelado',
};
const RESULT = {
  voltou: ['voltou a falar', 'good'], comprou: ['comprou depois', 'good'], pediu: ['tocou em pedir', 'good'],
  'hoje não': ['hoje não', 'muted'], parou: ['desligou o lembrete', 'bad'], respondeu: ['respondeu', 'muted'],
  'sem resposta': ['sem resposta', 'muted'], esperando: ['esperando', 'wait'], aviso: ['aviso', 'muted'],
};

export function resultLabel(routine, key) {
  if (routine === 'rastreio') {
    const tone = key === 'DELIVERED' || key === 'CONCLUDED' ? 'good' : key === 'CANCELLED' || key === 'CANCELED' ? 'bad' : 'muted';
    return [STATUS[key] || String(key || 'aviso').toLowerCase().replace(/_/g, ' '), tone];
  }
  if (routine === 'lembrete' && key === 'comprou') return ['virou pedido', 'good'];
  if (routine === 'abandono' && key === 'voltou') return ['voltou sem comprar', 'muted'];
  return RESULT[key] || [key, 'muted'];
}

// "há 3 min", "em 2 dias": o relógio anda junto com a página (o `now` vem da tela do time, a cada segundo).
export function ago(iso, now = Date.now()) {
  if (!iso) return '—';
  const s = Math.round((now - Date.parse(iso)) / 1000), a = Math.abs(s);
  if (s >= 0 && a < 10) return 'agora';
  const days = Math.round(a / 86400);
  const text = a < 45 ? `${a} s` : a < 3600 ? `${Math.round(a / 60)} min` : a < 86400 ? `${Math.round(a / 3600)} h` : `${days} ${days === 1 ? 'dia' : 'dias'}`;
  return s < 0 ? `em ${text}` : `há ${text}`;
}

function Spark({ serie, size }) {
  const max = Math.max(0, ...(serie || []));
  if (!serie?.length) return null;
  return <div className="routine-spark" role="img" aria-label={`Disparos por ${size === 'hora' ? 'hora nas últimas 24 h' : `dia nos últimos ${serie.length} dias`}`}>
    {serie.map((n, i) => <i key={i} className={n ? 'on' : ''} style={{ height: `${max ? Math.max(10, n / max * 100) : 10}%` }} title={`${n} ${n === 1 ? 'disparo' : 'disparos'}`} />)}
  </div>;
}

function Cron({ v, now }) {
  if (!v) return <p className="routine-cron"><Timer size={12} />A passada do cron aparece aqui depois do próximo deploy.</p>;
  const late = v.aCada && now - Date.parse(v.ultima) > v.aCada * 1600;
  return <div className={`routine-cron ${late ? 'late' : ''}`}>
    <span><Timer size={12} />{late ? 'Cron atrasado: ' : 'Cron '}passou {ago(v.ultima, now)}{v.aCada ? ` · a cada ${Math.round(v.aCada / 60)} min` : ''}</span>
    <span>{v.ativos ?? 0} {v.ativos === 1 ? 'lembrete ligado' : 'lembretes ligados'}{v.pessoas ? ` de ${v.pessoas} ${v.pessoas === 1 ? 'pessoa' : 'pessoas'}` : ''}</span>
    {v.proximo && <span><CalendarClock size={12} />próximo vence {ago(v.proximo, now)}</span>}
    {v.esperando > 0 && <span className="wait">{v.esperando} esperando a pessoa voltar (janela de 24h fechada)</span>}
    {v.erros > 0 && <span className="bad">{v.erros} falharam na última passada</span>}
  </div>;
}

function RoutineCard({ routine: r, now, hot, size, children }) {
  const meta = ROUTINES[r.id] || { emoji: '⚙️', color: '#64748b' };
  const fresh = r.ultimo && now - Date.parse(r.ultimo) < 120000;
  const results = Object.entries(r.resultados || {}).sort((a, b) => b[1] - a[1]);
  const top = r.destaque;
  return <article className={`routine-card ${hot ? 'hot' : ''}`} style={{ '--routine': meta.color }} aria-label={`${r.nome}: ${r.disparos} disparos`}>
    <header><span className="routine-icon" aria-hidden="true">{meta.emoji}</span><div><strong>{r.nome}</strong><small>{r.quando}</small></div></header>
    <div className="routine-main"><b>{r.disparos}</b><span>{r.disparos === 1 ? 'disparo' : 'disparos'}{r.conversas ? ` em ${r.conversas} ${r.conversas === 1 ? 'conversa' : 'conversas'}` : ''}</span></div>
    <Spark serie={r.serie} size={size} />
    <p className="routine-last"><i className={fresh ? 'live' : ''} />{r.ultimo ? `Último disparo ${ago(r.ultimo, now)}` : 'Não disparou no período'}</p>
    {top?.de > 0 && <p className="routine-highlight"><b>{pct(top.pct)}</b> {top.rotulo} <small>({top.n} de {top.de})</small></p>}
    {results.length > 0 && <div className="routine-chips">{results.map(([k, n]) => { const [label, tone] = resultLabel(r.id, k); return <span key={k} className={`routine-chip ${tone}`}>{label} <b>{n}</b></span>; })}</div>}
    {r.canais && <div className="routine-chips channels" aria-label="Como o lembrete chegou">{Object.entries(r.canais).map(([k, n]) => <span key={k} className="routine-chip">{k} <b>{n}</b></span>)}</div>}
    {children}
  </article>;
}

function Feed({ items, now, names, onOpen }) {
  if (!items?.length) return <p className="muted routine-empty">Nenhuma rotina disparou no período.</p>;
  return <ol className="routine-feed">{items.map((f, i) => {
    const meta = ROUTINES[f.rotina] || {}, [label, tone] = resultLabel(f.rotina, f.resultado);
    return <li key={`${f.at}-${f.rotina}-${i}`}>
      <span className="routine-dot" style={{ background: meta.color }} />
      <span className="routine-feed-what"><b>{meta.emoji} {names[f.rotina] || f.rotina}</b>
        {f.nome && f.conversa && onOpen ? <button type="button" className="text-button" onClick={() => onOpen(f.conversa)} title="Abrir a conversa">{f.nome}</button> : f.nome && <span>{f.nome}</span>}
        <small title={clock(f.at)}>{ago(f.at, now)}</small></span>
      <span className={`routine-chip ${tone}`}>{label}</span>
    </li>;
  })}</ol>;
}

export function RoutinesPanel({ source, period, step, now = Date.now(), onOpen }) {
  const { data } = useSummary('rotinas', { source, period });
  const [hot, setHot] = useState(null);
  useEffect(() => {   // passo ao vivo de uma rotina: o cartão dela acende na hora, sem esperar o resumo
    if (!step?.rotina) return undefined;
    setHot(step.rotina);
    const t = setTimeout(() => setHot(null), 2600);
    return () => clearTimeout(t);
  }, [step?.key]);
  const routines = data?.rotinas || [];
  if (!routines.length) return null;   // servidor de antes desta seção ou fora do ar: some em vez de mostrar zeros
  const names = Object.fromEntries(routines.map(r => [r.id, r.nome]));
  return <section className="panel routines" aria-labelledby="routines-title">
    <div className="panel-heading"><div><h2 id="routines-title">O que o Maestro faz sozinho</h2><p>Rotinas que disparam sem a pessoa pedir: cada disparo, o que ela fez depois e a última passada do cron. Sem texto da conversa.</p></div>
      {hot && <span className="live-pill routine-pill" style={{ '--routine': ROUTINES[hot]?.color }} role="status"><i />{names[hot]} agora</span>}</div>
    <div className="routines-body">
      <div className="routine-grid">{routines.map(r => <RoutineCard key={r.id} routine={r} now={now} hot={hot === r.id} size={data.serie?.tamanho}>{r.id === 'lembrete' && <Cron v={data.varredura} now={now} />}</RoutineCard>)}</div>
      <aside className="routine-side"><h3>Últimos disparos</h3><Feed items={data.disparos} now={now} names={names} onOpen={onOpen} /></aside>
    </div>
    {data.vitrine > 0 && <p className="routines-foot">Também sem IA: a vitrine de boas-vindas apareceu {data.vitrine} {data.vitrine === 1 ? 'vez' : 'vezes'} no período.</p>}
  </section>;
}
