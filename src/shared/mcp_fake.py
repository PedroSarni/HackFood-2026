"""MCP falso do iFood: mesmas tools do gateway, dados inventados, tudo em memória.

STUB — dono: Fabio (claim bot-ifood-agent). Em implementação: use esta assinatura, não reimplemente.
Serve pra desenvolver e testar sem credencial (o agente do portal ainda está em análise).
"""


class McpFake:
    def __init__(self, seed=0):
        self.seed = seed
        self.chamadas = []  # (tool, args) na ordem, pros testes conferirem

    def chamar(self, ferramenta, **argumentos):
        raise NotImplementedError('TODO: McpFake.chamar')
