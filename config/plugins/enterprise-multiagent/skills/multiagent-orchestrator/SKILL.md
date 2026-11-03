---
name: multiagent-orchestrator
description: >-
  Acione esta skill ao orquestrar tarefas complexas, features multi-módulo,
  refatorações ou correções de bugs usando a arquitetura corporativa
  Multiagente (Gemini 4 Argon como Principal Architect & Orchestrator e
  subagentes Gemini Flash como executores paralelos). Também acionada pelo
  comando /multiagent-orchestrator.
---

# Enterprise Multi-Agent Orchestration Playbook (Argon + Flash Fleet)

Este runbook define o protocolo canônico de engenharia multiagente inspirado nas arquiteturas de plataformas de IA de grandes empresas de tecnologia (Google Borg/Blaze, Stripe, Uber): **Control Plane Centralizado (Argon) + Data Plane Distribuído em Frota (Flash) + Portões Determinísticos de Qualidade e Segurança (Evaluator-Optimizer)**.

---

## 1. Arquitetura de Referência (4-Role Fleet)

```
                     ┌──────────────────────────────────────────────┐
                     │        TIER 1: CONTROL PLANE (ARGON)         │
                     │    Principal Architect & Technical Lead      │
                     │  (Análise, RFC/DAG, Contratos, Síntese Final)│
                     └──────┬───────────────┬───────────────┬───────┘
                            │               │               │
         ┌──────────────────┘               │               └──────────────────┐
         ▼ (Fase 1: Reconhecimento)         ▼ (Fase 3: Execução Paralela)      ▼ (Fase 4: Verificação & Red-Team)
┌─────────────────────────┐    ┌──────────────────────────┐    ┌───────────────────────────────────┐
│     flash-explorer      │    │   flash-implementer (N)  │    │  flash-qa-gatekeeper              │
│   Model="flash" (R/O)   │    │   Model="flash" (R/W)    │    │  Model="flash" (Testes & CI Gate) │
│ - Mapeamento de AST     │    │ - Escopo por Módulo      │    ├───────────────────────────────────┤
│ - Leitura de Schemas    │    │ - Worktrees / Inherit    │    │  flash-security-auditor           │
│ - Triagem de Logs/CI    │    │ - Shift-Left Unit Tests  │    │  Model="flash" (OWASP & Domínio)  │
└─────────────────────────┘    └──────────────────────────┘    └───────────────────────────────────┘
```

---

## 2. Procedimento Operacional Padrão (5 Fases Autônomas)

### Fase 1: Bootstrap & Reconhecimento (`flash-explorer`)
1. Verifique se os 4 subagentes (`flash-explorer`, `flash-implementer`, `flash-qa-gatekeeper`, `flash-security-auditor`) já estão ativos na sessão; caso contrário, registre-os via `define_subagent`.
2. Para mapear múltiplos diretórios, rastrear impacto entre pacotes ou diagnosticar logs extensos, invoque `flash-explorer`:
   ```json
   {
     "TypeName": "flash-explorer",
     "Role": "Codebase Reconnaissance",
     "Model": "flash",
     "Workspace": "inherit",
     "Prompt": "<Task Contract de Reconhecimento>"
   }
   ```

### Fase 2: Triagem, Task Sizing Gate, DAG e Execução Especulativa (Argon)
1. **Passo 2.1: Fast-Path Inline (Primeira Etapa Inegociável)**:
   - Se a tarefa exigir $\le 2$ passos simples (ex: ler 1 função, alterar poucas linhas em 1 arquivo, comando trivial de verificação) ou for um bugfix atômico:
   - **Execute DIRETO no orquestrador (Zero subagentes).** Não aciona o Sizing Gate nem decompõe em DAG.
2. **Passo 2.2: Adaptive Task Sizing Gate (Tarefas Fora do Fast-Path)**:
   - Feature Flag: **`ADAPTIVE_TASK_SIZING_ENABLED`** (gerenciado em `~/.gemini/config/flags.json` ou variável de ambiente; default: `true`).
   - Se `ADAPTIVE_TASK_SIZING_ENABLED=false`: ignora o Sizing Gate e procede ao Dynamic DAG paralelo.
   - Se `ADAPTIVE_TASK_SIZING_ENABLED=true`: avalia o modelo analítico antes do fan-out considerando taxa de coordenação ($T_{\text{tax}} \approx 25\text{s}$ por worker):
     $$\text{Expected Speedup} = \frac{T_{\text{single}}}{T_{\text{multi}}} \ge 1.20$$
   - Estratégias determinísticas:
     - **INLINE**: $\text{Expected Speedup} < 1.20$ (trabalho por módulo insuficiente para cobrir taxa de coordenação). Execução retida no orquestrador.
     - **BATCH**: módulos com alta interdependência ($D \ge 0.8$). Agrupados em um único worker `flash-implementer`.
     - **PARALLEL**: $\text{Expected Speedup} \ge 1.20$. Fan-out autorizado para múltiplos `flash-implementer` via Dynamic DAG.
