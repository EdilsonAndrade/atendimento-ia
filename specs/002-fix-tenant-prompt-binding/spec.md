# Especificação: Correção de Vínculo de Prompt não Reflete Guardrails no Chat

**Ticket:** EDI-38  
**Data:** 2026-08-20  
**Status:** Em Progresso

## Problema

Ao vincular um novo prompt a um tenant e salvar, a mudança é registrada no banco de dados e aparece na tabela, mas a tela de vinculação continua exibindo o **prompt antigo** como vínculo atual. Como resultado, o chat não aplica os guardrails vinculados ao novo prompt.

### Cenário de Erro

No tenant `1234`:
- Prompt anterior: "Agendamento Padrão e Assistente Comercial" (com guardrails antigos)
- Novo prompt selecionado: "Interasis AI - Com GREETING"
- Resultado esperado: Tela mostra novo prompt + novos guardrails
- Resultado atual: Tela mostra prompt antigo + guardrails antigos
- Chat continua ignorando os guardrails do novo prompt

## Raiz do Problema

Na tabela `tenant_prompts`, quando um tenant é vinculado a um novo prompt:

1. Um novo registro é inserido com `is_active = TRUE`
2. **MAS** os registros antigos não são desativados
3. Múltiplos registros com `is_active = TRUE` coexistem para o mesmo tenant
4. Queries com `LIMIT 1` retornam o primeiro registro (pode ser o antigo)

**Fluxo de dados afetado:**
- Endpoint `GET /tenant/{tenant_id}` → `get_tenant_prompt_details()` → retorna prompt antigo
- Chat `operational_node` → `carregar_operacional_prompt()` → carrega guardrails antigos

## Requisitos Funcionais

### RF-1: Vínculo Único Ativo por Tenant
Quando um tenant é vinculado a um novo prompt, apenas esse vínculo deve estar ativo.
- Todos os vínculos anteriores do tenant devem ser desativados (`is_active = FALSE`)
- A mudança deve ser atômica (uma transação)

### RF-2: UI Reflete Vínculo Atual
Ao abrir a tela de vinculação, o sistema deve exibir o prompt atualmente vinculado.
- GET `/prompt-manager/tenant/{tenant_id}` deve retornar o vínculo ativo correto
- Guardrails exibidos devem corresponder ao prompt ativo

### RF-3: Chat Aplica Guardrails Novos
Após vincular um novo prompt, o chat deve usar seus guardrails.
- `carregar_operacional_prompt()` deve buscar os guardrails do prompt ativo correto
- Runtime do agente usa o system prompt correto no `operational_node`

## Cenários de Teste

### Cenário 1: Vincular Novo Prompt
**Dado:** Tenant com vínculo anterior ao Prompt A  
**Quando:** Vincular tenant ao Prompt B  
**Então:**
- Prompt B aparece na tabela como ativo
- GET `/prompt-manager/tenant/{id}` retorna Prompt B
- Guardrails exibem os do Prompt B
- Banco: apenas 1 registro com `is_active = TRUE` (Prompt B)

### Cenário 2: Reutilizar Prompt Anterior
**Dado:** Tenant com vínculo ao Prompt B, vinculou antes ao Prompt A  
**Quando:** Vincular novamente ao Prompt A  
**Então:**
- Prompt A volta a ser ativo
- Registro antigo de Prompt A é reativado
- Prompt B é desativado

### Cenário 3: Chat com Novo Prompt
**Dado:** Tenant com novo vínculo  
**Quando:** Enviar mensagem no chat  
**Então:**
- `operational_node` carrega Prompt + guardrails corretos
- Resposta do agente aplica guardrails do novo prompt

## Critérios de Sucesso

1. **Integridade de Vínculos:** Máximo 1 registro com `(tenant_id, is_active=TRUE)` por tenant
2. **UI Consistente:** Tela de vinculação mostra prompt ativo correto em <100ms
3. **Chat Efetivo:** Guardrails do novo prompt são aplicados em todas as respostas
4. **Atomicidade:** Transação garante que no máximo 1 vínculo fica ativo
5. **Compatibilidade:** Reutilizar prompts anteriores continua funcionando

## Dependências Técnicas

- Tabela `tenant_prompts` (PostgreSQL)
- Repositório: `prompt_manager_repository.py`
- Serviço: `prompt_manager_service.py`
- Endpoints: `/link-tenant`, `/tenant/{tenant_id}`
- Runtime: `carregar_operacional_prompt()`, `operational_node`

## Supressões

- Não alterar fluxo de fallback para prompt padrão
- Não afetar vínculos já existentes de tenants ativos
- Não recriar tabelas ou migrações (ajuste SQL existente)

## Prioridade

**Alta** — Afeta qualidade de atendimento e uso de guardrails
