import React, { useCallback, useEffect, useState } from 'react';

// Bastidor da apresentação (src/bot/contexto.py), discreto no pé da barra lateral. Os rótulos são "Botão 1" e
// "Botão 2" de propósito (pedido do Fabio, 18/10): no palco ninguém precisa ler "iFood caiu" na tela.
// - "Modo palco": arma a troca automática. Com ele, no 1º sinal de queda do iFood o bot passa pro catálogo de
//   reserva sem mostrar erro a ninguém. Desligado (padrão), queda do iFood é erro de verdade, como deve ser.
// - "Catálogo de reserva": o mock do MCP ligado agora (na mão ou porque o iFood caiu com o modo palco armado).
const MOCK_MS = 15000;

function Chave({ titulo, ligado, onChange, disabled }) {  // sem descrição nem dica: no palco, só o nome e a chave
  return <label className="mode-control mock-switch">
    <span><span className="mock-switch-title">{titulo}</span></span>
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
  return <div className="mock-switches">
    <Chave titulo="Botão 1" ligado={state.reservaAuto} disabled={busy} onChange={() => mudar({ reservaAuto: !state.reservaAuto })} />
    <Chave titulo="Botão 2" ligado={state.ligado} disabled={busy} onChange={() => mudar({ ligado: !state.ligado })} />
  </div>;
}
