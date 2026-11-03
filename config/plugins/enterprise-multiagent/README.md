# Enterprise Multi-Agent Architecture (Argon Planner + Flash Fleet)

Plugin global do Google Antigravity que implementa o modelo operacional de engenharia de software multiagente utilizado em grandes empresas de tecnologia (Hierarchical Orchestrator-Workers + Evaluator-Optimizer Gatekeepers).

## Topologia de Agentes Incluída

1. **Control Plane — Principal Architect & Orchestrator (`Gemini 4 Argon`)**:
   - Atua na conversa principal. Decompõe problemas complexos, define contratos de interface (RFCs/Briefs), coordena worktrees paralelas e valida os resultados.
2. **`flash-explorer` (`model: flash`, Somente Leitura)**:
   - Especialista em reconhecimento rápido de código, mapeamento de símbolos/AST, rastreamento de dependências e triagem de logs de CI.
3. **`flash-implementer` (`model: flash`, Escrita/Execução)**:
   - Engenheiro de implementação focado em módulos delimitados (*Bounded Contexts*) e worktrees compartilhadas (`Workspace="share"`).
4. **`flash-qa-gatekeeper` (`model: flash`, Escrita/Testes)**:
   - Engenheiro SDET responsável por escrever testes determinísticos e executar o Quality Gate completo (`make check`, `pytest`, `ruff`, `mypy`, `bun test`).
5. **`flash-security-auditor` (`model: flash`, Somente Leitura)**:
   - Auditor Red-Team de segurança (OWASP, segredos, SQL schemas, containers não-root) e invariantes determinísticas de domínio.
