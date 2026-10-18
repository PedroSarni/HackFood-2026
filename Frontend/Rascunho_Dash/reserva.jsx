import React, { useCallback, useEffect, useState } from 'react';

// Bastidor da apresentação (src/bot/contexto.py), discreto no pé da barra lateral:
// - "Modo palco": arma a troca automática. Com ele, no 1º sinal de queda do iFood o bot passa pro catálogo de
//   reserva sem mostrar erro a ninguém. Desligado (padrão), queda do iFood é erro de verdade, como deve ser.
// - "Catálogo de reserva": o mock do MCP ligado agora (na mão ou porque o iFood caiu com o modo palco armado).
const MOCK_MS = 15000;
const hora = ts => new Date(ts * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });

function Chave({ titulo, detalhe, ligado, onChange, disabled, dica }) {
  return <label className="mode-control mock-switch" title={dica}>
    <span><span className="mock-switch-title">{titulo}</span><small>{detalhe}</small></span>
    <input role="switch" type="checkbox" aria-label={titulo} checked={ligado} disabled={disabled} onChange={onChange} />
    <span className="switch-track"><span /></span>
  </label>;
}

export function MockSwitch({ source }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const fonte = source || 'real';
  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/mock?fonte=${fonte}`);
      const data = response.ok ? await response.json() : null;
      setState(data && typeof data.ligado === 'boolean' ? data : null);
    } catch { setState(null); }
  }, [fonte]);
  useEffect(() => {
    if (typeof fetch !== 'function') return undefined;
    load();
    const timer = setInterval(load, MOCK_MS);
    return () => clearInterval(timer);
  }, [load]);
  if (!state) return null;
  const mudar = async corpo => {
    setBusy(true);
    try {
      const response = await fetch(`/api/mock?fonte=${fonte}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(corpo) });
      if (response.ok) setState(await response.json());
    } catch { /* fica como estava */ }
    setBusy(false);
  };
  const reserva = !state.ligado ? 'iFood de verdade' : state.auto ? `entrou sozinho às ${hora(state.desde)}` : 'ligado no dash';
  return <div className="mock-switches">
    <Chave titulo="Modo palco" detalhe={state.reservaAuto ? 'iFood caiu? vai pra reserva' : 'desligado'} ligado={state.reservaAuto}
      disabled={busy} onChange={() => mudar({ reservaAuto: !state.reservaAuto })}
      dica="Com o modo palco, no 1º erro do iFood o bot passa pro catálogo de reserva sem mostrar erro a ninguém." />
    <Chave titulo="Catálogo de reserva" detalhe={reserva} ligado={state.ligado} disabled={busy}
      onChange={() => mudar({ ligado: !state.ligado })} dica={state.motivo || 'Mock do MCP do iFood'} />
  </div>;
}
