# Feature Specification: Busca de Tenant com Prompts, Guardrails e Base de Conhecimento

**Feature Branch**: `001-admin-tenant-management`
**Created**: 2026-08-19
**Status**: Draft
**Input**: User description: "Dado que eu tenho acesso ao PAINEL Administrador ao fazer login entrando na na tela de Painel Admnistrador - Adicionar Novo Tenant - permitir busca de tenant para mostrar os prompts relacionads e guadrails - permitir editar ou excluir a base de conhecimento para incluir uma nova"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Buscar tenant e visualizar prompts e guardrails vinculados (Priority: P1)

Um administrador autenticado no Painel Administrador, na tela onde hoje é possível adicionar um novo tenant, precisa localizar rapidamente um tenant já cadastrado e visualizar quais prompts e guardrails estão associados a ele, para entender ou validar como o assistente de IA está configurado para aquele cliente.

**Why this priority**: É a capacidade central solicitada e pré-requisito para as demais — sem localizar o tenant, não há como visualizar ou gerenciar sua base de conhecimento.

**Independent Test**: Pode ser testado isoladamente buscando por um tenant existente e verificando que os prompts e guardrails vinculados são exibidos corretamente, entregando valor de visibilidade mesmo sem as funcionalidades de edição da base de conhecimento.

**Acceptance Scenarios**:

1. **Given** o administrador está na tela do Painel Administrador com o campo de busca de tenant, **When** ele informa o nome ou identificador de um tenant existente e confirma a busca, **Then** o sistema exibe os dados do tenant encontrado junto com os prompts vinculados a ele e os guardrails associados a cada prompt.
2. **Given** o administrador busca por um termo que não corresponde a nenhum tenant cadastrado, **When** ele confirma a busca, **Then** o sistema exibe uma mensagem informando que nenhum tenant foi encontrado, sem erro de sistema.
3. **Given** o tenant encontrado não possui prompt personalizado vinculado, **When** o resultado da busca é exibido, **Then** o sistema indica claramente que o tenant utiliza o prompt padrão e mostra os guardrails globais aplicáveis.

---

### User Story 2 - Editar a base de conhecimento de um tenant (Priority: P2)

Após localizar um tenant, o administrador precisa atualizar as regras e informações institucionais (base de conhecimento) já cadastradas para aquele tenant, mantendo o assistente de IA alinhado com mudanças no negócio do cliente.

**Why this priority**: Mantém a base de conhecimento correta ao longo do tempo, evitando a necessidade de suporte técnico para cada ajuste de conteúdo.

**Independent Test**: Pode ser testado isoladamente localizando um tenant com base de conhecimento já cadastrada, alterando o conteúdo e confirmando que a nova versão é salva e reprocessada.

**Acceptance Scenarios**:

1. **Given** o administrador localizou um tenant que já possui base de conhecimento cadastrada, **When** ele visualiza e edita o conteúdo existente e salva a alteração, **Then** o sistema armazena o novo conteúdo como a base de conhecimento vigente do tenant e inicia o reprocessamento (revetorização) automaticamente.
2. **Given** o administrador está editando a base de conhecimento, **When** ele tenta salvar com o conteúdo vazio, **Then** o sistema impede o salvamento e exibe uma mensagem de validação.

---

### User Story 3 - Excluir a base de conhecimento de um tenant (Priority: P3)

O administrador precisa remover completamente a base de conhecimento de um tenant (por exemplo, para recadastrá-la do zero ou porque o conteúdo ficou obsoleto), com uma confirmação explícita para evitar remoções acidentais.

**Why this priority**: Ação destrutiva e menos frequente que a edição, mas necessária para permitir recomeçar a base de conhecimento de um tenant.

**Independent Test**: Pode ser testado isoladamente localizando um tenant com base de conhecimento cadastrada, solicitando a exclusão, confirmando a ação e verificando que o conteúdo deixa de existir para aquele tenant.

**Acceptance Scenarios**:

1. **Given** o tenant localizado possui base de conhecimento cadastrada, **When** o administrador solicita a exclusão e confirma a ação, **Then** o sistema remove o conteúdo vetorizado do tenant e passa a exibir a base de conhecimento como vazia.
2. **Given** o administrador solicitou a exclusão da base de conhecimento, **When** ele cancela a confirmação, **Then** nenhuma alteração é realizada e o conteúdo original permanece intacto.

---

### User Story 4 - Cadastrar nova base de conhecimento para um tenant (Priority: P3)

Quando um tenant localizado ainda não possui base de conhecimento (ou ela foi excluída), o administrador precisa cadastrar um novo conteúdo diretamente a partir da mesma tela de busca.

**Why this priority**: Complementa as ações de edição/exclusão, fechando o ciclo de gestão da base de conhecimento no mesmo fluxo, mas depende de a busca (US1) já existir.

**Independent Test**: Pode ser testado isoladamente localizando um tenant sem base de conhecimento, inserindo um novo texto de regras e confirmando que a base de conhecimento passa a existir para aquele tenant.

**Acceptance Scenarios**:

1. **Given** o tenant localizado não possui base de conhecimento cadastrada, **When** o administrador insere um novo texto de regras e salva, **Then** o sistema cria a base de conhecimento vetorizada para aquele tenant e passa a exibi-la como conteúdo vigente.

---

### Edge Cases

