import { useEffect, useState } from 'react';

// Agregados do servidor local (src/painel/servidor.py): o diário inteiro nunca vem pro navegador,
// só o resumo do recorte e, quando há uma conversa aberta, a sequência dela. Recarrega sozinho
// enquanto a página está aberta; se o servidor cair, mantém o último resumo na tela.
export const REFRESH_MS = 5000;

export function summaryUrl(path, { source, period, conversation }) {
  const query = new URLSearchParams({ fonte: source || 'real' });
  if (period) query.set('dias', period);
  if (conversation) query.set('conversa', conversation);
  return `/api/${path}?${query}`;
}

export function useSummary(path, params) {
  const url = summaryUrl(path, params);
  const [state, setState] = useState({ status: 'loading', data: null });
  useEffect(() => {
    if (typeof fetch !== 'function') { setState({ status: 'offline', data: null }); return undefined; }
    let alive = true, timer = null;
    const load = async () => {
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        if (alive) setState({ status: 'ready', data });
      } catch {
        if (alive) setState(s => ({ status: 'offline', data: s.data }));
      }
      if (alive) timer = setTimeout(load, REFRESH_MS);
    };
    setState({ status: 'loading', data: null });
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [url]);
  return state;
}

export const DOMAINS = { user_mcp: 'Usuário', offer_discovery_mcp: 'Ofertas', cart_mcp: 'Carrinho', order_tracking_mcp: 'Pedido' };

export const latency = ms => ms === null || ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1).replace('.', ',')} s` : `${Math.round(ms)} ms`;
export const pct = value => `${Number(value || 0).toFixed(1).replace('.', ',')}%`;
export const clock = iso => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Sao_Paulo' });
export const day = iso => new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
