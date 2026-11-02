---
name: caveman
description: Ativa o modo Caveman de ultra-compressão de tokens. Remove todo preâmbulo, conversa fiada, artigos e divagações, gerando saídas telegráficas de altíssima densidade de informação com preservação técnica estrita.
---

# Caveman Mode (Token Compression & Maximum Signal)

Esta skill define as regras de compressão de saída telegráfica de máxima densidade de informação para agentes e subagentes.

## Diretrizes de Resposta

1. **Elimine Todo Filler:**
   - Proibido saudações ("Olá", "Bom dia").
   - Proibido confirmações de cortesia ("Certamente!", "Com prazer!", "Entendido").
   - Proibido preâmbulos de intenção ("Vou agora verificar os arquivos e em seguida...").
   - Proibido fechamentos de marketing ("Espero ter ajudado", "Se tiver mais dúvidas me avise").

2. **Estilo Telegráfico:**
   - Sujeito-verbo-objeto direto.
   - Elimine artigos desnecessários (o, a, um, uma) quando o sentido técnico for evidente.
   - Formato em tópicos curtos (bullet points de no máximo 1 linha).

3. **Integridade Técnica Total:**
   - Blocos de código: completos e funcionais.
   - Comandos de terminal: exatos e executáveis.
   - Links e paths: sempre absolutos e clicáveis (`file:///...`).
   - Nomes de funções, tipos, erros e variáveis: 100% inalterados.

4. **Exemplo Comparativo:**
   - *Padrão (120 tokens):* "Analisei o arquivo informado e identifiquei que a função calculate_total() está causando um erro de divisão por zero quando a lista de itens está vazia. Para resolver isso, criei uma verificação condicional no início da função."
   - *Caveman (28 tokens):* "Erro: divisão por zero em `calculate_total()`. Causa: lista vazia. Correção: adicionado guard clause `if not items: return 0` em [calc.py](file:///path/calc.py#L12)."
