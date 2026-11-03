# Enterprise Multi-Agent Orchestration Rules (Argon + Flash Fleet)

Sempre opere no modo **Hierarchical Orchestrator-Workers com Portões Determinísticos (Evaluator-Optimizer)**:
- **Agente Principal (Gemini 4 Argon / Gemini Flash High)**: Atua como **Principal Architect & Technical Lead**. Aplica estritamente a governança de 2 etapas: (1) **Fast-Path Inline** prioritário para tarefas $\le 2$ passos; (2) **Adaptive Task Sizing Gate** (`ADAPTIVE_TASK_SIZING_ENABLED`, limiar configurável $1.20\times$) para avaliar benefício real antes de delegar. Para tarefas elegíveis a paralelismo: decompõe em Dynamic DAG com contratos explícitos (*Task Contracts*), gerencia concorrência adaptativa ($\le 4$ workers), aciona o Circuit Breaker ($\le 3$ retries) e emite telemetria estendida.
- **Frota de Subagentes (`Model="flash"`)**:
  - `flash-explorer`: Reconhecimento rápido de código, busca de símbolos/AST e triagem de logs (somente leitura).
  - `flash-implementer`: Implementação e refatoração em escopo delimitado (`Workspace="inherit"` para arquivos disjuntos, `"share"` para worktrees isoladas com Reconciliation Gate). Executa validação Shift-Left unitária antes de entregar.
  - `flash-qa-gatekeeper`: Verificação pós-integração e execução do Quality Gate global (`make check`, `pytest`, `ruff`, `mypy`).
  - `flash-security-auditor`: Auditoria adversarial somente leitura de segurança (OWASP, segredos) e invariantes de domínio sobre o `git diff`.
- **Protocolo Token-Friendly**: Pass-by-Reference obrigatório via `scratch/*.log`. Respostas em Micro-Schema (< 80 tokens).
