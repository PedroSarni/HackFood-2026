const appState = {
  page: 'overview',
  period: '30d',
  mode: 'basic',
  activeConversationId: null,
  drawerOpen: false,
  filters: {
    search: '',
    status: 'all',
    region: 'all',
    channel: 'all',
    price: 'all',
    sort: 'recent'
  }
};

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function parseCurrency(value) {
  if (typeof value !== 'string') return 0;
  const cleaned = value.replace(/[R$\s.]/g, '').replace(',', '.');
  const numeric = Number.parseFloat(cleaned || '0');
  return Number.isFinite(numeric) ? numeric : 0;
}

function getConversationFilterOptions(data) {
  const uniqueRegions = [...new Set(data.conversations.map((item) => item.region || 'São Paulo / SP'))];
  const uniqueChannels = [...new Set(data.conversations.map((item) => item.channel || 'WhatsApp'))];
  const uniqueStatuses = [...new Set(data.conversations.map((item) => item.status))];

  return {
    regions: uniqueRegions,
    channels: uniqueChannels,
    statuses: uniqueStatuses
  };
}

function getFilteredConversations(data) {
  const filters = appState.filters;
  const query = filters.search.trim().toLowerCase();

  const filtered = data.conversations.filter((item) => {
    const region = item.region || 'São Paulo / SP';
    const channel = item.channel || 'WhatsApp';
    const amount = parseCurrency(item.paidValue || item.cartValue || 'R$ 0,00');
    const matchesSearch = !query || [item.customer, item.orderSummary, item.order, item.status, region, channel]
      .join(' ')
      .toLowerCase()
      .includes(query);

    const matchesStatus = filters.status === 'all' || item.status === filters.status;
    const matchesRegion = filters.region === 'all' || region === filters.region;
    const matchesChannel = filters.channel === 'all' || channel === filters.channel;

    let matchesPrice = true;
    if (filters.price === '0-50') matchesPrice = amount <= 50;
    if (filters.price === '50-100') matchesPrice = amount > 50 && amount <= 100;
    if (filters.price === '100-plus') matchesPrice = amount > 100;

    return matchesSearch && matchesStatus && matchesRegion && matchesChannel && matchesPrice;
  });

  const ordered = [...filtered].sort((a, b) => {
    if (filters.sort === 'value-desc') {
      return parseCurrency(b.paidValue || b.cartValue || 'R$ 0,00') - parseCurrency(a.paidValue || a.cartValue || 'R$ 0,00');
    }

    if (filters.sort === 'status') {
      return a.status.localeCompare(b.status);
    }

    if (filters.sort === 'value-asc') {
      return parseCurrency(a.paidValue || a.cartValue || 'R$ 0,00') - parseCurrency(b.paidValue || b.cartValue || 'R$ 0,00');
    }

    return new Date(b.lastAt) - new Date(a.lastAt);
  });

  return ordered;
}

