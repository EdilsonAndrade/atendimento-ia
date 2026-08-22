# Feature Specification: Vínculo explícito de prompt e guardrails globais no runtime

**Feature Branch**: `edilsonaandrade/edi-43-backend-eliminar-fallback-implicito-de-prompt-e-aplicar`
**Created**: 2026-08-22
**Status**: Draft
**Linear**: [EDI-43](https://linear.app/edilsonandrade/issue/EDI-43/backend-eliminar-fallback-implicito-de-prompt-e-aplicar) — relacionado: EDI-44 (frontend)
**Input**: Eliminar o fallback implícito de prompt no runtime do agente e aplicar guardrails globais em todos os caminhos de resolução.

## Contexto do Problema

A resolução de prompts e guardrails em tempo de atendimento usa fallbacks implícitos que entregam a um tenant conteúdo que não foi configurado para ele, sem que ninguém perceba (falha silenciosa em modo aberto). Dois defeitos concretos:

**1. Guardrails globais não alcançam o tenant sem vínculo de prompt.** Quando o tenant não tem prompt ativo, a resolução retorna direto o arquivo local de guardrails e nunca consulta os guardrails marcados como globais no banco. Na prática, "guardrail global" significa hoje "global para quem já tem prompt vinculado" — e o tenant novo, justamente quem mais precisa da rede de proteção padrão, fica sem.

**2. Divergência entre o que a tela mostra e o que o agente usa.** Para um tenant sem vínculo, a API de visão geral resolve pelo banco (prompt padrão + guardrails globais), enquanto o atendimento resolve pelos arquivos locais do projeto. O administrador abre a tela, vê o guardrail global listado para aquele tenant, e o agente em produção nunca o recebe.

## Decisão de Arquitetura

Separar dois conceitos hoje tratados como se fossem o mesmo:

| Conceito | Natureza | Comportamento |
| -- | -- | -- |
| **Prompt** | Identidade e comportamento do cliente | **Seletivo.** Sem fallback implícito — um tenant herdar prompt de outro contexto por omissão é o risco central desta feature. A marcação de "padrão" deixa de ser mecanismo de resolução em tempo de atendimento. |
| **Guardrail** | Política de segurança da plataforma | **Aditivo.** A marcação de "global" é legítima e continua. O problema nunca foi ela existir — foi ela ser invisível em vez de ser global de verdade. |

Os arquivos de texto do projeto deixam de ser fonte de verdade em tempo de atendimento e passam a ser **fonte de semente**: alimentam o banco na primeira inicialização e permanecem acessíveis apenas como contingência de indisponibilidade do banco.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guardrails globais alcançam todo tenant (Priority: P1)

O administrador marca um guardrail como global esperando que ele proteja todos os clientes da plataforma. Hoje, os tenants sem prompt vinculado ficam de fora sem qualquer aviso. Esta história faz o "global" valer para todo mundo, inclusive no caminho de erro de configuração.

**Why this priority**: É o defeito de segurança. Um guardrail global é uma política de plataforma — se ela não chega a parte dos tenants, a plataforma acredita estar protegida e não está. Entrega valor sozinha, mesmo sem nenhuma das outras histórias.

**Independent Test**: Configurar um guardrail global, disparar um atendimento para um tenant sem prompt vinculado e verificar que o texto do guardrail chegou ao conteúdo enviado ao modelo.

**Acceptance Scenarios**:

1. **Given** um tenant sem prompt vinculado e um guardrail marcado como global no banco, **When** o agente resolve o conteúdo para atender esse tenant, **Then** o texto do guardrail global está presente no resultado.
2. **Given** um tenant com prompt vinculado e guardrails próprios, mais um guardrail global, **When** o agente resolve o conteúdo, **Then** os guardrails próprios e o global estão todos presentes, sem duplicação de texto.
3. **Given** um mesmo tenant, **When** o administrador consulta a visão geral na tela e o agente resolve o conteúdo para atendimento, **Then** o conjunto de guardrails é idêntico nos dois caminhos.
4. **Given** um tenant sem prompt vinculado e nenhum guardrail global cadastrado, **When** o agente resolve o conteúdo, **Then** o resultado não contém texto de guardrail vindo de arquivo local.

---

### User Story 2 - Erro de configuração deixa de ser silencioso (Priority: P1)

Um tenant sem prompt operacional vinculado é um erro de configuração, não um estado normal de operação. Hoje esse caso é absorvido silenciosamente por um texto genérico do projeto, e ninguém descobre. Esta história transforma o caso em falha explícita e rastreável.

**Why this priority**: É o risco central da feature — um cliente receber comportamento que não é o dele. Precisa vir junto com a História 1 porque as duas alteram o mesmo ponto de resolução.

**Independent Test**: Remover o vínculo de prompt operacional de um tenant, disparar um atendimento e verificar que o sistema registra um alerta identificando o tenant, em vez de responder com o texto genérico do projeto.

**Acceptance Scenarios**:

1. **Given** um tenant sem prompt operacional vinculado, **When** o agente tenta resolver o conteúdo para atendimento, **Then** o sistema sinaliza erro de configuração com um registro rastreável que identifica o tenant afetado.
2. **Given** o mesmo cenário, **When** o erro é sinalizado, **Then** os guardrails globais ainda são resolvidos e aplicados — a política de segurança não falha junto com o prompt.
3. **Given** um tenant sem prompt operacional vinculado, **When** o agente resolve o conteúdo, **Then** em nenhuma hipótese o texto do arquivo local de prompt é usado como substituto.
4. **Given** o banco de dados indisponível, **When** o agente resolve o conteúdo para qualquer tenant, **Then** o conteúdo dos arquivos locais é usado como contingência e o atendimento continua funcionando.

---

### User Story 3 - Banco sempre nasce com o mínimo configurado (Priority: P2)

Numa instalação nova, o banco vazio faria a lista de prompts do cadastro de tenant aparecer sem nenhuma opção, e não haveria guardrail global algum. Esta história garante que a primeira inicialização já popula o mínimo necessário, a partir do conteúdo que hoje vive nos arquivos do projeto.

**Why this priority**: É pré-requisito prático das Histórias 1, 2 e 4 — sem ela, exigir vínculo de prompt num banco vazio deixa o administrador sem nada para escolher. Vem depois porque as duas primeiras já entregam valor num banco existente.

**Independent Test**: Subir a aplicação contra um banco vazio e verificar que a lista de prompts tem pelo menos uma opção por tipo de nó e que existe um guardrail global.

**Acceptance Scenarios**:

1. **Given** um banco vazio, **When** a aplicação inicializa pela primeira vez, **Then** existe pelo menos um prompt disponível para cada tipo de nó (operacional, institucional e conversa informal), com o conteúdo vindo dos arquivos do projeto.
2. **Given** um banco vazio, **When** a aplicação inicializa pela primeira vez, **Then** existe um guardrail marcado como global com o conteúdo do arquivo de guardrails do projeto.
3. **Given** um banco já semeado, **When** a aplicação inicializa novamente, **Then** nenhum registro é duplicado.
4. **Given** um administrador que editou o conteúdo de um prompt ou guardrail semeado, **When** a aplicação inicializa novamente, **Then** a edição do administrador é preservada — a semente nunca sobrescreve.
5. **Given** um banco vazio, **When** a aplicação inicializa, **Then** o conteúdo semeado preserva os marcadores de substituição dinâmica do texto, para que os guardrails continuem sendo injetados a cada atendimento em vez de ficarem congelados no texto.

---

### User Story 4 - Cadastro de tenant exige prompt e permite associação em massa (Priority: P2)

O administrador cadastra um tenant novo e o sistema passa a exigir a escolha do prompt operacional no mesmo ato. E, quando precisa aplicar um mesmo prompt a vários clientes, faz isso numa operação só em vez de repetir o vínculo um a um.

**Why this priority**: É o que impede o problema de voltar a acontecer para tenants novos. Depende da História 3 para ter o que oferecer na lista de escolha.

**Independent Test**: Cadastrar um tenant sem informar prompt e verificar que a operação é recusada; depois associar um prompt a três tenants numa única chamada e verificar os três vínculos ativos.

**Acceptance Scenarios**:

1. **Given** um cadastro de tenant sem prompt informado, **When** a criação é submetida, **Then** a operação é recusada com erro de validação e o tenant não é criado.
2. **Given** um cadastro de tenant com um prompt informado que não existe, **When** a criação é submetida, **Then** a operação é recusada identificando o motivo, e o tenant não é criado.
3. **Given** um cadastro de tenant com um prompt informado que existe mas não é do tipo operacional, **When** a criação é submetida, **Then** a operação é recusada identificando o motivo, e o tenant não é criado.
4. **Given** um cadastro válido, **When** a criação é submetida, **Then** o tenant e o vínculo do prompt são criados de forma atômica — não existe estado intermediário de tenant criado sem prompt.
5. **Given** um prompt e uma lista de vários tenants, **When** o administrador aplica a associação em massa, **Then** todos os tenants da lista ficam vinculados àquele prompt numa única operação.
6. **Given** uma associação em massa em que um dos tenants informados não existe, **When** a operação é submetida, **Then** nenhum vínculo é aplicado e a resposta identifica quais tenants não foram encontrados.
7. **Given** uma associação em massa de um prompt operacional a tenants que já possuem vínculos de outros tipos de nó, **When** a operação é aplicada, **Then** os vínculos dos outros tipos de nó permanecem intactos.

---

### User Story 5 - Exclusão não pode orfanar tenant nem remover proteção em silêncio (Priority: P2)

Exigir prompt no cadastro cobre os tenants novos, mas não impede que o vínculo seja destruído depois. Hoje, excluir um prompt remove em cascata os vínculos de todos os tenants que o usavam, sem aviso. Esta história fecha essa porta e faz o mesmo pelos guardrails.

**Why this priority**: Sem ela, o problema que as Histórias 2 e 4 resolvem pode ser reintroduzido por uma única exclusão na tela de administração.

**Independent Test**: Tentar excluir um prompt vinculado a um tenant e verificar que a operação é recusada com a lista de tenants bloqueadores; tentar excluir o guardrail global e verificar que a operação é recusada.

**Acceptance Scenarios**:

1. **Given** um prompt com vínculo ativo a um ou mais tenants, **When** o administrador tenta excluí-lo, **Then** a operação é recusada e a resposta lista quais tenants estão bloqueando.
2. **Given** um prompt sem nenhum vínculo ativo, **When** o administrador o exclui, **Then** a exclusão ocorre normalmente.
3. **Given** um guardrail marcado como global, **When** o administrador tenta excluí-lo, **Then** a operação é recusada indicando que ele precisa deixar de ser global antes.
4. **Given** um guardrail associado a um prompt que tem tenant ativo, **When** o administrador tenta excluí-lo, **Then** a operação é recusada e a resposta lista quais prompts estão bloqueando.
5. **Given** um guardrail que é global **e** está associado a um prompt em uso, **When** o administrador tenta excluí-lo, **Then** a recusa indica a condição de global, que é o bloqueio mais forte e o primeiro a ser resolvido.
6. **Given** um guardrail que não é global e não está associado a nenhum prompt em uso, **When** o administrador o exclui, **Then** a exclusão ocorre normalmente.

---

### Edge Cases

- **Banco indisponível durante o atendimento**: o conteúdo dos arquivos locais é usado como contingência para prompt e guardrails, e o atendimento não cai. Este é o único caminho em que os arquivos locais continuam sendo lidos em tempo de atendimento.
- **Distinguir "sem vínculo" de "banco fora do ar"**: são situações opostas — a primeira precisa falhar e alertar, a segunda precisa continuar atendendo. O sistema não pode tratar uma como a outra.
- **Guardrail global excluído e recriado pela semente**: como a semente só cria o que não existe, excluir o guardrail global faria ele reaparecer na inicialização seguinte. O bloqueio de exclusão evita esse comportamento confuso de "apaguei e voltou sozinho".
- **Guardrail contendo o marcador de substituição no próprio texto**: guardrail é conteúdo, nunca modelo de texto; o marcador não pode vazar literalmente para o conteúdo final nem disparar substituição em cascata.
- **Prompt sem o marcador de guardrails no texto**: prompts gravados antes desta correção podem ter os guardrails embutidos no corpo. Os guardrails resolvidos precisam chegar ao conteúdo final mesmo assim, em vez de sumirem.
- **Guardrail global com texto idêntico a um guardrail vinculado ao prompt**: o mesmo bloco de regras não pode aparecer duas vezes no conteúdo final.
- **Tenant sem vínculo em produção no momento do deploy**: precisam ser vinculados antes de a exigência entrar em vigor, senão o atendimento deles quebra.
- **Tenant sem vínculo dos nós institucional e de conversa informal**: continuam resolvendo pelas cadeias atuais (o institucional herda a resolução do operacional; a conversa informal usa o prompt padrão semeado). Só o nó operacional exige vínculo.

## Requirements *(mandatory)*

### Functional Requirements

**Resolução em tempo de atendimento**

- **FR-001**: O sistema MUST resolver os guardrails de um tenant sem prompt vinculado a partir dos guardrails marcados como globais no banco, em vez de retornar o conteúdo do arquivo local.
- **FR-002**: O sistema MUST usar uma única rotina de resolução compartilhada pelos três tipos de nó (operacional, institucional e conversa informal), em vez de repetir o padrão em cada um.
- **FR-003**: O sistema MUST resolver, para um mesmo tenant, exatamente o mesmo conjunto de guardrails na visão geral exibida ao administrador e no conteúdo entregue ao agente.
- **FR-004**: O sistema MUST sinalizar erro de configuração rastreável, identificando o tenant, quando não houver prompt operacional vinculado — em vez de assumir silenciosamente um conteúdo local.
- **FR-005**: O sistema MUST aplicar os guardrails globais mesmo quando o erro de FR-004 ocorre; a política de segurança não pode falhar junto com o prompt.
- **FR-006**: O sistema MUST NOT usar os arquivos locais como fonte de conteúdo em tempo de atendimento, exceto no caminho de contingência de FR-007.
- **FR-007**: O sistema MUST continuar usando o conteúdo dos arquivos locais quando o banco estiver indisponível, mantendo o atendimento em pé.
- **FR-008**: O sistema MUST manter as cadeias de resolução atuais dos nós institucional e de conversa informal — apenas o nó operacional passa a exigir vínculo explícito.
- **FR-009**: O sistema MUST evitar que o mesmo texto de guardrail apareça duas vezes no conteúdo final quando um guardrail global e um vinculado ao prompt tiverem conteúdo equivalente.
- **FR-010**: O sistema MUST garantir que os guardrails resolvidos cheguem ao conteúdo final mesmo quando o prompt não contiver o marcador de substituição.

**Semente a partir dos arquivos do projeto**

- **FR-011**: O sistema MUST criar, na inicialização, um prompt semente para cada tipo de nó, com o conteúdo lido do arquivo correspondente do projeto.
- **FR-012**: O sistema MUST criar, na inicialização, um guardrail marcado como global com o conteúdo do arquivo de guardrails do projeto.
- **FR-013**: O sistema MUST criar registros de semente apenas quando ainda não existirem, sem duplicar em execuções repetidas e sem sobrescrever conteúdo editado pelo administrador.
- **FR-014**: O sistema MUST gravar o conteúdo semeado preservando os marcadores de substituição dinâmica, para que os guardrails sejam injetados a cada atendimento em vez de ficarem congelados no texto.
- **FR-015**: O sistema MUST NOT impedir a inicialização da aplicação caso a semente falhe.

**Cadastro e vínculo**

- **FR-016**: O sistema MUST exigir a identificação de um prompt operacional na criação de um tenant, recusando a criação quando ele não for informado.
- **FR-017**: O sistema MUST recusar a criação de tenant quando o prompt informado não existir ou não for do tipo operacional, indicando qual das duas condições ocorreu.
- **FR-018**: O sistema MUST criar o tenant e o vínculo do prompt de forma atômica, sem deixar tenant criado sem vínculo em caso de falha parcial.
- **FR-019**: Administradores MUST be able to associar um mesmo prompt a vários tenants numa única operação.
- **FR-020**: O sistema MUST aplicar a associação em massa de forma atômica: se qualquer tenant informado não existir, nenhum vínculo é aplicado e a resposta identifica os tenants não encontrados.
- **FR-021**: O sistema MUST preservar, na associação em massa, os vínculos ativos dos demais tipos de nó de cada tenant.

**Proteção de exclusão**

- **FR-022**: O sistema MUST recusar a exclusão de um prompt que tenha vínculo ativo com algum tenant, e MUST identificar na resposta quais tenants bloqueiam a operação.
- **FR-023**: O sistema MUST recusar a exclusão de um guardrail marcado como global, indicando que a marcação precisa ser removida antes.
- **FR-024**: O sistema MUST recusar a exclusão de um guardrail associado a um prompt que tenha tenant ativo, e MUST identificar na resposta quais prompts bloqueiam a operação.
- **FR-025**: O sistema MUST tratar a condição de global como prioritária quando as duas condições de bloqueio de guardrail coexistirem.

**Contrato de erro para a interface administrativa**

- **FR-026**: O sistema MUST expor as recusas de regra de negócio num formato estruturado que inclua um código estável legível por máquina, uma mensagem exibível ao administrador e a lista dos itens que bloqueiam a operação.
- **FR-027**: O sistema MUST manter estável o código legível por máquina, de modo que a interface possa decidir o que exibir sem interpretar o texto da mensagem.

**Migração**

- **FR-028**: O sistema MUST associar, antes de a exigência de vínculo entrar em vigor, todos os tenants hoje sem vínculo operacional ao prompt que atualmente serve como padrão.
- **FR-029**: A migração MUST ser aplicada no mesmo procedimento de implantação que ativa a exigência, de modo que nenhum tenant existente fique em estado de erro.

### Key Entities

- **Tenant**: o cliente atendido pela plataforma. Passa a exigir, desde a criação, um vínculo com um prompt operacional.
- **Prompt**: o conteúdo que define a identidade e o comportamento do agente para um cliente, classificado por tipo de nó (operacional, institucional, conversa informal). Relaciona-se com tenants por um vínculo muitos-para-muitos, com no máximo um vínculo ativo por tenant por tipo de nó.
- **Guardrail**: a política de segurança aplicada ao conteúdo. Pode estar associada a prompts específicos ou marcada como global, caso em que se aplica a todos os tenants sem necessidade de associação manual.
- **Vínculo tenant-prompt**: a associação explícita entre um tenant e um prompt, com estado de ativo/inativo e possibilidade de conteúdo sobrescrito para aquele tenant.
- **Registros semente**: os prompts e o guardrail global criados na primeira inicialização a partir dos arquivos do projeto, garantindo que o banco nunca esteja vazio.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos tenants recebem os guardrails marcados como globais, incluindo os que não possuem prompt vinculado.
- **SC-002**: Para qualquer tenant, o conjunto de guardrails exibido na tela de administração é idêntico ao efetivamente aplicado no atendimento — zero divergência.
- **SC-003**: Nenhum atendimento usa conteúdo de arquivo local enquanto o banco estiver disponível.
- **SC-004**: Todo tenant sem prompt operacional vinculado produz um registro de alerta que identifica o tenant, permitindo ao operador localizar a configuração faltante sem precisar reproduzir o caso.
- **SC-005**: Com o banco indisponível, o atendimento continua respondendo — a indisponibilidade não gera falha visível ao usuário final.
- **SC-006**: Numa instalação nova, o administrador consegue cadastrar um tenant sem nenhuma configuração manual prévia, escolhendo entre as opções já disponíveis na lista.
- **SC-007**: Executar a inicialização repetidas vezes não altera a contagem de registros nem o conteúdo editado pelo administrador.
- **SC-008**: Associar um prompt a N tenants exige uma única operação, em vez de N operações.
- **SC-009**: Nenhuma exclusão na área administrativa consegue deixar um tenant sem prompt vinculado ou remover a proteção global em vigor.
- **SC-010**: Após a implantação, zero tenants existentes ficam em estado de erro de configuração.
- **SC-011**: A suíte de testes cobre os quatro cenários de resolução exigidos — sem vínculo com global, sem vínculo sem global, com vínculo mais global, e banco indisponível — além dos casos de bloqueio de exclusão.

## Assumptions

- Apenas o nó operacional exige vínculo explícito. Institucional e conversa informal mantêm suas cadeias de resolução atuais — decisão tomada com o solicitante para limitar o risco de regressão.
- O cadastro de tenant exige apenas o prompt operacional. Guardrail não é campo obrigatório em nenhum ponto: o guardrail global semeado cobre todos os tenants automaticamente.
- O modelo de dados muitos-para-muitos entre tenant e prompt já existe e suporta a associação em massa sem alteração de estrutura.
- A migração de dados e a ativação da exigência ocorrem no mesmo procedimento de implantação, sem chave de ativação gradual — decisão tomada com o solicitante.
- O conteúdo atual do arquivo de guardrails do projeto é adequado como política global padrão, já que reproduz o comportamento vigente em que todo tenant recebia esse texto.
- A interface administrativa correspondente é escopo do EDI-44; esta feature entrega o contrato de API que ela consome.
- A rotina de semente continua sendo executada a cada inicialização do processo, mantendo o comportamento idempotente já existente.
