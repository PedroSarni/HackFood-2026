import { useEffect, useState } from 'react';

// Conversas do bot em tempo real: o servidor local (src/painel/servidor.py) manda a foto inteira
// por SSE a cada mudança. O EventSource reconecta sozinho se o servidor cair e voltar.
export const liveAvailable = () => typeof EventSource !== 'undefined';

export function useLiveSessions(enabled) {
  const [state, setState] = useState({ status: 'connecting', source: null, sessions: [], now: null, error: null });
  useEffect(() => {
    if (!enabled || !liveAvailable()) return undefined;
    setState(s => ({ ...s, status: 'connecting' }));
    const stream = new EventSource('/api/stream');
    stream.addEventListener('sessoes', event => {
      try {
        const data = JSON.parse(event.data);
        setState({ status: 'live', source: data.fonte, sessions: data.sessions || [], now: data.agora * 1000, error: data.erro });
      } catch { /* foto quebrada: espera a próxima */ }
    });
    stream.onerror = () => setState(s => ({ ...s, status: 'offline' }));
    return () => stream.close();
  }, [enabled]);
  return state;
}