function renderConversationsPage() {
  const data = getCurrentData();
  const filteredConversations = getFilteredConversations(data);
  const options = getConversationFilterOptions(data);
  const totalValue = filteredConversations.reduce((sum, item) => sum + parseCurrency(item.paidValue || item.cartValue || 'R$ 0,00'), 0);
  const averageValue = filteredConversations.length ? totalValue / filteredConversations.length : 0;

  return `
    <div class="page-shell">
      <div class="section-card">
        <div class="section-header">
          <div>
            <h3>Painel de conversas</h3>
            <p class="section-subtitle">Filtros operacionais para análise do canal e do desempenho comercial</p>
          </div>
          <button class="ghost-button" id="resetConversationFilters">Limpar filtros</button>
        </div>

        <div class="filter-toolbar">
          <label class="filter-field filter-field-wide">
            <span>Buscar</span>
            <input type="search" data-conversation-filter="search" placeholder="Cliente, pedido, região, canal..." value="${escapeHtml(appState.filters.search)}" />
          </label>

          <label class="filter-field">
            <span>Status</span>
            <select data-conversation-filter="status">
              <option value="all">Todos</option>
              ${options.statuses.map((status) => `<option value="${status}" ${appState.filters.status === status ? 'selected' : ''}>${status}</option>`).join('')}
            </select>
          </label>

          <label class="filter-field">
            <span>Região</span>
            <select data-conversation-filter="region">
              <option value="all">Todas</option>
              ${options.regions.map((region) => `<option value="${region}" ${appState.filters.region === region ? 'selected' : ''}>${region}</option>`).join('')}
            </select>
          </label>

          <label class="filter-field">
            <span>Canal</span>
            <select data-conversation-filter="channel">
              <option value="all">Todos</option>
              ${options.channels.map((channel) => `<option value="${channel}" ${appState.filters.channel === channel ? 'selected' : ''}>${channel}</option>`).join('')}
            </select>
          </label>

          <label class="filter-field">
            <span>Faixa de valor</span>
            <select data-conversation-filter="price">
              <option value="all">Qualquer valor</option>
              <option value="0-50" ${appState.filters.price === '0-50' ? 'selected' : ''}>Até R$ 50</option>
              <option value="50-100" ${appState.filters.price === '50-100' ? 'selected' : ''}>R$ 50 a R$ 100</option>
              <option value="100-plus" ${appState.filters.price === '100-plus' ? 'selected' : ''}>Acima de R$ 100</option>
            </select>
          </label>

          <label class="filter-field">
            <span>Ordenar</span>
            <select data-conversation-filter="sort">
              <option value="recent" ${appState.filters.sort === 'recent' ? 'selected' : ''}>Mais recentes</option>
              <option value="value-desc" ${appState.filters.sort === 'value-desc' ? 'selected' : ''}>Maior valor</option>
              <option value="value-asc" ${appState.filters.sort === 'value-asc' ? 'selected' : ''}>Menor valor</option>
              <option value="status" ${appState.filters.sort === 'status' ? 'selected' : ''}>Por status</option>
            </select>
          </label>
        </div>

        <div class="filter-summary">
          <div class="result-box">
            <span>Conversas filtradas</span>
            <strong>${filteredConversations.length}</strong>
          </div>
          <div class="result-box">
            <span>Valor total</span>
            <strong>${new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(totalValue)}</strong>
          </div>
          <div class="result-box">
            <span>Média por conversa</span>
            <strong>${new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(averageValue)}</strong>
          </div>
        </div>

        <div class="table-wrap">
          ${filteredConversations.length ? `
            <table class="table">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Região</th>
                  <th>Canal</th>
                  <th>Última interação</th>
                  <th>Status</th>
                  <th>Resumo</th>
                  <th>Pedido</th>
                  <th>Valor</th>
                  <th>Ação</th>
                </tr>
              </thead>
              <tbody>
                ${filteredConversations.map((item) => `
                  <tr>
                    <td>${item.customer}</td>
                    <td>${item.region || 'São Paulo / SP'}</td>
                    <td>${item.channel || 'WhatsApp'}</td>
                    <td>${new Date(item.lastAt).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                    <td><span class="status-badge ${normalizeStatus(item.status)}">${item.status}</span></td>
                    <td>${item.orderSummary}</td>
                    <td>${item.order}</td>
                    <td>${item.paidValue}</td>
                    <td><button class="action-button" data-conversation-id="${item.id}">Abrir</button></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : `
            <div class="empty-state">
              Nenhuma conversa atende aos filtros aplicados. Ajuste os critérios para ampliar a busca.
            </div>
          `}
        </div>
      </div>
    </div>
  `;
}

function attachDynamicEvents() {
  document.querySelectorAll('[data-goto]').forEach((button) => {
    button.addEventListener('click', () => {
      setRoute(button.dataset.goto);
    });
  });

  document.querySelectorAll('[data-conversation-id]').forEach((button) => {
    button.addEventListener('click', () => {
      openConversationDrawer(button.dataset.conversationId);
    });
  });

  document.querySelectorAll('[data-conversation-filter]').forEach((control) => {
    const key = control.dataset.conversationFilter;

    const applyFilter = (event) => {
      appState.filters[key] = event.target.value;
      render();
    };

    if (control.type === 'search') {
      control.addEventListener('input', applyFilter);
      return;
    }

    control.addEventListener('change', applyFilter);
  });

  const resetFiltersButton = document.getElementById('resetConversationFilters');
  if (resetFiltersButton) {
    resetFiltersButton.addEventListener('click', () => {
      appState.filters = {
        search: '',
        status: 'all',
        region: 'all',
        channel: 'all',
        price: 'all',
        sort: 'recent'
      };
      render();
    });
  }
}
