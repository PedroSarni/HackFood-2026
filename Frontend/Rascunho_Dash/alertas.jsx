import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bell, CheckCheck, CircleCheck, X } from 'lucide-react';

// Central de notificações: o que o time precisa ver mesmo sem estar olhando o dash. Hoje são os créditos
// do Claude (acabaram, key recusada, voltou). Vem de src/shared/alertas.py via GET /api/alertas.
const ALERTAS_MS = 15000;
const VAZIO = { alertas: [], naoLidas: 0 };
const ler = d => (Array.isArray(d?.alertas) ? { alertas: d.alertas, naoLidas: Number(d.naoLidas) || 0 } : VAZIO);

export function useAlerts(source) {
  const [state, setState] = useState(VAZIO);
  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/alertas?fonte=${source || 'real'}`);
      if (response.ok) setState(ler(await response.json()));
    } catch { /* servidor fora: o sino fica como estava */ }
  }, [source]);
  useEffect(() => {
    if (typeof fetch !== 'function') return undefined;
    load();
    const timer = setInterval(load, ALERTAS_MS);
    return () => clearInterval(timer);
  }, [load]);
  const readAll = useCallback(async () => {
    try {
      const response = await fetch(`/api/alertas/lidas?fonte=${source || 'real'}`, { method: 'POST' });
      if (response.ok) setState(ler(await response.json()));
    } catch { /* tenta de novo no próximo clique */ }
  }, [source]);
  return { ...state, readAll };
}

const when = ts => new Date(ts * 1000).toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });

export function AlertBell({ alerts }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = e => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = e => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close); document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);
  const { alertas, naoLidas, readAll } = alerts;
  const grave = alertas.some(a => !a.lida && a.nivel === 'erro');  // aviso (ex.: iFood caiu, reserva entrou) fica discreto
  return <div className="alert-bell" ref={box}>
    <button className={`icon-button bell-button ${grave ? 'has-unread' : ''}`} aria-label={naoLidas ? `${naoLidas} notificações não lidas` : 'Notificações'} aria-expanded={open} onClick={() => setOpen(v => !v)}>
      <Bell size={16} />{naoLidas > 0 && <span className={`bell-count ${grave ? '' : 'quiet'}`}>{naoLidas > 9 ? '9+' : naoLidas}</span>}
    </button>
    {open && <div className="alert-panel" role="dialog" aria-label="Notificações">
      <div className="alert-panel-head"><strong>Notificações</strong>{naoLidas > 0 && <button className="alert-read" onClick={readAll}><CheckCheck size={14} />Marcar como lidas</button>}<button className="icon-button" aria-label="Fechar notificações" onClick={() => setOpen(false)}><X size={14} /></button></div>
      {!alertas.length ? <p className="alert-empty">Nada por aqui. Quando os créditos do Claude acabarem, o aviso aparece neste sino.</p>
        : <ul>{alertas.map(a => <li key={a.id} className={`alert-item ${a.nivel} ${a.lida ? 'lida' : ''}`}>
          {a.nivel === 'ok' ? <CircleCheck size={16} /> : <AlertTriangle size={16} />}
          <div><strong>{a.titulo}</strong>{a.nivel === 'erro' && <p>O bot seguiu respondendo pelo Gemini. Recarregue os créditos na Anthropic e ele volta sozinho em até 10 min.</p>}{a.detalhe && <small>{a.detalhe}</small>}<span>{when(a.ultima || a.quando)}{a.vezes > 1 ? ` · ${a.vezes}x` : ''}</span></div>
        </li>)}</ul>}
    </div>}
  </div>;
}

export function AlertBanner({ alerts }) {
  const erro = alerts.alertas.find(a => a.nivel === 'erro' && !a.lida);
  if (!erro) return null;
  return <div className="live-banner offline alert-banner" role="alert"><AlertTriangle size={18} /><div><strong>{erro.titulo}</strong><p>O bot está respondendo pelo Gemini (reserva) enquanto isso. Recarregue os créditos na Anthropic: o Claude volta sozinho em até 10 min.</p></div><button className="alert-read" onClick={alerts.readAll}><CheckCheck size={14} />Ok, vi</button></div>;
}
