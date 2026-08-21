# Feature Specification: Migrations versionadas do schema PostgreSQL (EDI-37)

**Feature Branch**: `edilsonaandrade/edi-37-configurar-migrations-e-acesso-sql-do-projeto`
**Created**: 2026-08-21
**Status**: Draft
**Linear**: [EDI-37 — Configurar migrations e acesso SQL do projeto](https://linear.app/edilsonandrade/issue/EDI-37/configurar-migrations-e-acesso-sql-do-projeto)
**Input**: Adotar um versionador de schema (Alembic) para o banco PostgreSQL do projeto, tornando a estrutura do banco reproduzível e portável entre clouds, mantendo `psycopg` como driver das consultas. O banco de produção já existe e não pode perder dados.

## Contexto do problema

Hoje a estrutura do banco nasce de duas fontes descoordenadas:

1. **DDL executado em tempo de execução pela aplicação** — quatro rotinas disparam `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... IF NOT EXISTS` durante o atendimento de requisições, cobrindo 3 das 9 tabelas do projeto.
2. **Tabelas criadas manualmente no banco de produção** — as outras 6 tabelas, mais uma função e três gatilhos de `updated_at`, não têm nenhuma definição versionada no repositório.

Consequências práticas:

- **Não é possível recriar o ambiente.** Subir o projeto num banco em branco (nova cloud, novo cliente, máquina de um desenvolvedor novo, ambiente de teste de integração) exige que alguém saiba, de memória, quais tabelas criar na mão.
- **A estrutura do banco não tem histórico.** Não há registro de qual alteração foi aplicada, quando, nem como desfazê-la.
- **Alteração de estrutura no caminho quente.** Uma das rotinas roda `ALTER TABLE` a cada chamada de oito métodos diferentes de repositório, ou seja, durante o atendimento normal de requisições.
- **Risco de divergência silenciosa** entre o que o código pressupõe e o que existe de fato em produção.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recriar o banco inteiro a partir do repositório (Priority: P1)

Um desenvolvedor (ou uma migração para outra cloud) precisa de um banco novo, vazio, funcionando com a aplicação. Ele aponta a configuração para o banco vazio, roda um único comando de migração e obtém a estrutura completa e idêntica à de produção — todas as 9 tabelas, chaves, índices, restrições, a extensão de UUID, a função de timestamp e os três gatilhos. Nenhum passo manual.

**Why this priority**: É o objetivo central do ticket (portabilidade entre clouds/bancos) e o pré-requisito de tudo mais. Sem uma definição versionada e completa do schema, nada nas outras histórias tem valor.

**Independent Test**: Criar um banco PostgreSQL vazio, rodar a migração e comparar a estrutura resultante com o dump de produção. As duas devem coincidir nas 9 tabelas do projeto e nos objetos de apoio. Entrega valor sozinha: o projeto passa a ser instalável do zero.

**Acceptance Scenarios**:

1. **Given** um banco PostgreSQL vazio, **When** a migração de baseline é aplicada, **Then** as 9 tabelas do projeto existem com as mesmas colunas, tipos, valores padrão, chaves primárias, restrições de unicidade, índices (incluindo o índice único parcial de prompt padrão por tipo de nó), a restrição de valores válidos de tipo de nó e as 3 chaves estrangeiras do dump de produção.
2. **Given** um banco PostgreSQL vazio, **When** a migração de baseline é aplicada, **Then** a extensão de geração de UUID, a função de atualização de timestamp e os três gatilhos de `updated_at` existem, e um `UPDATE` numa linha de prompt atualiza `updated_at` automaticamente.
3. **Given** a migração de baseline já aplicada, **When** ela é executada novamente, **Then** nada é alterado e nenhum erro é levantado.
4. **Given** o banco recriado do zero, **When** a aplicação sobe e um agendamento é criado, consultado e cancelado, **Then** o fluxo funciona sem que nenhuma tabela precise ser criada manualmente.

---

### User Story 2 - Adotar o versionamento sem tocar nos dados de produção (Priority: P1)

O responsável pelo deploy precisa colocar o banco de produção — que já existe, com dados reais de clientes — sob controle do versionador, sem que nenhuma estrutura seja recriada, alterada ou apagada.

**Why this priority**: É a condição de segurança que viabiliza a adoção. Sem ela, ativar migrations em produção seria destrutivo. Empata em prioridade com a US1 porque as duas juntas formam a entrega mínima viável.

**Independent Test**: Num clone do banco de produção, marcar a baseline como já aplicada e verificar que (a) o histórico de versões passa a existir apontando para a baseline, (b) nenhuma tabela, coluna, índice ou linha foi alterada, e (c) uma execução subsequente de "aplicar migrações pendentes" não faz nada.

**Acceptance Scenarios**:

1. **Given** um banco com a estrutura e os dados atuais de produção, **When** a baseline é marcada como já aplicada, **Then** o histórico de versões registra a baseline e **nenhum** comando de estrutura é executado.
2. **Given** o banco de produção marcado com a baseline, **When** o comando de aplicar migrações pendentes roda, **Then** nada é aplicado e o processo termina com sucesso.
3. **Given** o banco de produção antes e depois da adoção, **When** as contagens de linhas de todas as 9 tabelas são comparadas, **Then** são idênticas.

---

### User Story 3 - Migrações aplicadas automaticamente a cada deploy (Priority: P2)

Quando uma nova versão da aplicação sobe em produção, qualquer alteração de estrutura pendente é aplicada automaticamente antes de a aplicação começar a atender requisições — sem ninguém lembrar de rodar um comando manual, e sem que a aplicação suba com o banco desatualizado.

**Why this priority**: Sem isso, o versionamento existe mas depende de disciplina humana e diverge na primeira distração. Vem depois das duas primeiras porque só faz sentido quando já existe uma baseline confiável.

**Independent Test**: Subir o contêiner apontando para um banco em branco e verificar, pelos logs de inicialização, que as migrações são aplicadas antes de a aplicação aceitar requisições.

**Acceptance Scenarios**:

1. **Given** um banco com migrações pendentes, **When** o contêiner da aplicação inicia, **Then** as migrações são aplicadas antes de a aplicação começar a aceitar requisições.
2. **Given** o mecanismo de inicialização do contêiner, **When** o orquestrador de contêineres substitui o comando de execução (como ocorre hoje em produção), **Then** as migrações ainda assim são aplicadas.
3. **Given** uma migração que falha, **When** o contêiner inicia, **Then** a aplicação **não** sobe atendendo requisições com o banco em estado inconsistente, e a falha aparece nos logs.
4. **Given** um banco já atualizado, **When** o contêiner reinicia, **Then** a inicialização não altera nada e o tempo adicional de subida é desprezível.

---

### User Story 4 - Aplicação deixa de alterar a estrutura do banco (Priority: P3)

A aplicação passa a assumir que a estrutura do banco já está correta quando sobe. Nenhuma requisição de usuário dispara criação ou alteração de tabela.

**Why this priority**: É a consolidação — elimina a fonte concorrente de verdade e o custo de `ALTER TABLE` no caminho quente. Depende inteiramente das histórias anteriores estarem funcionando, por isso vem por último.

**Independent Test**: Exercitar os fluxos de prompts, sessões de conversa, base de conhecimento e agendamentos com um usuário de banco **sem permissão de alterar estrutura**. Todos devem funcionar normalmente.

**Acceptance Scenarios**:

1. **Given** a aplicação conectada com um usuário de banco sem permissão de DDL, **When** os fluxos de prompts, guardrails, sessões de conversa, base de conhecimento e agendamentos são exercitados, **Then** todos funcionam sem erro de permissão.
2. **Given** o código-fonte após a mudança, **When** ele é inspecionado, **Then** não resta nenhuma rotina que execute criação ou alteração de tabela em tempo de execução.
3. **Given** os fluxos existentes de negócio, **When** a suíte de testes roda, **Then** todos os testes que hoje passam continuam passando.

---

### Edge Cases

- **Banco de produção divergente do dump usado como baseline.** Se alguém alterar a estrutura manualmente entre a geração do dump e a adoção, a baseline mente. Precisa haver uma forma de conferir a estrutura real contra a baseline antes de marcá-la como aplicada.
- **Duas instâncias da aplicação subindo ao mesmo tempo** e tentando aplicar a mesma migração. Só uma pode aplicar; a outra deve aguardar ou seguir sem erro, nunca aplicar em duplicidade.
- **Tabelas que não pertencem ao projeto.** As tabelas criadas e mantidas pelas bibliotecas de terceiros (memória de conversa e armazenamento de vetores) não podem ser versionadas aqui: se a biblioteca evoluir o próprio schema, o versionador entraria em conflito com ela.
- **Banco novo sem a extensão de vetores.** Ao subir num banco em branco, a estrutura das bibliotecas de terceiros é criada por elas mesmas, não pela migração — o ambiente novo precisa permitir isso.
- **Falha de conexão com o banco durante a inicialização do contêiner.** Precisa falhar de forma visível, não subir silenciosamente.
- **Reversão de migração.** Ao desfazer a baseline num banco de produção, o resultado seria a perda de todos os dados. Esse caminho precisa ser explicitamente inofensivo ou bloqueado.

## Requirements *(mandatory)*

### Functional Requirements

**Baseline e versionamento**

- **FR-001**: O sistema MUST manter, versionada no repositório, a definição completa da estrutura das 9 tabelas do projeto: `tenants`, `prompts`, `guardrails`, `prompt_guardrails`, `tenant_prompts`, `whatsapp_instances`, `agendamentos`, `chat_thread_sessions` e `tenant_knowledge_base`.
- **FR-002**: A definição versionada MUST incluir, além das tabelas: chaves primárias, restrições de unicidade, índices (incluindo o índice único parcial que garante um único prompt padrão por tipo de nó), a restrição de valores válidos do tipo de nó, as 3 chaves estrangeiras existentes, a extensão de geração de UUID, a função de atualização de timestamp e os três gatilhos de `updated_at`.
- **FR-003**: A definição versionada MUST corresponder exatamente à estrutura atual de produção — sem acrescentar, remover ou corrigir nada em relação a ela.
- **FR-004**: O sistema MUST registrar, no próprio banco, qual versão de estrutura está aplicada.
- **FR-005**: O sistema MUST permitir marcar um banco pré-existente como já estando na versão de baseline, **sem executar nenhum comando de alteração de estrutura**.
- **FR-006**: Aplicar as migrações num banco já atualizado MUST ser inofensivo (nenhuma alteração, nenhum erro).

**Deploy**

- **FR-007**: O sistema MUST aplicar as migrações pendentes automaticamente na inicialização do contêiner, antes de a aplicação começar a aceitar requisições.
- **FR-008**: O mecanismo de aplicação automática MUST funcionar mesmo quando o orquestrador de contêineres substitui o comando de execução da imagem — condição que ocorre hoje em produção.
- **FR-009**: Se uma migração falhar, o sistema MUST impedir que a aplicação passe a atender requisições e MUST registrar a falha de forma visível nos logs.
- **FR-010**: O sistema MUST permitir que um operador aplique, reverta e consulte o estado das migrações manualmente, com comandos documentados.

**Fronteira com bibliotecas de terceiros**

- **FR-011**: O sistema MUST excluir do controle de versão as tabelas criadas e mantidas por bibliotecas de terceiros: as quatro tabelas de memória de conversa (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) e as duas de armazenamento de vetores (`langchain_pg_collection`, `langchain_pg_embedding`), além da extensão de vetores.
- **FR-012**: A exclusão MUST ser automática, de modo que uma futura geração automática de migração não proponha alterações nessas tabelas.

**Remoção do DDL em tempo de execução**

- **FR-013**: O sistema MUST deixar de executar criação ou alteração de estrutura durante o atendimento de requisições, removendo as quatro rotinas atuais (garantia da coluna de tipo de nó, criação da tabela de sessões de conversa, criação da tabela de base de conhecimento e criação da tabela de agendamentos).
- **FR-014**: Após a remoção, a aplicação MUST funcionar integralmente com um usuário de banco **sem permissão de alterar estrutura**.
- **FR-015**: A remoção MUST NOT alterar o comportamento observável de nenhum fluxo de negócio existente.

**Documentação**

- **FR-016**: O sistema MUST documentar o procedimento de adoção em produção (marcar a baseline) e o de criação de um ambiente novo do zero.
- **FR-017**: O sistema MUST documentar como criar uma nova migração para alterações futuras de estrutura.

### Key Entities

- **Migração**: uma unidade versionada e ordenada de alteração de estrutura, com identificador próprio, referência à migração anterior e um caminho de aplicação e outro de reversão.
- **Baseline**: a primeira migração, que representa a fotografia da estrutura atual de produção. É aplicada de verdade em bancos vazios e apenas *registrada* em bancos que já existem.
- **Histórico de versões**: registro persistido no próprio banco indicando qual migração está aplicada.
- **Tabelas do projeto** (sob controle): `tenants` (clientes da plataforma), `prompts` e `guardrails` e suas associações `prompt_guardrails` e `tenant_prompts` (configuração de comportamento da IA por cliente), `whatsapp_instances` (canais de WhatsApp por cliente), `agendamentos` (compromissos marcados), `chat_thread_sessions` (controle de expiração de conversa por inatividade), `tenant_knowledge_base` (base de conhecimento textual por cliente).
- **Tabelas de terceiros** (fora do controle): memória de conversa do orquestrador de agentes e armazenamento de vetores da busca semântica.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um banco PostgreSQL vazio se torna um ambiente funcional da aplicação com **um único comando** e **zero passos manuais** de criação de tabela.
- **SC-002**: A estrutura de um banco criado do zero é **idêntica** à de produção nas 9 tabelas do projeto e nos objetos de apoio — verificável comparando dumps de estrutura.
- **SC-003**: A adoção em produção resulta em **zero linhas alteradas ou perdidas**: as contagens de todas as 9 tabelas são idênticas antes e depois.
- **SC-004**: **Nenhuma** alteração de estrutura ocorre durante o atendimento de requisições — comprovado por a aplicação funcionar integralmente com um usuário de banco sem permissão de DDL.
- **SC-005**: Toda alteração futura de estrutura fica registrada com autoria, ordem e caminho de reversão, rastreável pelo histórico do repositório.
- **SC-006**: Um deploy num banco já atualizado adiciona **menos de 5 segundos** ao tempo de subida da aplicação.
- **SC-007**: **100%** dos testes que passam hoje continuam passando após a mudança.

## Assumptions

- **Ferramenta**: Alembic, decidido com o usuário. Alembic versiona o schema e não exige ORM — as migrações podem conter SQL explícito. É camada distinta do driver.
- **Driver mantido**: `psycopg` continua sendo o driver de todas as consultas. A eventual troca da camada de consulta (SQLAlchemy Core ou ORM) está **fora do escopo** deste ticket e vira ticket próprio.
- **Fonte da baseline**: o dump de estrutura do banco de **produção** (PostgreSQL 15.18, Debian), coletado em 2026-08-21 diretamente do contêiner do banco, conferido contra o DDL presente no código — as 3 tabelas criadas em tempo de execução coincidem 100% com produção, o que torna a marcação de baseline segura. Um primeiro dump usado no levantamento vinha de um PostgreSQL 17.5 (ambiente de desenvolvimento); as duas estruturas se mostraram idênticas, mas a fonte oficial é a de produção.
- **Estratégia de adoção**: em produção a baseline é apenas *registrada*, nunca executada. Consequência aceita e conhecida: qualquer objeto que a baseline descreva mas que não exista em produção nunca será criado lá — correções de estrutura precisam vir em migrações posteriores, que rodam de verdade.
- **Ponto de execução no deploy**: a inicialização da imagem do contêiner, e não o script de inicialização atual — porque o arquivo de orquestração de produção substitui o comando de execução, o que faz o script atual **não** ser executado em produção hoje.
- **Versão do banco**: PostgreSQL **15.18** (Debian) em produção — o ambiente de desenvolvimento roda 17.x. Todos os recursos usados na baseline (índice único parcial, restrição de verificação, gatilhos, `gen_random_uuid()` nativo desde a 13) são suportados na 15. Verificado na prática: a baseline foi aplicada num contêiner `postgres:15` e o dump resultante conferiu com o de produção.
- **Acesso**: quem executa a adoção em produção tem acesso ao banco e permissão para criar a tabela de histórico de versões.

## Out of Scope

Registrados como achados no comentário do EDI-37; cada um vira ticket próprio:

- Adicionar chaves estrangeiras de `tenant_id` (`agendamentos`, `tenant_prompts`, `whatsapp_instances` → `tenants`), que hoje não existem — exige varrer registros órfãos antes.
- Adicionar o gatilho de `updated_at` faltante na tabela `tenants`, que hoje faz o campo nunca ser atualizado.
- Migrar as consultas de `psycopg` para SQLAlchemy.
- Padronizar a geração de UUID (`whatsapp_instances` usa uma função diferente das demais tabelas).
- Remover ou passar a usar a coluna `tenants.active`, que existe no banco mas nunca é lida pelo código.
