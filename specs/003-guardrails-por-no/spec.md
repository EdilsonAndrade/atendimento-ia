# Feature Specification: Guardrails Independentes por Nó (Operational, Institutional, Chitchat)

**Feature Branch**: `edilsonaandrade/edi-42-permitir-associar-guardrails-ao-chitchat_node`
**Created**: 2026-08-20
**Status**: Draft
**Ticket**: EDI-42
**Input**: User description: "Como usuário administrativo, deve ser possível associar guardrails também ao `chitchat_node` e ao `institutional_node`. Na tela de associação de guardrails, o destino padrão deve continuar sendo o `operational_node`, como hoje. Deve haver uma opção para associar o guardrail também ao `chitchat_node`. Quando um guardrail for associado aos dois nós, os prompts de ambos devem incluir a tag `{guardrail}` para permitir a associação." Refinado em conversa: os três nós (`operational_node`, `institutional_node`, `chitchat_node`) passam a ter prompts e guardrails independentes entre si; `institutional_node` usa o prompt do `operational_node` como fallback quando não houver um próprio configurado; `chitchat_node` usa o texto fixo atual como fallback quando não houver um próprio configurado no banco.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Associar guardrails ao chitchat_node (Priority: P1)

Um administrador precisa restringir ou orientar o comportamento do assistente durante conversas casuais (chitchat) — hoje isso não é possível, pois o `chitchat_node` usa um texto fixo no código, sem nenhuma configuração vinda do painel administrativo.

**Why this priority**: É a necessidade que originou o ticket e a lacuna mais crítica — hoje o `chitchat_node` é o único nó sem nenhum guardrail configurável.

**Independent Test**: Pode ser testado associando um guardrail ao `chitchat_node` de um tenant, iniciando uma conversa casual e confirmando que a resposta do assistente respeita a nova regra, sem alterar o comportamento dos demais nós.

**Acceptance Scenarios**:

1. **Given** um tenant sem nenhum prompt de chitchat configurado, **When** o administrador associa um guardrail ao `chitchat_node` desse tenant, **Then** o sistema passa a aplicar esse guardrail nas conversas casuais do tenant.
2. **Given** um tenant com guardrails associados ao `operational_node`, **When** o administrador consulta os guardrails do `chitchat_node` desse mesmo tenant, **Then** o sistema não retorna os guardrails do `operational_node` como se fossem do `chitchat_node` (os conjuntos são independentes).
3. **Given** um tenant sem nenhum guardrail configurado para o `chitchat_node`, **When** uma conversa casual ocorre, **Then** o sistema aplica o comportamento padrão atual (fallback), sem erros para o usuário final.

---

### User Story 2 - Associar guardrails ao institutional_node de forma independente (Priority: P2)

Um administrador precisa configurar guardrails específicos para respostas institucionais (ex.: perguntas sobre endereço, políticas, regras da empresa) que sejam diferentes dos guardrails usados no fluxo operacional (agendamento), algo que hoje não é possível porque o `institutional_node` sempre reaproveita os mesmos guardrails do `operational_node`.

**Why this priority**: Também mencionado explicitamente no ticket; depende do mesmo modelo de dados da User Story 1, mas é uma necessidade secundária em relação ao chitchat.

**Independent Test**: Pode ser testado associando um guardrail apenas ao `institutional_node` de um tenant que já possui guardrails no `operational_node`, fazendo uma pergunta institucional e confirmando que apenas o guardrail do `institutional_node` é aplicado.

**Acceptance Scenarios**:

1. **Given** um tenant com um prompt institucional próprio configurado, **When** o administrador associa um guardrail a esse prompt, **Then** apenas as respostas do `institutional_node` passam a respeitar esse guardrail — as respostas do `operational_node` e `chitchat_node` não são afetadas.
2. **Given** um tenant que ainda não possui um prompt institucional próprio, **When** uma pergunta institucional é feita, **Then** o sistema aplica o prompt e os guardrails atualmente configurados para o `operational_node` desse tenant (fallback).

---

### User Story 3 - Continuidade de atendimento durante a transição (Priority: P3)

Como o sistema já está em produção atendendo tenants reais, a introdução de prompts independentes por nó não pode interromper ou degradar o atendimento de tenants já configurados enquanto o administrador ainda não configurou nada para os novos nós.

**Why this priority**: É uma garantia de não-regressão que sustenta as duas histórias anteriores, mas não introduz capacidade nova por si só.

**Independent Test**: Pode ser testado verificando, para um tenant já existente antes da mudança, que as respostas do `operational_node`, `institutional_node` e `chitchat_node` continuam idênticas ao comportamento anterior até que o administrador configure algo nos novos nós.

**Acceptance Scenarios**:

1. **Given** um tenant configurado antes desta funcionalidade existir, **When** o sistema entra em operação com a nova modelagem, **Then** o `institutional_node` desse tenant passa a ter automaticamente um prompt próprio equivalente ao seu prompt operacional atual, e o `chitchat_node` continua funcionando com o texto padrão atual.
2. **Given** um tenant sem qualquer vínculo de prompt configurado (usa apenas os padrões globais), **When** qualquer um dos três nós é acionado, **Then** o sistema responde normalmente, sem erros, usando os respectivos fallbacks.

---

### Edge Cases

