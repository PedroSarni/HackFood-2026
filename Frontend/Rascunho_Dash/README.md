# HackFood Analytics

Dash local em React, React Router e Vite, alimentado em tempo real pelo diário do bot (ou pela demonstração simulada). Identidade visual em vermelho, branco e cinza.

## Executar

```sh
npm install
npm run dev
```

Abra a URL exibida pelo Vite. `npm run build` gera `dist/`. `npm run preview` serve o build. As rotas usam o histórico do navegador: uma hospedagem estática futura deve direcionar caminhos desconhecidos a `index.html`.

## Dados reais ou demonstração (tempo real)

Um servidor local serve **duas fontes ao mesmo tempo** e o seletor no topo do dash troca entre elas na hora:

| Seletor | O que mostra |
| --- | --- |
| **Dados reais** | O diário do bot de verdade (`modal.Dict hackfood-painel`, gravado por `src/shared/painel.py`). Precisa do login do Modal nesta máquina. |
| **Demonstração** | ~800 conversas simuladas em 30 dias, com clientes novos chegando ao vivo. Os clientes conversam com o Bot de verdade (fluxo, textos, MCP falso), então as conversas no drawer são as reais do bot. Nenhum dado real. |

```sh
.venv/Scripts/python.exe -m src.painel.servidor     # na raiz do repo (flags: --sem-real, --sem-demo, --nova-demo)
cd Frontend/Rascunho_Dash && npm run dev            # o Vite repassa /api pra 127.0.0.1:8787
```

- Link direto pra apresentação: `http://127.0.0.1:5173/?fonte=demo` ou `?fonte=real`. A última escolha fica salva no navegador.
- A demo leva ~15 s pra gerar na 1ª vez (o dash mostra o progresso); depois fica em cache na pasta temporária e os horários são trazidos pra hoje a cada início.
- Etapas do funil vêm das chamadas ao MCP: `searchOffers` → recomendação, `getItem` → seleção, `createCart`/`addItemToCart` → carrinho, `getCartDeliveryMethods` → carrinho confirmado, `listPaymentMethods` → checkout, `setCartPayment` → pagamento, `submitOrder` → pedido, `trackOrder` DELIVERED → entrega.
- Sessão nova: 6h sem falar, mensagem depois de um pedido confirmado, ou lembrete de recorrência (origem *Follow-up*). Abandono: carrinho parado 30 min; se a pessoa volta e fecha, vira *Recuperada*.
- Privacidade: CPF digitado sai mascarado, link de login não é gravado, telefone aparece mascarado e o servidor só escuta em 127.0.0.1.
- Compra nova aparece como aviso na tela; o drawer de uma conversa aberta atualiza sozinho.

## Experiência

- Modo básico como padrão; preferência de modo preservada no navegador.
- Visão geral com seis indicadores, vendas, funil simplificado, resultados e últimas conversas.
- Conversão com três indicadores e três etapas no básico; dez etapas, perdas, abandono e restaurantes no avançado.
- Rotas independentes para Visão geral, Conversão, Conversas, IA, Follow-ups, Clientes, Mercado, Financeiro e Relatórios.
- Conversas com pesquisa, filtros, paginação e drawer que preserva a tabela. Mensagens e eventos em ordem cronológica; resumo comercial e análise em uma segunda aba.
- Período e filtros globais aplicados sobre a mesma base usada nas métricas. Filtros avançados ficam suspensos no modo básico; voltam ao reativar o avançado.
- Exportação CSV do recorte global com identificadores de cliente, sem conteúdo das mensagens. Filtros locais da tabela não alteram esta exportação.
- Relatório PDF disponível no menu **Exportar → Relatório PDF**, nos dois modos, e em **Relatórios → Baixar relatório PDF**, no modo avançado. Inclui resumo executivo, vendas diárias, funil, restaurantes, distribuição de status, critérios das métricas e todas as conversas do recorte global, com paginação automática.
- Identidade visual utiliza os PNGs fornecidos em `images/`, com a paleta vermelho `#EA1D2C`, branco e cinza. O WebP original tem um fundo quadriculado incorporado (não é transparente), por isso os PNGs foram priorizados para preservar o acabamento.

## Dados e métricas

`data.js` centraliza filtros, cálculos e exportação. Os dados chegam do servidor local (`live.js`): dados reais do bot ou a demonstração simulada; a data de referência é o "hoje" do servidor. Cada sessão representa uma única jornada de compra; valores são inteiros em centavos. Fuso: `America/Sao_Paulo`. A base fixa de 360 sessões ficou só para os testes (`tests/fixtures.js`).

| Indicador | Regra |
| --- | --- |
| GMV | Soma das compras confirmadas e recuperadas; exclui canceladas |
| Pedidos concluídos | Sessões com compra confirmada; não exige entrega confirmada |
| Ticket médio | GMV / pedidos concluídos |
| Conversão | Sessões com compra confirmada / sessões iniciadas no período |
| Abandono | Carrinhos sem conclusão após 30 minutos, ainda não recuperados |
| Taxa de abandono | Carrinhos ainda abandonados / carrinhos criados |
| Recuperação | Carrinhos recuperados / (ainda abandonados + recuperados) |
| Funil | Sessões únicas que alcançaram cada etapa, na coorte de início selecionada |
| Primeira lista aceita | Sessões que selecionaram na primeira lista / sessões com recomendação |
| Recompra | Clientes com ≥2 compras / clientes com ≥1 compra no período |

Comparação com período imediatamente anterior de mesma duração. Hipóteses de abandono são identificadas como hipóteses. Compra após follow-up é uma associação temporal; não há grupo de controle. Cada fonte é calculada separadamente: dados reais e demonstração nunca se misturam.

## Limites e integração futura

O dash **não implementa autenticação administrativa nem auditoria de acesso**: por isso o servidor do painel só escuta em 127.0.0.1 e não deve ser publicado.

Para publicar, trocar o servidor local por um serviço autenticado, com paginação no servidor, autorização administrativa, pseudonimização, retenção e registro de acesso. Usar IDs de eventos para deduplicar webhooks e comprovar confirmações de pedidos no backend. Os eventos precisam conter `id`, `conversationId`, `type`, `at`, `source` e metadados disponíveis. Não tratar a simulação como canal de ingestão.

XLSX, coortes, mapas, custos, versões da IA e campanhas reais não foram implementados. Métricas indisponíveis estão identificadas na interface. CSV e PDF são exportações funcionais do protótipo. Fontes web usam Google Fonts com fallback local.

O PDF é gerado no navegador, sem envio de dados a um serviço externo. `pdf-report.js` reutiliza os cálculos de `data.js`; `report-download.js` carrega o gerador e a imagem da marca somente ao solicitar o arquivo. Os relatórios não incluem nomes, telefones ou conteúdo de mensagens. Período, filtros globais efetivos, data de emissão, fuso horário e identificação de dados simulados constam no documento.

## Verificação

```sh
npm test
npm run build
```

Os testes cobrem regras financeiras, denominadores, filtros e períodos, integridade da base de teste (`tests/fixtures.js`, entregue ao App por um EventSource falso em `tests/setup.js`), CSV, rotas, modos, troca de fonte, etapas do funil, pesquisa, paginação e drawer. O dialog é adaptado no jsdom; comportamento nativo de foco, layout e responsividade precisam de conferência em navegador real.

A exportação PDF também tem testes de seleção de filtros, geração de arquivo, paginação, recorte vazio, falha e nova tentativa, além de bloqueio de downloads duplicados.