- O que acontece quando o administrador busca usando um termo muito curto ou apenas caracteres especiais? O sistema deve orientar o preenchimento sem retornar erro.
- Como o sistema trata a busca por um tenant inativo ou excluído (soft delete)? Deve ser possível localizá-lo, com uma indicação visual clara do status.
- O que acontece se o reprocessamento (revetorização) da base de conhecimento falhar após uma edição, exclusão ou criação? O administrador deve ser informado do status de falha e poder tentar novamente.
- Como o sistema se comporta se dois administradores editarem a base de conhecimento do mesmo tenant ao mesmo tempo? A última gravação confirmada prevalece, sem travar a tela para os demais.
- O que é exibido quando um tenant não possui nenhum guardrail global nem vinculado?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST permitir que o administrador busque um tenant por nome ou identificador a partir da tela do Painel Administrador onde hoje é possível adicionar um novo tenant.
- **FR-002**: O sistema MUST exibir, para o tenant encontrado, os prompts vinculados a ele, incluindo a indicação de que o prompt padrão está em uso quando não houver personalização.
- **FR-003**: O sistema MUST exibir os guardrails associados a cada prompt do tenant encontrado, incluindo guardrails globais aplicáveis.
- **FR-004**: O sistema MUST informar de forma clara ao administrador quando a busca não retornar nenhum tenant correspondente.
- **FR-005**: O sistema MUST exibir o conteúdo atual da base de conhecimento do tenant encontrado, quando existente.
- **FR-006**: O sistema MUST permitir que o administrador edite o conteúdo da base de conhecimento de um tenant que já a possua.
- **FR-007**: O sistema MUST permitir que o administrador exclua a base de conhecimento de um tenant, mediante confirmação explícita antes da remoção definitiva.
- **FR-008**: O sistema MUST permitir que o administrador cadastre uma nova base de conhecimento para um tenant que não a possua.
- **FR-009**: O sistema MUST impedir o salvamento de uma base de conhecimento com conteúdo vazio.
- **FR-010**: O sistema MUST reprocessar (revetorizar) automaticamente a base de conhecimento sempre que ela for criada ou editada, e informar ao administrador o status desse processamento.
- **FR-011**: O sistema MUST manter os prompts e guardrails exibidos nesta tela de busca em modo somente leitura; a criação e edição desses itens continuam ocorrendo na área de gestão de prompts já existente.
- **FR-012**: O acesso à busca de tenant e à gestão da base de conhecimento MUST estar restrito a administradores autenticados com acesso ao Painel Administrador.

### Key Entities *(include if feature involves data)*

- **Tenant**: Cliente cadastrado no sistema; possui identificador, nome, domínios permitidos e status (ativo/inativo/excluído). É a entidade central pela qual o administrador busca.
- **Prompt**: Instrução operacional usada pelo assistente de IA; pode ser padrão (global) ou personalizado e vinculado a um tenant específico.
- **Guardrail**: Regra de restrição aplicada a um prompt para orientar ou limitar o comportamento do assistente de IA; pode ser global ou específica de um prompt.
- **Base de Conhecimento**: Conteúdo textual único por tenant, contendo regras e informações institucionais usadas pelo assistente de IA para respostas contextualizadas; cada tenant possui no máximo um conteúdo vigente por vez.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O administrador localiza um tenant existente e visualiza seus prompts e guardrails vinculados em até 10 segundos após confirmar a busca.
- **SC-002**: 100% das buscas por tenant inexistente resultam em mensagem clara ao administrador, sem exibir erro de sistema.
- **SC-003**: O administrador consegue editar, excluir ou cadastrar a base de conhecimento de um tenant em uma única sessão, sem necessidade de suporte técnico.
- **SC-004**: 100% das exclusões de base de conhecimento exigem confirmação explícita do administrador antes de serem efetivadas.
- **SC-005**: Alterações na base de conhecimento (criação, edição ou exclusão) ficam refletidas no comportamento do assistente de IA do tenant em até 5 minutos após a confirmação da ação.

## Assumptions

- Esta funcionalidade entrega apenas os endpoints de API necessários para o Painel Administrador operar; a interface (tela) do Painel Administrador é construída e mantida em uma aplicação separada, que já existe como serviço próprio na infraestrutura e consome esses endpoints — não faz parte do escopo de implementação deste repositório.
- O acesso e a autenticação ao Painel Administrador já existem e estão fora do escopo desta funcionalidade — o administrador já parte do princípio de que possui esse acesso.
- FR-012 descreve o estado desejado (acesso restrito a administradores autenticados), mas sua aplicação **no backend** depende de uma feature futura de autenticação de administrador (hoje inexistente); nesta entrega, a restrição de acesso continua sendo feita apenas pelo próprio Painel Administrador no frontend, como já ocorre com as demais rotas administrativas existentes.
- A base de conhecimento de cada tenant é tratada como um conteúdo único de texto corrido por tenant (consistente com o mecanismo atual de ingestão), e não como uma lista de itens individuais.
- Os prompts e guardrails exibidos na tela de busca são somente leitura; a criação e edição desses itens permanece na área de gestão de prompts já existente, fora do escopo desta funcionalidade.
- A busca de tenant aceita nome ou identificador, com correspondência parcial e sem diferenciação entre maiúsculas/minúsculas.
- Excluir a base de conhecimento remove apenas o conteúdo vetorizado associado, sem afetar o cadastro do tenant, seus prompts ou seus guardrails.
- O reprocessamento (revetorização) da base de conhecimento após uma alteração ocorre de forma assíncrona, e o painel comunica ao administrador o status desse processamento (em andamento, concluído ou falho).
