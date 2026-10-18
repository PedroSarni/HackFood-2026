import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Clock3, Copy, FileCode2, KeyRound, LifeBuoy, Network, Power, Search, ShieldCheck, Sparkles, X, Zap } from 'lucide-react';
import { clock, latency, pct, useLiveSteps, useSummary, useTeam } from './telemetria.js';
import { ConversationPicker, Step } from './agentes.jsx';

// O time de agentes, do jeito que o bot funciona: o Maestro (o código, src/bot/fluxo.py) recebe a
// mensagem, chama cada especialista e o iFood, e responde. Os agentes não se falam entre si.
// Ficha de cada um em src/agentes/<id>.py; os números vêm do diário (só contagens, sem texto).

const W = 960, H = 430;
const SPOT = { cliente: { x: 70, y: 392 }, maestro: { x: 480, y: 330 }, ifood: { x: 890, y: 392 } };
const IFOOD = '#f59e0b', WHATSAPP = '#25d366';

function seats(team) {
  const n = team.length;
  return Object.fromEntries(team.map((a, i) => {
    const angle = Math.PI + (i + 0.5) / n * Math.PI;
    return [a.id, { x: Math.round(480 + Math.cos(angle) * 330), y: Math.round(300 + Math.sin(angle) * 215) }];
  }));
}

const curve = (a, b) => `M${a.x},${a.y} Q${(a.x + b.x) / 2},${Math.min(a.y, b.y) - 24} ${b.x},${b.y}`;

const SAYS = {
  entendimento: s => s.acao ? `Entendi: ${s.acao}${s.itens ? ` · ${s.itens} ${s.itens === 1 ? 'item' : 'itens'}` : ''}` : 'Entendi a mensagem',
  foto: s => s.foto ? `Na foto: ${s.foto}${s.itens ? ` · ${s.itens} itens` : ''}` : 'Li a foto',
  relevancia: s => s.mantidas !== undefined ? `Fiquei com ${s.mantidas} ofertas` : s.listas !== undefined ? `Filtrei ${s.listas} listas` : 'Filtrei as ofertas',
  grupo: s => s.itens ? `Kit com ${s.itens} itens` : 'Montei o kit',
  tutor: () => 'Expliquei o próximo passo',
  voz: () => 'Gravei o áudio',
  ouvido: () => 'Transcrevi o áudio',
};

export function sayFor(step, byId) {
  const who = byId[step.agente]?.nome || 'Alguém';
  if (step.tipo === 'entrada') return { who: 'Cliente', text: `Mandou ${String(step.formato || 'mensagem').toLowerCase()}` };
  if (step.tipo === 'saida') return { who: 'Maestro', text: `Respondeu${step.formato ? ` (${String(step.formato).toLowerCase()})` : ''}` };
  if (step.tipo === 'mcp') return { who: 'Maestro', text: `Pediu ao iFood: ${step.tool}${step.ok === false ? ' · falhou' : ''}` };
  if (step.erro === 'desligado') return { who, text: 'Estou de folga: foi o plano B' };
  if (step.ok === false) return { who, text: `Tropecei: ${step.erro || 'erro'}${step.tentativas > 1 ? ` (${step.tentativas} tentativas)` : ''}` };
  const text = (SAYS[step.agente] || (() => 'Feito'))(step);
  return { who, text: step.reserva ? `${text} · no modelo reserva` : text };
}

// Foto de cada agente (a ficha diz o arquivo); sem foto, vai o emoji.
const PHOTOS = import.meta.glob('./images/agentes/*', { eager: true, query: '?url', import: 'default' });

function Avatar({ agent, size = 44 }) {
  const photo = agent.foto && PHOTOS[`./images/agentes/${agent.foto}`];
  return <span className={`agent-avatar ${photo ? 'with-photo' : ''}`} style={{ '--agent': agent.cor, width: size, height: size, fontSize: size * .46 }} aria-hidden="true">{photo ? <img src={photo} alt="" /> : agent.emoji}</span>;
}

