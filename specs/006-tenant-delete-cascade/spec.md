# Feature Specification: Exclusão segura de tenant com desvínculo/exclusão em cascata de prompts e guardrails

**Feature Branch**: `edilsonaandrade/edi-45-backend-exclusao-segura-de-tenant-com-desvinculoexclusao-em`
**Created**: 2026-08-22
**Status**: Draft
**Input**: User description: "Backend: exclusão segura de tenant com desvínculo/exclusão em cascata de prompts e guardrails (EDI-45) — ao excluir um tenant, o sistema deve deletar de fato os prompts e guardrails que forem exclusivos daquele tenant, e apenas desvincular os que forem compartilhados com outros tenants/prompts ou marcados como globais, avaliando prompt e guardrail de forma independente, tudo em uma operação atômica, sem deixar registros órfãos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Excluir tenant com prompt e guardrail exclusivos (Priority: P1)

Um administrador exclui um tenant cujo prompt e guardrail associados não são usados por nenhum outro tenant ou prompt. O sistema remove o tenant e também deleta de fato o prompt e o guardrail, já que não pertencem mais a nada.

**Why this priority**: É o cenário mais comum e o que hoje mais gera lixo de dados (prompts/guardrails órfãos, sem tenant e sem uso), pois a exclusão atual não avalia nada disso.

**Independent Test**: Criar um tenant com prompt e guardrail exclusivos a ele, excluí-lo, e verificar que tenant, prompt e guardrail deixaram de existir.

**Acceptance Scenarios**:

1. **Given** um tenant com um prompt vinculado que não está associado a nenhum outro tenant, **When** o tenant é excluído, **Then** o tenant e o prompt são removidos.
2. **Given** um tenant cujo prompt tem um guardrail vinculado que não é global e não está associado a nenhum outro prompt, **When** o tenant é excluído, **Then** o guardrail também é removido.

---

### User Story 2 - Excluir tenant com prompt compartilhado (Priority: P1)

Um administrador exclui um tenant cujo prompt também está vinculado a outros tenants. O sistema remove o tenant e desfaz apenas o vínculo daquele tenant com o prompt, preservando o prompt para os demais tenants que ainda o utilizam.

**Why this priority**: Impedir que a exclusão de um tenant quebre o atendimento de outros tenants que compartilham o mesmo prompt é crítico — é o principal risco de uma exclusão em cascata mal feita.

**Independent Test**: Vincular o mesmo prompt a dois tenants, excluir um deles, e verificar que o prompt continua íntegro e associado ao tenant remanescente.

**Acceptance Scenarios**:

1. **Given** um prompt vinculado a dois ou mais tenants, **When** um desses tenants é excluído, **Then** apenas o vínculo daquele tenant com o prompt é removido e o prompt permanece intacto para os demais.

---

### User Story 3 - Excluir tenant com guardrail global ou compartilhado (Priority: P1)

Um administrador exclui um tenant cujo prompt tem um guardrail marcado como global, ou vinculado também a prompts de outros tenants. O sistema remove o tenant e o vínculo, mas preserva o guardrail, pois ele continua servindo outros tenants/prompts (ou a plataforma como um todo, no caso de global).

**Why this priority**: Guardrails globais protegem todos os tenants da plataforma; excluí-los por engano ao apagar um único tenant seria uma falha de segurança grave.

**Independent Test**: Marcar um guardrail como global (ou vinculá-lo a um prompt de outro tenant), excluir um tenant cujo prompt usa esse guardrail, e verificar que o guardrail continua existindo e aplicado normalmente.

**Acceptance Scenarios**:

1. **Given** um guardrail marcado como global vinculado ao prompt de um tenant, **When** esse tenant é excluído, **Then** apenas o vínculo é removido e o guardrail continua existindo e sendo aplicado globalmente.
2. **Given** um guardrail vinculado a prompts de dois tenants diferentes (nenhum deles global), **When** um dos tenants é excluído, **Then** o guardrail permanece, pois ainda está em uso pelo prompt do outro tenant.

---

### User Story 4 - Consultar o impacto antes de confirmar a exclusão (Priority: P2)

Antes de confirmar a exclusão de um tenant, um administrador (através de uma interface administrativa) precisa saber exatamente o que vai ser excluído de fato e o que vai ser apenas desvinculado, para poder confirmar a ação com segurança.

**Why this priority**: Sem essa visibilidade prévia, a exclusão em cascata vira uma caixa-preta arriscada para quem está operando o sistema — mas o sistema já garante o comportamento correto mesmo sem essa consulta (por isso P2, não P1).

**Independent Test**: Solicitar o impacto de uma exclusão para um tenant com combinação mista (prompt exclusivo + guardrail global), e confirmar que a resposta indica corretamente o que será excluído e o que será apenas desvinculado, batendo com o resultado real após a exclusão.

**Acceptance Scenarios**:

1. **Given** um tenant com prompt exclusivo e guardrail global, **When** o impacto da exclusão é consultado antes de confirmar, **Then** o resultado indica que o prompt será excluído e o guardrail será apenas desvinculado.
2. **Given** o impacto consultado para um tenant, **When** a exclusão é de fato executada em seguida, **Then** o resultado real bate exatamente com o que foi informado na consulta prévia.

---

### Edge Cases

