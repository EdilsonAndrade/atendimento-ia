# Plano de Implementação: Correção de Vínculo de Prompt

**Ticket:** EDI-38  
**Data:** 2026-08-20

## Objetivo

Garantir que quando um tenant é vinculado a um novo prompt, o vínculo antigo é desativado automaticamente, permitindo que a UI e o chat reflitam sempre o prompt ativo correto.

## Análise de Impacto

### Componentes Afetados

| Componente | Arquivo | Mudança |
|-----------|---------|---------|
| Repository | `prompt_manager_repository.py` | Desativar vínculos antigos em `sync_tenant_prompt()` |
| Service | `prompt_manager_service.py` | (Nenhuma - lógica está no repo) |
| Endpoint | `prompt_manager.py` | (Nenhuma - já chama o repo correto) |
| Runtime | `carregar_operacional_prompt()` | (Nenhuma - a query já faz LIMIT 1) |

### Mudanças de Banco de Dados

**Nenhuma migração necessária** — apenas ajuste na lógica SQL da query existente.

## Solução Técnica

### Abordagem: Desativar Vínculos Antigos Atomicamente

No método `sync_tenant_prompt()` do `PromptManagerRepository`:

1. **Passo 1:** Desativar todos os registros antigos do tenant (exceto o novo)
   ```sql
   UPDATE tenant_prompts
   SET is_active = FALSE, updated_at = NOW()
   WHERE tenant_id = %s AND prompt_id != %s
   ```

2. **Passo 2:** Ativar o novo vínculo (ou atualizar se já existe)
   ```sql
   INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active, custom_content_override)
   VALUES (%s, %s, TRUE, %s)
   ON CONFLICT (tenant_id, prompt_id)
   DO UPDATE SET is_active = TRUE, custom_content_override = EXCLUDED.custom_content_override
   ```

### Por Que Funciona

- **Antes:** INSERT sem desativar = múltiplos registros ativos
- **Depois:** UPDATE desativa + INSERT ativa = 1 ativo garantido
- **Atomicidade:** Mesma transação, sem race conditions
- **Compatibilidade:** Reutilizar prompts antigos continua funcionando (UPDATE reativa)

## Testes Necessários

### Testes Unitários

1. **test_sync_tenant_prompt_deactivates_old_links**
   - Dado: Tenant com vínculo ao Prompt A
   - Quando: `sync_tenant_prompt(tenant_id, prompt_B_id)`
   - Então: Prompt A fica inativo, Prompt B fica ativo

2. **test_sync_tenant_prompt_reactivates_old_prompt**
   - Dado: Tenant vinculado ao Prompt B (Prompt A inativo)
   - Quando: `sync_tenant_prompt(tenant_id, prompt_A_id)`
   - Então: Prompt A reativado, Prompt B desativado

3. **test_get_active_prompt_returns_only_active**
   - Dado: Múltiplos registros, apenas 1 ativo
   - Quando: `get_active_prompt_by_tenant(tenant_id)`
   - Então: Retorna o registro ativo

### Testes de Integração

1. **test_endpoint_link_tenant_updates_ui**
   - POST `/link-tenant` com novo prompt
   - GET `/tenant/{id}` retorna novo prompt
   - Verificar guardrails também

2. **test_chat_uses_new_guardrails_after_binding**
   - Vincular novo prompt
   - Enviar mensagem no chat
   - Verificar que response aplica novo guardrail

## Riscos e Mitigações

| Risco | Severidade | Mitigação |
|-------|-----------|-----------|
| Race condition em `sync_tenant_prompt` | Alta | Usar transação única (já é por conexão) |
| Vínculos antigos ficam orfãos | Baixa | Apenas mudam status, dados preservados |
| Chat lê vínculo antigo durante UPDATE | Média | Queries já fazem LIMIT 1 + ORDER BY data |

## Cronograma

1. Implementar mudança no repository (5 min)
2. Adicionar testes unitários (15 min)
3. Testes manuais no tenant 1234 (10 min)
4. Code review (10 min)
5. Deploy (5 min)

**Total:** ~45 min

## Rollback

Se necessário, reverter commit:
```bash
git revert <commit_hash>
```

Nenhum rollback de dados necessário — apenas lógica de negócio inverte.
