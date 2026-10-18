import React, { useEffect, useState } from 'react';
import { Activity, Clock3, MessagesSquare, Network, Search, Zap } from 'lucide-react';
import { DOMAINS, clock, day, latency, pct, useSummary } from './telemetria.js';

// Uso do MCP e rastro dos agentes. Tudo vem agregado do servidor local (telemetria.js):
// aqui só desenha. Fonte 'demo' = clientes simulados, sempre com o rótulo de demonstração.

function Stat({ label, value, icon: Icon, caption }) {
  return <article className="kpi"><div className="kpi-label">{label}<Icon size={17} /></div><strong>{value}</strong><div className="kpi-caption">{caption}</div></article>;
}

function Section({ title, subtitle, action, children }) {
  return <section className="panel"><div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}

function Nothing({ title, text }) {
  return <div className="empty"><Search size={28} /><h3>{title}</h3><p>{text}</p></div>;
}

function Status({ state, source }) {
  if (state.status === 'offline') return <div className="live-banner offline"><Zap size={18} /><div><strong>Sem resposta do servidor do painel.</strong><p>{state.data ? 'Mostrando o último resumo recebido. ' : ''}Esta página tenta de novo sozinha.</p></div></div>;
  if (source === 'demo') return <div className="telemetry-note"><span className="badge purple"><i />Demonstração</span>Dados simulados: clientes de mentira conversando com o bot de verdade.</div>;
  return null;
}

export function ConversationPicker({ list, value, onChange }) {
  const known = list.some(c => c.id === value);
  return <label className="telemetry-picker"><MessagesSquare size={15} /><select aria-label="Conversa" value={known ? value : ''} onChange={e => onChange(e.target.value)}>
    <option value="">Todas as conversas</option>
    {list.map(c => <option key={c.id} value={c.id}>{c.nome} · {day(c.inicio)} · {c.mcp} MCP · {c.ia} IA</option>)}
  </select></label>;
}

function UsageBar({ value }) {
  return <span className="usage-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, value)}%` }} /></span>;
}

export function McpPage({ source, period }) {
  const [conversation, setConversation] = useState('');
  useEffect(() => setConversation(''), [source]);
  const state = useSummary('mcp', { source, period, conversation });
  const data = state.data;
  if (!data) return <><Status state={state} source={source} />{state.status === 'loading' && <Nothing title="Carregando o uso do MCP" text="Somando as chamadas do período no servidor do painel." />}</>;
  const errors = data.tools.reduce((n, t) => n + t.erros, 0);
  const served = data.tools.filter(t => t.tool !== 'listItemTaxonomy').length;
  return <>
    <Status state={state} source={source} />
    <div className="filter-bar telemetry-filters"><ConversationPicker list={data.conversasLista} value={conversation} onChange={setConversation} /><span className="sample-label">{conversation ? 'Uma conversa' : `${data.conversas} conversas usaram o MCP`} · período do filtro global</span></div>
    <div className="simple-stats">
      <Stat label="Chamadas ao MCP" value={data.total} icon={Activity} caption="No recorte escolhido" />
      <Stat label="Conversas que usaram" value={data.conversas} icon={MessagesSquare} caption="Sessões com ao menos uma chamada" />
      <Stat label="Tools usadas" value={`${served} de 23`} icon={Network} caption="O servidor tem 23 tools" />
      <Stat label="Taxa de erro" value={pct(data.total ? errors / data.total * 100 : 0)} icon={Zap} caption={`${errors} chamadas com erro`} />
    </div>
    <Section title="Uso por tool" subtitle="Quantas vezes o código do bot chamou cada tool do iFood, com erro e latência">
      {data.tools.length ? <div className="table-scroll"><table><thead><tr><th>Tool</th><th>Domínio</th><th className="align-right">Chamadas</th><th>% do total</th><th className="align-right">% de erro</th><th className="align-right">Latência média</th><th className="align-right">Latência máx.</th><th className="align-right">Conversas</th></tr></thead>
        <tbody>{data.tools.map(t => <tr key={t.tool}><td><strong>{t.tool}</strong></td><td>{DOMAINS[t.dominio] || '—'}</td><td className="align-right">{t.chamadas}</td><td><span className="usage-cell"><UsageBar value={t.pct} />{pct(t.pct)}</span></td><td className="align-right">{t.erros ? <span className="badge red" title={t.erroComum ? `Erro mais comum: ${t.erroComum}` : undefined}><i />{pct(t.pctErro)}</span> : pct(0)}</td><td className="align-right">{latency(t.msMedio)}</td><td className="align-right">{latency(t.msMax)}</td><td className="align-right">{t.conversas}</td></tr>)}</tbody></table></div>
        : <Nothing title="Nenhuma chamada ao MCP neste recorte" text="Quando o bot buscar, montar carrinho ou fechar pedido, as tools aparecem aqui." />}
    </Section>
    <Section title="Tools que o bot ainda não chamou" subtitle="Da doc do iFood, sem nenhuma chamada no recorte">
      <div className="chip-list">{data.nunca.map(t => <span className="subtle-pill" key={t.tool} title={DOMAINS[t.dominio]}>{t.tool}{t.soNaDoc && <b>só na doc</b>}</span>)}{!data.nunca.length && <span className="muted">Todas as tools foram chamadas.</span>}</div>
    </Section>
    {conversation && <Section title="Sequência das chamadas" subtitle="Na ordem em que o bot chamou o iFood nesta conversa">
      {data.sequencia?.length ? <ol className="call-sequence">{data.sequencia.map((c, i) => <li key={`${c.at}-${i}`} className={c.ok ? '' : 'failed'}><span className="step-number">{i + 1}</span><strong>{c.tool}</strong><span>{clock(c.at)}</span><span>{latency(c.ms)}</span>{c.ok ? <span className="badge green"><i />ok</span> : <span className="badge red"><i />{c.erro || 'erro'}</span>}</li>)}</ol>
        : <Nothing title="Esta conversa não chamou o MCP" text="Ela pode ter parado antes da busca." />}
    </Section>}
  </>;
}