// O palco: cada passo do diário vira um "recado" correndo entre o cliente, o Maestro, o agente e o iFood.
// Clicar num personagem abre um balãozinho com o que ele andou fazendo (e, no iFood, o resumo do MCP).
function Stage({ team, byId, step, offline, history, usage, mcp, picked, onPick, onOpenSheet }) {
  const pos = useMemo(() => seats(team), [team]);
  const target = step?.tipo === 'ia' ? pos[step.agente] : step?.tipo === 'mcp' ? SPOT.ifood : step ? SPOT.cliente : null;
  const from = step?.tipo === 'entrada' ? SPOT.cliente : SPOT.maestro;
  const to = step?.tipo === 'entrada' ? SPOT.maestro : target;
  const color = step?.tipo === 'ia' ? byId[step.agente]?.cor : step?.tipo === 'mcp' ? IFOOD : WHATSAPP;
  const bubble = step && !picked ? sayFor(step, byId) : null;
  const bubbleAt = step?.tipo === 'ia' ? pos[step.agente] : step?.tipo === 'entrada' ? SPOT.cliente : SPOT.maestro;
  const state = !step ? '' : step.erro === 'desligado' ? 'off' : step.ok === false ? 'fail' : 'ok';
  const conducting = step && step.tipo !== 'entrada';
  const at = p => ({ left: `${p.x / W * 100}%`, top: `${p.y / H * 100}%` });
  const pick = id => onPick(picked === id ? null : id);
  const lastTool = history.ifood?.[0];
  const mcpErrors = (mcp?.tools || []).reduce((n, t) => n + (t.erros || 0), 0);
  return <div className="team-stage" onKeyDown={e => { if (e.key === 'Escape') onPick(null); }}>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="O time trabalhando: cliente, Maestro, agentes e iFood">
      <defs><radialGradient id="stage-glow"><stop offset="0" stopColor="#ea1d2c" stopOpacity=".09" /><stop offset="1" stopColor="#ea1d2c" stopOpacity="0" /></radialGradient></defs>
      <circle cx={SPOT.maestro.x} cy={SPOT.maestro.y} r="190" fill="url(#stage-glow)" />
      <path className={`wire ${step?.tipo === 'entrada' || step?.tipo === 'saida' ? 'hot' : ''}`} style={{ '--agent': WHATSAPP }} d={curve(SPOT.cliente, SPOT.maestro)} />
      <path className={`wire ${step?.tipo === 'mcp' ? 'hot' : ''}`} style={{ '--agent': IFOOD }} d={curve(SPOT.maestro, SPOT.ifood)} />
      {team.map(a => <path key={a.id} className={`wire ${a.ligado ? '' : 'off'} ${step?.agente === a.id ? 'hot' : ''}`} style={{ '--agent': a.cor }} d={curve(SPOT.maestro, pos[a.id])} />)}
      {step && to && <g key={step.key}>
        <circle r="7" fill={color} className="packet"><animateMotion dur=".55s" fill="freeze" path={curve(from, to)} /></circle>
        {step.tipo !== 'entrada' && step.tipo !== 'saida' && <circle r="5" fill={color} opacity=".55" className="packet"><animateMotion begin=".6s" dur=".5s" fill="freeze" path={curve(to, SPOT.maestro)} /></circle>}
      </g>}
    </svg>
    <button type="button" className={`stage-node client ${step?.tipo === 'entrada' || step?.tipo === 'saida' ? 'hot' : ''} ${picked === 'cliente' ? 'picked' : ''}`} style={at(SPOT.cliente)} onClick={() => pick('cliente')} aria-label="Ver o que chegou do cliente"><span className="node-icon">💬</span><strong>Cliente</strong><small>WhatsApp</small></button>
    <button type="button" className={`stage-node maestro ${step ? 'hot' : ''} ${conducting ? 'conducting' : ''} ${picked === 'maestro' ? 'picked' : ''}`} style={at(SPOT.maestro)} onClick={() => pick('maestro')} aria-label="Ver o que o Maestro orquestrou">
      <span className="node-icon">🎼<span className="batons" aria-hidden="true"><i className="baton left" /><i className="baton right" /></span></span><strong>Maestro</strong><small>o código que orquestra</small>
    </button>
    <button type="button" className={`stage-node ifood ${step?.tipo === 'mcp' ? 'hot' : ''} ${picked === 'ifood' ? 'picked' : ''}`} style={at(SPOT.ifood)} onClick={() => pick('ifood')} aria-label="Ver o uso do MCP do iFood">
      <span className="node-icon">🛵</span><strong>iFood</strong><small>{mcp ? `${mcp.total} chamadas · ${pct(mcp.total ? mcpErrors / mcp.total * 100 : 0)} erro` : 'MCP'}</small>
      {lastTool && <span className={`node-tag ${lastTool.ok === false ? 'fail' : ''}`}>{lastTool.tool}</span>}
    </button>
    {team.map(a => {
      const busy = step?.tipo === 'ia' && step.agente === a.id;
      return <button type="button" key={a.id} className={`stage-agent ${a.ligado ? '' : 'off'} ${busy ? `busy ${state}` : ''} ${picked === a.id ? 'picked' : ''}`} style={{ ...at(pos[a.id]), '--agent': a.cor }} onClick={() => pick(a.id)} aria-label={`Ver as ações de ${a.nome}`}>
        <Avatar agent={a} size={52} />{!a.ligado && <span className="zz" aria-hidden="true">z<b>z</b></span>}
        <strong>{a.nome}</strong><small>{a.cargo}</small>
      </button>;
    })}
    {bubble && bubbleAt && <div key={`b-${step.key}`} className={`stage-bubble ${state} ${bubbleAt === SPOT.maestro ? 'over-maestro' : ''}`} style={at(bubbleAt)} role="status"><b>{bubble.who}</b> {bubble.text}{step.ms > 0 && <small>{latency(step.ms)}</small>}</div>}
    {picked && <Peek id={picked} at={picked === 'cliente' ? SPOT.cliente : picked === 'maestro' ? SPOT.maestro : picked === 'ifood' ? SPOT.ifood : pos[picked]} agent={byId[picked]} usage={usage[picked]} history={history} byId={byId} mcp={mcp} onClose={() => onPick(null)} onOpenSheet={onOpenSheet} />}
    {!step && <div className="stage-idle">{offline ? 'Sem conexão com o servidor do painel.' : 'O time está esperando a próxima mensagem. Manda um “oi” pro bot no WhatsApp.'}</div>}
  </div>;
}

