"""Qualquer mensagem que a Meta recusaria reprova o teste, mesmo que o bot tenha se virado
(o fallback em texto numerado esconde o problema da conversa, mas não daqui)."""
import pytest

from tests import fakes


@pytest.fixture(autouse=True)
def nenhuma_mensagem_recusada(monkeypatch):
    criados = []
    original = fakes.WhatsAppFake.__init__

    def init(self, *a, **kw):
        original(self, *a, **kw)
        criados.append(self)
    monkeypatch.setattr(fakes.WhatsAppFake, '__init__', init)
    yield
    for w in criados:
        if getattr(w, 'esperar_recusa', False):
            continue
        assert not w.recusadas, f'a Meta recusaria: {w.recusadas[0][0]}'


@pytest.fixture(autouse=True)
def freio_do_ifood_sem_espera(monkeypatch):
    """O ritmo de ~3 chamadas/s vale em produção; nos testes (MockTransport) só atrasaria."""
    from src.shared import ifood_mcp
    monkeypatch.setattr(ifood_mcp, 'INTERVALO_MIN', 0)
    monkeypatch.setattr(ifood_mcp, '_freio', {'proxima': 0.0, 'bloqueado_ate': 0.0})
