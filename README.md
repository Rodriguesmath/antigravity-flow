# ⚡ Antigravity Flow

> **High-Performance Orchestration & Token-Friendly Subagent Toolkit for Google Antigravity / Gemini CLI.**

Este repositório contém a suíte completa de **regras de orquestração**, **protocolos anti-latência**, **skills customizadas** e **configurações otimizadas** para transformar o Google Antigravity em um ambiente de desenvolvimento autônomo ágil, enxuto e livre de overhead desnecessário de tokens.

---

## 🎯 Pilares da Arquitetura

O fluxo é construído sobre 7 princípios fundamentais definidos em `config/rules/model-routing.md`:

1. **Heurística Fast-Path Inline (Anti-Latência):**
   - Subagentes possuem custo de inicialização (2–4s de cold-start).
   - Tarefas $\le 2$ passos simples (ler 1 função, trocar poucas linhas, rodar 1 comando trivial) são executadas **diretamente no orquestrador**, sem spawn desnecessário de subagentes.
2. **Cascata Adaptativa em 3 Níveis:**
   - **Nível 1 (Orquestrador Estratégico):** Planejamento macro, decomposição e síntese (`Claude Opus 5.5` / `Gemini 4 Argon` ou fallback `Gemini 3.8 Flash Medium`).
   - **Nível 2 (Subagentes Táticos):** Implementação, refatoração e testes de lógica complexa (`Gemini Flash`).
   - **Nível 3 (Workers Mecânicos):** Execução de terminal, greps em lote, leitura massiva de logs (`Gemini Flash-Lite` com flag `[FAST: ZERO COT / DIRECT ACTION]`).
3. **Padrão Unificado "Write & Verify":**
   - Elimina cascatas sequenciais fragmentadas (Agente escreve -> volta -> Agente testa -> volta).
   - O worker tático escreve o código e valida/testa no mesmo turno, reduzindo o tempo de espera pela metade.
4. **Protocolo Token-Friendly Inter-Agentes (Pass-by-Reference):**
   - Proibido despejo de diffs inteiros e logs brutos no chat ($O(N^2)$ tokens).
   - Saídas volumosas são salvas em `scratch/<task_name>.log` ou diretamente nos arquivos de destino.
   - Retorno em micro-schema compacto (< 80 tokens).
5. **Diretriz Perpétua Caveman:**
   - Comunicação telegráfica, zero fillers, zero cortesias vazias e densidade máxima de informação por token com 100% de precisão técnica.
6. **Princípio Ponytail (The Lazy Senior Developer):**
   - Foco no menor diff funcional possível. Menos código = menos bugs e manutenção.
   - Aplicação da Escada de Decisão dos 7 Degraus (YAGNI -> Reuso Interno -> Stdlib -> Dep Existente -> Uma Linha -> Código Mínimo).
7. **Integração Mandatória com Graphify:**
   - Consulta e navegação em codebases através de grafos de conhecimento estruturados (`graph.json`), eliminando leituras cegas de diretórios.

---

## 🤖 Plugin Enterprise Multi-Agent (`enterprise-multiagent`)

O repositório inclui a frota corporativa de subagentes e portões determinísticos:

| Subagente | Modelo | Papel & Especialidade |
|---|---|---|
| **`flash-explorer`** | `Gemini Flash` | Reconhecimento rápido de código (read-only), rastreamento de AST/dependências e triagem de logs sem poluir a janela de contexto. |
| **`flash-implementer`** | `Gemini Flash` | Implementação de escopo delimitado (*Bounded Context*) com validação unitária local (Shift-Left) e menor diff funcional (Ponytail). |
| **`flash-qa-gatekeeper`** | `Gemini Flash` | **Falsification Mindset**: tentativa ativa de falsificar a implementação via testes de borda (BVA, EP), suites de regressão e Quality Gates determinísticos. |
| **`flash-security-auditor`** | `Gemini Flash` | Threat Modeling e auditoria adversarial (OWASP, segredos, CWE-78, CWE-89, CWE-22, gates clínicos) com classificação de explorabilidade. |