function PeekSteps({ steps, byId, empty }) {
  if (!steps?.length) return <p className="muted">{empty}</p>;
  return <ol className="ticker compact">{steps.slice(0, 5).map(s => { const say = sayFor(s, byId);
    return <li key={s.key} className={s.erro === 'desligado' ? 'off' : s.ok === false ? 'fail' : ''}><span className="ticker-dot" style={{ background: byId[s.agente]?.cor || (s.tipo === 'mcp' ? IFOOD : WHATSAPP) }} /><span>{s.tipo === 'ia' ? say.text : `${say.who}: ${say.text}`}</span><small>{s.ms > 0 ? latency(s.ms) : clock(new Date(s.ts * 1000).toISOString())}</small></li>; })}</ol>;
}

// O balãozinho de um personagem do palco: as últimas ações dele e, no iFood, o resumo do MCP.
function Peek({ id, at, agent, usage, history, byId, mcp, onClose, onOpenSheet }) {
  const left = at.x / W * 100, below = at.y < H * 0.45;
  const style = { left: `${Math.min(Math.max(left, 17), 83)}%`, top: `${at.y / H * 100}%` };
  let title, body;
  if (agent) {
    title = <><Avatar agent={agent} size={30} /><span><b>{agent.nome}</b><small>{agent.cargo} · {agent.ligado ? 'no ar' : 'de folga'}</small></span></>;
    body = <>
      <div className="peek-stats"><span><b>{usage?.chamadas ?? 0}</b>chamadas</span><span><b>{usage?.chamadas ? pct(100 - usage.pctErro) : '—'}</b>sucesso</span><span><b>{latency(usage?.msMedio)}</b>médio</span></div>
      <PeekSteps steps={history[id]} byId={byId} empty={`${agent.nome} ainda não trabalhou desde que você abriu a página.`} />
      <button className="text-button" onClick={() => onOpenSheet(id)}>Abrir a ficha completa</button>
    </>;
  } else if (id === 'ifood') {
    const top = (mcp?.tools || []).slice(0, 5), max = Math.max(1, ...top.map(t => t.chamadas));
    title = <><span className="peek-icon">🛵</span><span><b>iFood · MCP</b><small>{mcp ? `${mcp.total} chamadas em ${mcp.conversas} conversas` : 'carregando'}</small></span></>;
    body = <>
      {top.length ? <div className="peek-tools">{top.map(t => <div key={t.tool}><span>{t.tool}</span><i style={{ width: `${t.chamadas / max * 100}%` }} /><b>{t.chamadas}</b><small className={t.erros ? 'bad' : ''}>{t.erros ? `${pct(t.pctErro)} erro` : latency(t.msMedio)}</small></div>)}</div> : <p className="muted">Nenhuma chamada ao MCP no período.</p>}
      <h4>Agora há pouco</h4>
      <PeekSteps steps={history.ifood} byId={byId} empty="Nenhuma chamada desde que você abriu a página." />
      <Link className="text-button" to="/mcp">Ver o uso do MCP completo</Link>
    </>;
  } else if (id === 'maestro') {
    title = <><span className="peek-icon">🎼</span><span><b>Maestro</b><small>src/bot/fluxo.py · decide cada passo</small></span></>;
    body = <><p className="muted">Recebe a mensagem, chama cada agente e o iFood, e responde. Os agentes nunca se falam direto.</p><PeekSteps steps={history.todos} byId={byId} empty="Esperando a próxima mensagem." /></>;
  } else {
    title = <><span className="peek-icon">💬</span><span><b>Cliente</b><small>o que chega e o que sai no WhatsApp</small></span></>;
    body = <PeekSteps steps={history.cliente} byId={byId} empty="Nenhuma mensagem desde que você abriu a página." />;
  }
  return <div className={`stage-peek ${below ? 'below' : 'above'}`} style={{ ...style, '--agent': agent?.cor || (id === 'ifood' ? IFOOD : '#ea1d2c') }} role="dialog" aria-label="Detalhes do personagem">
    <div className="peek-head">{title}<button className="icon-button" onClick={onClose} aria-label="Fechar detalhes"><X size={15} /></button></div>
    {body}
  </div>;
}

