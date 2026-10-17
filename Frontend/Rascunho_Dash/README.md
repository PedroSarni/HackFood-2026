# HackFood Analytics

Protótipo local em React, React Router e Vite. Identidade visual em vermelho, branco e cinza; nenhum serviço de pedidos é conectado.

## Executar

```sh
npm install
npm run dev
```

Abra a URL exibida pelo Vite. `npm run build` gera `dist/`. `npm run preview` serve o build. As rotas usam o histórico do navegador: uma hospedagem estática futura deve direcionar caminhos desconhecidos a `index.html`.

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

## Demonstrar uma compra

1. Clique em **Simular compra**.
2. Avance pelas cinco ações no rodapé do painel: recomendação, carrinho, checkout, pagamento e confirmação.
3. Cada ação registra mensagens e eventos. O carrinho não entra no GMV até a confirmação.
4. Clique em **Ver resultado no Analytics**. A mesma sessão já compõe os indicadores e pode ser localizada em Conversas por `CLI-PITCH`.

Nenhuma mensagem é enviada ao WhatsApp e nenhum pagamento ou pedido real é realizado. Apenas as últimas 20 sessões de pitch são guardadas em `localStorage`, na chave `hackfood-demo-sessions-v1`. A preferência usa `hackfood-mode`. Quando armazenamento não estiver disponível, a demonstração continua em memória.

## Dados e métricas

`data.js` centraliza fixtures, filtros, cálculos e exportação. A base tem 360 sessões simuladas entre 19/08 e 17/10/2026; a data de referência é fixa para manter a apresentação reproduzível. A amostra padrão de 30 dias tem 180 sessões. Cada sessão representa uma única jornada de compra; valores são inteiros em centavos. Fuso: `America/Sao_Paulo`.

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

Comparação com período imediatamente anterior de mesma duração. Hipóteses de abandono são identificadas como hipóteses. Compra após follow-up é uma associação temporal; não há grupo de controle. Todos os números derivam das fixtures, sem dados reais misturados.

## Limites e integração futura

Este diretório estava vazio; não havia backend, autenticação ou integração a preservar. O protótipo **não implementa autenticação administrativa, auditoria de acesso, armazenamento de conversas reais ou integração com WhatsApp/iFood**. Não inserir dados pessoais reais no armazenamento demonstrativo.

Para integração futura, substituir o carregamento em `data.js` por um serviço autenticado, com paginação no servidor, autorização administrativa, pseudonimização, retenção e registro de acesso. Usar IDs de eventos para deduplicar webhooks e comprovar confirmações de pedidos no backend. Os eventos precisam conter `id`, `conversationId`, `type`, `at`, `source` e metadados disponíveis. Não tratar a simulação como canal de ingestão.

XLSX, coortes, mapas, custos, versões da IA e campanhas reais não foram implementados. Métricas indisponíveis estão identificadas na interface. CSV e PDF são exportações funcionais do protótipo. Fontes web usam Google Fonts com fallback local.

O PDF é gerado no navegador, sem envio de dados a um serviço externo. `pdf-report.js` reutiliza os cálculos de `data.js`; `report-download.js` carrega o gerador e a imagem da marca somente ao solicitar o arquivo. Os relatórios não incluem nomes, telefones ou conteúdo de mensagens. Período, filtros globais efetivos, data de emissão, fuso horário e identificação de dados simulados constam no documento. Uma amostra gerada está em `output/pdf/hackfood-relatorio-exemplo.pdf`.

## Verificação

```sh
npm test
npm run build
```

Os testes cobrem regras financeiras, denominadores, filtros e períodos, integridade das fixtures, CSV, persistência, rotas, modos, etapas do funil, pesquisa, paginação, drawer e simulação completa. O dialog é adaptado no jsdom; comportamento nativo de foco, layout e responsividade precisam de conferência em navegador real. Não havia navegador disponível na sessão de implementação.

A exportação PDF também tem testes de seleção de filtros, geração de arquivo, paginação, recorte vazio, falha e nova tentativa, além de bloqueio de downloads duplicados. O PDF de exemplo foi renderizado com Poppler e suas 13 páginas foram inspecionadas; a extração confirmou as 180 conversas únicas e os totais do painel.
