import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

if (typeof window !== 'undefined') {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLElement.prototype.scrollTo = vi.fn();
  afterEach(() => { cleanup(); localStorage.clear(); });
}