// Toca os passos em fila, um de cada vez; se acumular, acelera pra não ficar pra trás do tempo real.
// `history` guarda os últimos passos de cada personagem, pros balõezinhos do palco.
function usePlayer(source) {
  const queue = useRef([]);
  const [step, setStep] = useState(null);
  const [recent, setRecent] = useState([]);
  const [lastSeen, setLastSeen] = useState({});
  const [history, setHistory] = useState({});
  useEffect(() => { queue.current = []; setStep(null); setRecent([]); setHistory({}); }, [source]);
  const seq = useRef(0);
  const push = useCallback(steps => { queue.current.push(...steps.map(st => ({ ...st, key: `p${seq.current++}` }))); if (queue.current.length > 40) queue.current = queue.current.slice(-40); }, []);
  const status = useLiveSteps(source, push);
  useEffect(() => {
    let timer = null, alive = true;
    const next = () => {
      const item = queue.current.shift();
      if (item) {
        setStep(item);
        setRecent(r => [item, ...r].slice(0, 9));
        if (item.agente) setLastSeen(s => ({ ...s, [item.agente]: Date.now() }));
        const who = item.tipo === 'ia' ? item.agente : item.tipo === 'mcp' ? 'ifood' : 'cliente';
        setHistory(h => ({ ...h, [who]: [item, ...(h[who] || [])].slice(0, 6), todos: [item, ...(h.todos || [])].slice(0, 6) }));
      }
      const wait = !item ? 400 : queue.current.length > 12 ? 280 : queue.current.length > 4 ? 650 : 1250;
      if (alive) timer = setTimeout(next, wait);
    };
    next();
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  return { step, recent, lastSeen, history, status };
}

function Ticker({ recent, byId }) {
  if (!recent.length) return <p className="muted ticker-empty">Os últimos passos do time aparecem aqui.</p>;
  return <ol className="ticker">{recent.map(s => { const say = sayFor(s, byId); const agent = byId[s.agente];
    return <li key={s.key} className={s.erro === 'desligado' ? 'off' : s.ok === false ? 'fail' : ''}><span className="ticker-dot" style={{ background: agent?.cor || (s.tipo === 'mcp' ? IFOOD : WHATSAPP) }} /><span><b>{say.who}</b> {say.text}</span><small>{clock(new Date(s.ts * 1000).toISOString())}</small></li>; })}</ol>;
}

const FILTERS = { todos: 'Todos', ligados: 'Ligados', desligados: 'Desligados', erros: 'Com erro' };

function AgentCard({ agent, usage, working, onOpen }) {
  const success = usage?.chamadas ? 100 - usage.pctErro : null;
  const status = !agent.ligado ? ['off', 'De folga'] : working ? ['busy', 'Trabalhando'] : usage?.pctErro > 10 ? ['warn', 'Tropeçando'] : ['on', 'No ar'];
  return <button type="button" className={`agent-card ${status[0]}`} style={{ '--agent': agent.cor }} onClick={onOpen} aria-label={`Abrir a ficha de ${agent.nome}, ${agent.cargo}`}>
    <div className="agent-card-top"><Avatar agent={agent} /><div><strong>{agent.nome}</strong><small>{agent.cargo}</small></div><span className={`agent-status ${status[0]}`}><i />{status[1]}</span></div>
    <p className="agent-quote">{agent.bordao}</p>
    <div className="agent-numbers">
      <span><b>{usage?.chamadas ?? 0}</b>chamadas</span>
      <span><b className={success !== null && success < 90 ? 'bad' : ''}>{success === null ? '—' : pct(success)}</b>sucesso</span>
      <span><b>{latency(usage?.msMedio)}</b>tempo médio</span>
      <span><b>{usage?.reserva ?? 0}</b>no reserva</span>
    </div>
    <div className="agent-card-foot"><span className="model-chip">{agent.modelos?.[0]?.modelo || '—'}</span>{agent.modeloEscolhido && <span className="subtle-pill">escolhido no painel</span>}{usage?.pulos > 0 && <span className="subtle-pill">{usage.pulos} pulos</span>}</div>
  </button>;
}

function Switch({ checked, onChange, label, disabled }) {
  return <label className="mode-control agent-switch"><span>{label}</span><input role="switch" type="checkbox" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)} /><span className="switch-track"><span /></span></label>;
}

