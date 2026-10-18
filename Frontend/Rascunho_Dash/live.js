import { useEffect, useState } from 'react';

// Conversas em tempo real: o servidor local (src/painel/servidor.py) manda a foto inteira por SSE a
// cada mudança, de uma de duas fontes: 'real' (diário do bot) ou 'demo' (clientes simulados).
// O EventSource reconecta sozinho se o servidor cair e voltar.
export const liveAvailable = () => typeof EventSource !== 'undefined';
const empty = { status: 'connecting', state: null, sessions: [], now: null, error: null, progress: null };

export function useLiveSessions(source) {
  const [live, setLive] = useState(empty);
  useEffect(() => {
    if (!source || !liveAvailable()) return undefined;
    setLive(empty);
    const stream = new EventSource(`/api/stream?fonte=${source}`);
    stream.addEventListener('sessoes', event => {
      try {
        const data = JSON.parse(event.data);
        setLive({ status: 'live', state: data.estado, sessions: data.sessions || [], now: data.agora * 1000, error: data.erro, progress: data.progresso });
      } catch { /* foto quebrada: espera a próxima */ }
    });
    stream.onerror = () => setLive(s => ({ ...s, status: 'offline' }));
    return () => stream.close();
  }, [source]);
  return live;
}