- O que acontece quando um guardrail marcado como global (`is_global = TRUE`) é criado? Deve continuar sendo aplicado automaticamente a todos os nós (`operational_node`, `institutional_node`, `chitchat_node`), sem necessidade de associação manual.
- O que acontece se o administrador associar um guardrail a um prompt cujo texto não contém a tag de substituição de guardrails? O guardrail fica associado, mas não aparece na mensagem final enviada ao modelo para aquele prompt — o salvamento não é bloqueado.
- O que acontece se o administrador vincular um tenant a um novo prompt do `chitchat_node`? Isso não pode desativar o vínculo ativo do tenant com o prompt do `operational_node` ou do `institutional_node` (cada nó tem seu próprio vínculo ativo, independente dos demais).
- O que acontece com um tenant que tem prompt institucional configurado e depois esse vínculo é removido? O sistema volta a aplicar o fallback (prompt do `operational_node`) automaticamente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE permitir associar um ou mais guardrails a um prompt do `operational_node` de um tenant, mantendo o comportamento atual como padrão.
- **FR-002**: O sistema DEVE permitir associar um ou mais guardrails a um prompt do `institutional_node` de um tenant, de forma independente dos guardrails do `operational_node`.
- **FR-003**: O sistema DEVE permitir associar um ou mais guardrails a um prompt do `chitchat_node` de um tenant, de forma independente dos guardrails dos demais nós.
- **FR-004**: Quando um tenant não possuir um prompt próprio configurado para o `institutional_node`, o sistema DEVE utilizar o prompt e os guardrails atualmente ativos no `operational_node` desse tenant.
- **FR-005**: Quando um tenant não possuir um prompt próprio configurado para o `chitchat_node`, o sistema DEVE utilizar o texto padrão de fallback atualmente embutido no sistema, preservando o comportamento hoje existente.
- **FR-006**: O sistema DEVE prover, para tenants já configurados antes desta funcionalidade, um prompt inicial do `institutional_node` equivalente ao prompt atual do `operational_node`, editável de forma independente a partir de então.
- **FR-007**: O sistema DEVE prover um prompt inicial do `chitchat_node` equivalente ao texto atualmente fixo no código, armazenado de forma editável, sem exigir configuração manual para manter o comportamento atual.
- **FR-008**: O conteúdo de um prompt DEVE poder incluir uma tag de substituição que represente o conjunto de guardrails associados a ele, para que sejam incluídos na mensagem enviada ao modelo de IA.
- **FR-009**: O sistema DEVE manter, para cada tenant, um vínculo ativo independente por nó (`operational_node`, `institutional_node`, `chitchat_node`) — associar ou atualizar o prompt de um nó NÃO DEVE desativar o vínculo ativo dos demais nós desse tenant.
- **FR-010**: O sistema DEVE continuar aplicando automaticamente todos os guardrails marcados como globais a qualquer nó, independentemente de associação explícita a um prompt.

### Key Entities *(include if feature involves data)*

- **Prompt**: template de instrução usado pelo assistente de IA; passa a estar associado a um nó de destino (`operational_node`, `institutional_node` ou `chitchat_node`) além do tenant; pode conter a tag de substituição de guardrails.
- **Guardrail**: regra reutilizável de restrição/comportamento aplicada às respostas do assistente; pode ser global (aplicada a todos os nós automaticamente) ou vinculada explicitamente a um ou mais prompts específicos.
- **Vínculo Tenant-Prompt**: relação entre um tenant e o prompt ativo para um determinado nó; cada tenant possui um vínculo ativo independente por nó.
- **Nó de Destino**: identifica em qual etapa do atendimento (`operational_node`, `institutional_node`, `chitchat_node`) um prompt e seus guardrails associados são aplicados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um administrador consegue configurar guardrails exclusivos do `chitchat_node` sem que isso altere o comportamento do `operational_node` ou do `institutional_node`.
- **SC-002**: Um administrador consegue configurar guardrails exclusivos do `institutional_node` sem que isso altere o comportamento do `operational_node` ou do `chitchat_node`.
- **SC-003**: 100% dos tenants já configurados continuam recebendo, no `operational_node` e no `institutional_node`, exatamente os mesmos guardrails que recebiam antes da mudança, sem necessidade de reconfiguração manual.
- **SC-004**: Em 100% dos casos em que um nó não possui prompt próprio configurado, o sistema aplica o fallback correspondente sem gerar erro perceptível para o usuário final da conversa.
- **SC-005**: A alteração de vínculo de prompt em um nó nunca desativa o vínculo ativo dos outros dois nós do mesmo tenant (0% de interferência cruzada entre nós).

## Assumptions

- A interface administrativa ("tela de associação de guardrails") citada no ticket é implementada em outro repositório (frontend); este repositório entrega apenas o backend (API e modelo de dados) que a suporta.
- O `operational_node` mantém seu comportamento e prompt atuais sem alteração funcional — a mudança é aditiva para os outros dois nós.
- Guardrails marcados como globais continuam sendo aplicados a todos os nós automaticamente, sem necessidade de associação explícita, como já ocorre hoje.
- A criação dos prompts iniciais (seed) do `institutional_node` e do `chitchat_node` para tenants já existentes é feita automaticamente pelo sistema, sem exigir ação manual do administrador.
- A ausência da tag de substituição de guardrails no texto de um prompt não impede o salvamento do prompt; apenas resulta nos guardrails associados não sendo incluídos na mensagem final enviada ao modelo.
