import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { createSeed, FIXTURE_DATE } from './fixtures.js';

if (typeof window !== 'undefined') {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLElement.prototype.scrollTo = vi.fn();
  // Servidor do painel de mentira: a 1ª foto chega na hora, com a base fixa e o "agora" dela.
  window.EventSource = class {
    constructor(url) { this.url = url; }
    addEventListener(type, listener) {
      if (type !== 'sessoes') return;
      const foto = { fonte: 'demo', estado: 'pronto', erro: null, agora: Date.parse(`${FIXTURE_DATE}T20:00:00-03:00`) / 1000, sessions: createSeed() };
      listener({ data: JSON.stringify(foto) });
    }
    close() {}
  };
  afterEach(() => { cleanup(); localStorage.clear(); });
}
