## 2026-10-17 21:30 — dados do dashboard não carregam

**Prompt:** quando eu entro no frontend e quano tento puxar os dados reais ou os dados reais ou a demonstração eu não consigo puxar as informações, pq nn consigo, o wu preciso?

**Resposta:** Verifiquei o frontend e o servidor do painel: as duas fontes dependem da API Python local na porta 8787, que não respondeu neste ambiente.
Não há `.venv` e o Python padrão não tem fastapi, uvicorn, modal ou httpx. Orientei a instalação e execução no Linux; o comando mostrado no painel usa caminho de Windows.
Dados reais exigem autenticação e acesso ao workspace Modal do bot; a demonstração pode rodar com `--sem-real`. Nenhuma alteração no código da aplicação; execução e autenticação ficam pendentes.