---

## 🧰 Skills Incluídas

| Skill | Descrição |
|---|---|
| **`caveman`** | Ultra-compressão de saída; resposta telegráfica com preservação técnica estrita. |
| **`ponytail`** | Princípio da menor intervenção funcional e código enxuto. |
| **`ponytail-audit`** | Auditoria de código, segurança, performance e detecção de código morto. |
| **`ponytail-debt`** | Gerenciador e extrator de dívida técnica e atalhos (`shortcut:` ledger). |
| **`ponytail-gain`** | Métricas de impacto, economia de tokens e linhas de código poupadas. |
| **`ponytail-review`** | Code review focado em simplicidade, segurança e completude. |
| **`ponytail-help`** | Referência rápida dos comandos e níveis Ponytail. |
| **`graphify`** | Transforma qualquer base de código em um grafo de conhecimento consultável via CLI. |

---

## 🚀 Instalação Rápida

### 1. Clonar e Instalar

```bash
git clone https://github.com/Rodriguesmath/antigravity-flow.git
cd antigravity-flow
./install.sh
```

O instalador automático:
- Cria a estrutura em `~/.gemini/`
- Instala as regras em `~/.gemini/config/rules/model-routing.md`
- Atualiza o link global `~/.gemini/GEMINI.md`
- Sincroniza todas as skills em `~/.gemini/config/skills/`
- Inicializa `~/.gemini/antigravity-cli/settings.json` com padrões otimizados (caso não exista).

### 2. Dependências Opcionais (Graphify)

Para habilitar a extração e consulta de grafos de código com a skill `graphify`:

```bash
pip install --user graphify-cli
# ou consulte: https://github.com/graphify
```

---

## 🔄 Sincronizando com Outro Computador

Para aplicar as mesmas configurações e skills em uma nova máquina:

1. No novo computador, clone o repositório e execute `./install.sh`.
2. Para manter seus computadores sincronizados com suas melhorias pessoais de fluxo, basta comitar suas alterações neste repositório:
```bash
git add .
git commit -m "feat(skills): update orchestration rules"
git push
```
E no outro PC:
```bash
cd antigravity-flow
git pull && ./install.sh
```

---

## 📂 Estrutura do Repositório

```text
antigravity-flow/
├── install.sh                  # Script de instalação e sincronização idempotente
├── LICENSE                     # Licença MIT
├── README.md                   # Documentação completa
└── config/
    ├── settings.json.example   # Template limpo de configurações do CLI
    ├── AGENTS.md               # Diretrizes globais de engenharia e orquestração
    ├── flags.json              # Feature flags do harness (Adaptive Sizing Gate)
    ├── rules/
    │   └── model-routing.md    # Regra mestra de orquestração adaptativa
    ├── skills/
    │   ├── caveman/            # Skill de compressão telegráfica
    │   ├── graphify/           # Suíte de visualização e consulta de grafos de código
    │   └── ponytail*/          # Suíte Ponytail (audit, debt, gain, review, help)
    └── plugins/
        └── enterprise-multiagent/
            ├── plugin.json     # Manifesto do plugin
            ├── hooks.json      # Hooks de auditoria e ciclo de vida
            ├── agents/         # Definições dos 4 subagentes Flash
            ├── rules/          # Regras operacionais do plugin
            ├── scripts/        # Task Sizing Gate, Execution Policy e Interceptor
            └── skills/         # Skill multiagent-orchestrator
```

---

## 🤝 Contribuições

Contribuições para novas skills, melhorias nos prompts de orquestração e refinamentos no protocolo de subagentes são bem-vindas! Sinta-se livre para abrir uma **Issue** ou enviar um **Pull Request**.

---

## 📄 Licença

Distribuído sob a licença [MIT](LICENSE).