function AgentSheet({ agent, usage, steps, known, onClose, onUpdate, source }) {
  const dialog = useRef(null);
  const [tab, setTab] = useState('desempenho');
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  useEffect(() => { const previous = document.activeElement; dialog.current?.showModal?.(); return () => previous?.focus?.(); }, []);
  const run = async body => { setBusy(true); setError(''); try { await onUpdate(agent.id, body); setConfirm(false); } catch (e) { setError(e.message); } finally { setBusy(false); } };
  const toggle = on => { if (!on && agent.essencial && !confirm) { setConfirm(true); return; } run({ ligado: on }); };
  const copy = async () => { try { await navigator.clipboard.writeText(agent.prompts.join('\n\n---\n\n')); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {} };
  const promptLive = agent.versaoNoAr ? (agent.versaoNoAr === agent.versaoPrompt ? 'igual ao do código' : 'diferente do código daqui: falta deploy') : 'o bot no ar ainda não publicou a ficha';
  const tabs = { desempenho: 'Desempenho', config: 'Configuração', prompt: agent.tipo === 'ia' ? 'System prompt' : 'Serviço' };
  return <dialog className="conversation-drawer agent-sheet" ref={dialog} style={{ '--agent': agent.cor }} onCancel={e => { e.preventDefault(); onClose(); }} aria-labelledby="agent-sheet-title">
    <div className="drawer-shell">
      <div className="drawer-topline"><span><Sparkles size={16} /> Ficha do agente</span><button className="icon-button" onClick={onClose} aria-label="Fechar ficha"><X size={20} /></button></div>
      <div className="sheet-hero"><Avatar agent={agent} size={64} /><div><h2 id="agent-sheet-title">{agent.nome} <span>· {agent.cargo}</span></h2><p>{agent.faz}</p><em>{agent.bordao}</em></div></div>
      <div className="sheet-power">
        <Switch label={agent.ligado ? 'Ligado' : 'Desligado'} checked={agent.ligado} disabled={busy} onChange={toggle} />
        <span className="sheet-power-note"><LifeBuoy size={14} />Se desligar: {agent.planoB}</span>
        {confirm && <div className="sheet-confirm" role="alert"><strong>{agent.nome} é essencial pra conversa.</strong><p>{agent.planoB} Vale na próxima mensagem, sem deploy.</p><div><button className="button" onClick={() => setConfirm(false)}>Manter ligado</button><button className="button primary" onClick={() => run({ ligado: false })} disabled={busy}>Desligar mesmo assim</button></div></div>}
        {error && <p className="sheet-error">Não deu: {error}</p>}
        {source === 'demo' && <p className="muted small-note">Na demonstração o interruptor vale só pros clientes simulados.</p>}
      </div>
      <div className="drawer-tabs" role="tablist">{Object.entries(tabs).map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div>
      <div className="sheet-body">
        {tab === 'desempenho' && <>
          <div className="sheet-stats">
            <div><span>Chamadas</span><b>{usage?.chamadas ?? 0}</b></div>
            <div><span>Sucesso</span><b>{usage?.chamadas ? pct(100 - usage.pctErro) : '—'}</b></div>
            <div><span>Tempo médio</span><b>{latency(usage?.msMedio)}</b></div>
            <div><span>Mais lento</span><b>{latency(usage?.msMax)}</b></div>
            <div><span>Conversas</span><b>{usage?.conversas ?? 0}</b></div>
            <div><span>Caiu pro reserva</span><b>{usage?.reserva ?? 0}</b></div>
          </div>
          <h3>Quem respondeu por {agent.nome}</h3>
          {usage?.modelos?.length ? <div className="model-bars">{usage.modelos.map(m => <div key={m.modelo}><span>{m.modelo}</span><i style={{ width: `${m.n / usage.chamadas * 100}%` }} /><b>{m.n}</b></div>)}</div> : <p className="muted">Nenhuma chamada no período.</p>}
          <h3>Últimos passos</h3>
          {steps.length ? <ol className="ticker">{steps.map(s => <li key={s.key} className={s.erro === 'desligado' ? 'off' : s.ok === false ? 'fail' : ''}><span className="ticker-dot" style={{ background: agent.cor }} /><span>{sayFor(s, { [agent.id]: agent }).text}{s.modelo ? ` · ${s.modelo}` : ''}</span><small>{latency(s.ms)}</small></li>)}</ol> : <p className="muted">Assim que {agent.nome} trabalhar, os passos aparecem aqui.</p>}
        </>}
        {tab === 'config' && <>
          <h3>Fila de modelos</h3>
          <ol className="model-queue">{agent.modelos.map((m, i) => <li key={m.modelo}><span className="step-number">{i + 1}</span><strong>{m.modelo}</strong>{i === 0 ? <span className="badge green"><i />principal</span> : <span className="subtle-pill">reserva</span>}{m.prazo && <small>até {String(m.prazo).replace('.', ',')} s</small>}{m.pensamento && <small>pensamento {m.pensamento}</small>}</li>)}</ol>
          {agent.tipo === 'ia' && <p className="muted small-note">Toda a fila falhou? Ainda tem o quebra-galho do OpenRouter, se a key estiver configurada.</p>}
          {agent.tipo === 'ia' && <label className="sheet-field"><span>Modelo principal</span><select value={agent.modeloEscolhido || ''} disabled={busy} onChange={e => run(e.target.value ? { modelo: e.target.value } : { limparModelo: true })}><option value="">{agent.modeloEscolhido ? 'Voltar ao padrão da ficha' : `Padrão da ficha (${agent.modelos[0]?.modelo})`}</option>{known.map(m => <option key={m} value={m}>{m}</option>)}</select></label>}
          {agent.modelosNoAr && agent.modelosNoAr[0]?.modelo !== agent.modelos[0]?.modelo && !agent.modeloEscolhido && <p className="sheet-warn">No ar o principal é {agent.modelosNoAr[0]?.modelo}: o código daqui ainda não subiu.</p>}
          <h3><KeyRound size={14} /> Keys</h3>
          <div className="key-list">{agent.keys.map(k => <div key={k.nome}><code>{k.nome}</code><span>{k.secret ? `secret ${k.secret}` : ''}</span>{k.configurada ? <span className="badge green"><i />{k.final}</span> : <span className="badge red"><i />faltando</span>}</div>)}</div>
          <p className="muted small-note"><ShieldCheck size={12} /> {agent.keysDoAr ? 'Lido do bot no ar. A key inteira nunca sai do Modal.' : 'O bot no ar ainda não publicou a ficha: mostrando o ambiente desta máquina.'}</p>
          <h3><LifeBuoy size={14} /> Plano B</h3><p>{agent.planoB}</p>
          <h3><FileCode2 size={14} /> Onde mexer</h3>
          <ul className="file-list">{agent.arquivos.map(f => <li key={f}><code>{f}</code></li>)}</ul>
          <p className="muted small-note">A fila só deste agente fica em <code>{agent.arquivos[0]}</code>. Sem deploy: variável <code>AGENTE_{agent.id.toUpperCase()}_MODELOS</code> ou o seletor acima.</p>
        </>}
        {tab === 'prompt' && (agent.tipo === 'ia' ? <>
          <div className="prompt-head"><span className="subtle-pill">versão {agent.versaoPrompt}</span><span className={agent.versaoNoAr && agent.versaoNoAr !== agent.versaoPrompt ? 'sheet-warn inline' : 'muted'}>No ar: {promptLive}</span><button className="button" onClick={copy}><Copy size={14} />{copied ? 'Copiado' : 'Copiar'}</button></div>
          {agent.prompts.map((p, i) => <pre className="prompt-box" key={i}>{p}</pre>)}
        </> : <><p>{agent.nome} não tem system prompt: é um serviço da ElevenLabs.</p><p className="muted">Modelo: <code>{agent.modelos[0]?.modelo}</code></p></>)}
      </div>
    </div>
  </dialog>;
}

export function TeamPage({ source, period }) {
  const team = useTeam(source);
  const usageState = useSummary('agentes', { source, period });
  const { step, recent, lastSeen, history, status } = usePlayer(source);
  const mcpState = useSummary('mcp', { source, period });
  const mcp = mcpState.data;
  const [picked, setPicked] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [filter, setFilter] = useState('todos');
  const [kind, setKind] = useState('');
  const [model, setModel] = useState('');
  const [search, setSearch] = useState('');
  const [conversation, setConversation] = useState('');
  const timeline = useSummary('agentes', { source, period, conversation });
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { setOpenId(null); setConversation(''); setPicked(null); }, [source]);
  const agents = team.data?.agentes || [];
  const byId = useMemo(() => Object.fromEntries(agents.map(a => [a.id, a])), [agents]);
  const usage = useMemo(() => Object.fromEntries((usageState.data?.agentes || []).map(u => [u.agente, u])), [usageState.data]);
  const models = useMemo(() => [...new Set(agents.map(a => a.modelos?.[0]?.modelo).filter(Boolean))], [agents]);
  const shown = agents.filter(a => (filter === 'todos' || (filter === 'ligados' ? a.ligado : filter === 'desligados' ? !a.ligado : (usage[a.id]?.erros || 0) > 0))
    && (!kind || a.tipo === kind) && (!model || a.modelos?.[0]?.modelo === model)
    && (!search || `${a.nome} ${a.cargo} ${a.faz}`.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR'))));
  if (!team.data) return team.status === 'offline'
    ? <div className="live-banner offline"><Zap size={18} /><div><strong>Sem resposta do servidor do painel.</strong><p>Na raiz do repo, rode <code>.venv/Scripts/python.exe -m src.painel.servidor</code>. Esta página tenta de novo sozinha.</p></div></div>
    : <div className="empty"><Search size={28} /><h3>Chamando o time</h3><p>Lendo a ficha de cada agente.</p></div>;
  const on = agents.filter(a => a.ligado).length;
  const calls = Object.values(usage).reduce((n, u) => n + u.chamadas, 0);
  const errors = Object.values(usage).reduce((n, u) => n + u.erros, 0);
  const timed = Object.values(usage).filter(u => u.msMedio !== null);
  const avg = timed.length ? timed.reduce((n, u) => n + u.msMedio * u.chamadas, 0) / Math.max(1, timed.reduce((n, u) => n + u.chamadas, 0)) : null;
  const open = openId && byId[openId];
  const mcpErrors = (mcp?.tools || []).reduce((n, t) => n + (t.erros || 0), 0);
  const topTools = (mcp?.tools || []).slice(0, 6);
  const rules = usageState.data?.regras || [];
  return <>
    {source === 'demo' && <div className="telemetry-note"><span className="badge purple"><i />Demonstração</span>Clientes simulados conversando com o bot de verdade.</div>}
    <div className="team-summary">
      <div><Power size={16} /><span>No ar</span><b>{on} de {agents.length}</b></div>
      <div><Activity size={16} /><span>Chamadas no período</span><b>{calls}</b></div>
      <div><ShieldCheck size={16} /><span>Sucesso</span><b>{calls ? pct(100 - errors / calls * 100) : '—'}</b></div>
      <div><Clock3 size={16} /><span>Tempo médio</span><b>{latency(avg)}</b></div>
      <div><Network size={16} /><span>Pedidos ao iFood (MCP)</span><b>{mcp ? mcp.total : '—'}{mcp?.total > 0 && <small> · {pct(mcpErrors / mcp.total * 100)} erro</small>}</b></div>
    </div>
    <section className="panel team-live">
      <div className="panel-heading"><div><h2>O time agora</h2><p>Cada recado é um passo de verdade do bot. Toque em alguém pra ver o que ele andou fazendo.</p></div><span className={`live-pill ${status === 'offline' ? 'offline' : ''}`}><i />{status === 'offline' ? 'Desconectado' : 'Ao vivo'}</span></div>
      <div className="team-live-body"><Stage team={agents} byId={byId} step={step} offline={status === 'offline'} history={history} usage={usage} mcp={mcp} picked={picked} onPick={setPicked} onOpenSheet={id => { setPicked(null); setOpenId(id); }} /><aside><h3>Agora há pouco</h3><Ticker recent={recent} byId={byId} /></aside></div>
      {topTools.length > 0 && <div className="mcp-strip"><span className="mcp-strip-label"><Network size={13} />O que o Maestro mais pede ao iFood</span>{topTools.map(t => <span key={t.tool} className={`mcp-chip ${step?.tipo === 'mcp' && step.tool === t.tool ? 'hot' : ''}`} title={`${t.chamadas} chamadas · ${pct(t.pctErro)} de erro · média ${latency(t.msMedio)}`}>{t.tool}<b>{t.chamadas}</b>{t.erros > 0 && <i>{pct(t.pctErro)}</i>}</span>)}<Link to="/mcp" className="text-button">ver tudo</Link></div>}
    </section>
    <section className="panel">
      <div className="panel-heading"><div><h2>Quem está performando</h2><p>Toque num agente pra ver a ficha: modelo, prompt, key e o interruptor.</p></div></div>
      <div className="team-filters">
        <div className="segmented" role="group" aria-label="Filtrar por situação">{Object.entries(FILTERS).map(([k, label]) => <button key={k} className={filter === k ? 'active' : ''} aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>)}</div>
        <select aria-label="Tipo de agente" value={kind} onChange={e => setKind(e.target.value)}><option value="">IA e serviços</option><option value="ia">Só IA (prompt + modelo)</option><option value="servico">Só serviços de voz</option></select>
        <select aria-label="Modelo principal" value={model} onChange={e => setModel(e.target.value)}><option value="">Qualquer modelo</option>{models.map(m => <option key={m}>{m}</option>)}</select>
        <label className="search-field"><Search size={16} /><input aria-label="Buscar agente" placeholder="Buscar agente" value={search} onChange={e => setSearch(e.target.value)} /></label>
      </div>
      {shown.length ? <div className="agent-grid">{shown.map(a => <AgentCard key={a.id} agent={a} usage={usage[a.id]} working={now - (lastSeen[a.id] || 0) < 4000} onOpen={() => setOpenId(a.id)} />)}</div>
        : <div className="empty"><Search size={28} /><h3>Nenhum agente com esses filtros</h3><p>Limpe a busca ou escolha outro filtro.</p></div>}
      {rules.length > 0 && <div className="rules-row"><span className="muted">Rotinas do Maestro, sem IA:</span>{rules.map(r => <span key={r.agente} className="subtle-pill">{r.nome} · {r.disparos} disparos</span>)}</div>}
    </section>
    <section className="panel">
      <div className="panel-heading"><div><h2>Uma conversa, passo a passo</h2><p>Mensagem, quem pensou, o que o código pediu ao iFood e a resposta. Sem o texto da conversa.</p></div>{timeline.data && <ConversationPicker list={timeline.data.conversasLista} value={conversation} onChange={setConversation} />}</div>
      {conversation && timeline.data?.linha?.length ? <ol className="agent-timeline">{timeline.data.linha.map((s, i) => <Step key={`${s.at}-${i}`} step={s} />)}</ol>
        : <p className="muted pad">{conversation ? 'Nada registrado nesta conversa.' : 'Escolha uma conversa pra ver o caminho dela.'}</p>}
    </section>
    {open && <AgentSheet agent={open} usage={usage[open.id]} steps={recent.filter(s => s.agente === open.id)} known={team.data.conhecidos || []} source={source} onClose={() => setOpenId(null)} onUpdate={team.update} />}
  </>;
}