- Tenant sem nenhum prompt ou guardrail vinculado é excluído normalmente, sem nenhuma limpeza adicional necessária.
- Um guardrail vinculado a múltiplos prompts, onde um desses prompts fica órfão pela exclusão e outro pertence a um tenant que permanece: o guardrail deve ser preservado.
- Um guardrail é simultaneamente global E vinculado a outro prompt: qualquer uma das duas condições já é suficiente para preservá-lo.
- A exclusão falha no meio do processo (ex.: erro de sistema): nenhuma alteração parcial deve persistir — nem o tenant, nem os prompts/guardrails devem ser afetados.
- Tentativa de excluir um tenant que não existe: deve retornar um erro claro, sem efeito colateral algum.
- Prompt ou guardrail vinculado ao tenant através de um vínculo inativo (não é o vínculo ativo atual do tenant): também deve ser considerado na avaliação de exclusividade e limpo junto com o tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE permitir que um administrador exclua um tenant.
- **FR-002**: Ao excluir um tenant, o sistema DEVE identificar todos os prompts vinculados a ele (vínculos ativos e inativos).
- **FR-003**: Para cada prompt vinculado, o sistema DEVE determinar se ele é usado exclusivamente pelo tenant sendo excluído ou se é compartilhado com outro(s) tenant(s).
- **FR-004**: Quando um prompt for exclusivo do tenant sendo excluído, o sistema DEVE excluir esse prompt de fato como parte da exclusão do tenant.
- **FR-005**: Quando um prompt for compartilhado com outro(s) tenant(s), o sistema DEVE remover apenas o vínculo entre o tenant excluído e o prompt, preservando o prompt intacto para os demais.
- **FR-006**: Para cada guardrail vinculado a um prompt do tenant, o sistema DEVE avaliar sua exclusividade de forma **independente** do destino do prompt (o guardrail pode ser preservado mesmo que o prompt ao qual está vinculado seja excluído, e vice-versa).
- **FR-007**: Quando um guardrail não for global e não estiver vinculado a nenhum outro prompt, o sistema DEVE excluí-lo de fato.
- **FR-008**: Quando um guardrail for global, ou estiver vinculado a outro(s) prompt(s) além do(s) do tenant excluído, o sistema DEVE preservá-lo e remover apenas a associação correspondente ao tenant excluído.
- **FR-009**: O sistema DEVE executar a exclusão do tenant e toda a limpeza/desvínculo de prompts e guardrails associados como uma **única operação atômica** — se qualquer etapa falhar, nenhuma alteração deve ser persistida.
- **FR-010**: O sistema DEVE oferecer uma forma de consultar, antes da exclusão ser efetivada, quais prompts e guardrails serão excluídos de fato versus apenas desvinculados, para que uma interface administrativa possa exibir essa informação a quem for confirmar a ação.
- **FR-011**: O sistema NÃO DEVE deixar registros de associação órfãos (referenciando um tenant que não existe mais) após a exclusão de um tenant.
- **FR-012**: O sistema DEVE retornar um erro claro ao tentar excluir um tenant que não existe, sem produzir nenhum efeito colateral.

### Key Entities *(include if feature involves data)*

- **Tenant**: cliente/organização atendido pelo sistema; possui vínculos com prompts.
- **Prompt**: conteúdo de comportamento/identidade que pode ser vinculado a um ou mais tenants; pode ter guardrails associados.
- **Guardrail**: política de segurança aplicada a um prompt; pode ser marcada como global (aplicada a todos os tenants automaticamente) ou vinculada a um ou mais prompts específicos.
- **Vínculo Tenant-Prompt**: associação entre um tenant e um prompt, podendo estar ativa ou inativa (histórica).
- **Vínculo Prompt-Guardrail**: associação entre um prompt e um guardrail.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das exclusões de tenant não deixam nenhum registro de associação órfão (auditável após a operação).
- **SC-002**: 100% das consultas de impacto pré-exclusão correspondem exatamente ao resultado real observado após a exclusão ser efetivada.
- **SC-003**: Prompts e guardrails exclusivos de um tenant são completamente removidos em 100% das exclusões desse tenant.
- **SC-004**: Prompts e guardrails compartilhados ou globais nunca são removidos ao excluir um tenant que os compartilha — 0 incidentes de perda de dados entre tenants.
- **SC-005**: Uma exclusão que falha no meio do processo deixa o sistema exatamente no estado anterior em 100% dos casos (nenhuma alteração parcial).

## Assumptions

- "Exclusivo" significa que nenhum outro tenant possui vínculo (ativo ou inativo) com aquele prompt, e nenhum outro prompt possui vínculo com aquele guardrail.
- A exclusividade de um guardrail é avaliada de forma independente da exclusividade do prompt ao qual ele está vinculado no momento da exclusão — um tenant pode ter prompt exclusivo com guardrail compartilhado/global, ou o inverso.
- A funcionalidade de consulta de impacto (FR-010) é pensada para ser consumida por uma interface administrativa externa (acompanhada por um ticket de frontend à parte); esta especificação cobre apenas a capacidade do sistema de fornecer essa informação.
- A exclusão de tenant continua restrita a administradores, sem novas regras de autorização além das já existentes para gestão de tenants.
- Não há requisito de "lixeira" ou exclusão reversível — a exclusão é definitiva assim que confirmada.