3. **Passo 2.3: Decomposição em Dynamic DAG e Contratos de Interface Congelados**:
   - A partir do relatório do `flash-explorer`, construa o DAG de execução:
   - **Contratos de Interface Congelados**: Schemas, DTOs e assinaturas de funções são definidos e congelados antes de codificar.
   - **Execução Especulativa (Shift-Left Extremo)**: Quando a interface estiver congelada, dispare o `flash-qa-gatekeeper` para criar testes de integração e casos de borda em paralelo enquanto os `flash-implementer` escrevem a lógica funcional.
4. **Passo 2.4: Scheduler Adaptativo & Concurrency Throttling**:
   - Limite base: $\max(N_{agentes}) = \min(N_{tarefas\_disjuntas}, 4)$.
   - Em caso de saturação de tokens (TPM), latência elevada de API ou erros HTTP 429, reduza dinamicamente o pool para $N=2$ ou $N=1$ (adaptive backoff).
5. **Passo 2.5: Seleção de Workspace e Isolamento**:
   - `Workspace="inherit"`: Obrigatório quando arquivos são **estritamente disjuntos**.
   - `Workspace="share"`: Utilizado quando agentes operam em árvores isoladas via `git worktree`.

### Fase 3: Execução Paralela com Shift-Left (`flash-implementer`)
- Dispare os implementadores associados aos nós independentes do DAG.
- **Shift-Left Local Obrigatório**: Cada `flash-implementer` compila e executa testes unitários locais antes de retornar `STATUS: OK`.
- Se a interface do contrato for alterada durante o desenvolvimento, invalide os testes especulativos e notifique o QA Gatekeeper.

### Fase 4: Semantic Reconciliation Gate & Verificação Cruzada
1. **Semantic Reconciliation Gate (Obrigatório para `Workspace="share"`)**:
   - **Passo 1 (Sintático)**: `git merge --no-ff` e validação de conflitos textuais.
   - **Passo 2 (Semântico)**: Execução de compilação/typecheck rápido de fronteira (`tsc --noEmit`, `mypy`, `gcc -fsyntax-only`) para detectar quebras de contrato de API sem conflito de texto Git.
2. **Execução Simultânea dos Portões**:
   - **`flash-qa-gatekeeper`** (`Model="flash"`, `Workspace="inherit"`): Executa testes pré-escritos especulativamente e a bateria global (`make check`).
   - **`flash-security-auditor`** (`Model="flash"`, `Workspace="inherit"`): Audita o `git diff` contra vazamento de credenciais, OWASP e invariantes de domínio.
3. **Circuit Breaker no Evaluator-Optimizer**:
   - Limite estrito de **3 tentativas** de correção.
   - Se persistir com falha na 3ª tentativa, interrompa o loop, grave `scratch/circuit_breaker.log` e escalone para intervenção humana.

### Fase 5: Consolidação, Telemetria V2 & Entrega Executiva (Argon)
- Apresente ao usuário o resumo executivo final contendo:
  1. Decisões arquiteturais e DAG executado.
  2. Tabela de arquivos/símbolos modificados com links clicáveis (`file:///...`).
  3. Evidência de aprovação do Quality Gate e Auditoria de Segurança.
  4. Bloco de telemetria operacional estendida:
     ```yaml
     TELEMETRY:
       WALL_CLOCK_SEC: <tempo_total>
       CRITICAL_PATH_SEC: <tempo_caminho_critico>
       SUBAGENTS_SPAWNED: <total_agentes>
       CONCURRENCY_PEAK: <pico_simultaneo>
       FIRST_PASS_APPROVAL: <TRUE | FALSE>
       OPTIMIZER_RETRIES: <0..3>
       RECONCILIATION_STATUS: <CLEAN | SEMANTIC_ERROR | CONFLICT_RESOLVED | N/A>
       QUALITY_GATE: <PASS | FAIL>
       SECURITY_AUDIT: <APPROVED | REJECTED>
       TASK_SIZING_DECISION: <FAST_PATH | INLINE | BATCH | PARALLEL | DISABLED>
       ESTIMATED_SINGLE_TIME: <segundos | N/A>
       ESTIMATED_MULTI_TIME: <segundos | N/A>
       EXPECTED_SPEEDUP: <ratio | N/A>
       ESTIMATION_CONFIDENCE: <HIGH | MEDIUM | LOW | N/A>
       ACTUAL_SPEEDUP: <ratio | N/A>
     ```
