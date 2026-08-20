# Tarefas: EDI-38 - Correção de Vínculo de Prompt

**Status:** Pronto para Implementação  
**Total Estimado:** 45 minutos

## Tarefas

### 1. Implementar Correção no Repository
**Arquivo:** `modules/prompt_manager/prompt_manager_repository.py`  
**Tempo:** 10 min  
**Dependência:** Nenhuma

#### Descrição
Modificar método `sync_tenant_prompt()` para desativar vínculos antigos antes de ativar o novo.

#### Checklist
- [ ] Adicionar UPDATE para desativar registros antigos com `prompt_id != novo_prompt_id`
- [ ] Manter INSERT/ON CONFLICT para o novo vínculo
- [ ] Ambas as queries na mesma transação (mesma conexão)
- [ ] Adicionar comentário explicando a ordem das operações

#### Verificação
```python
# Verificar que o método tem:
# 1. UPDATE tenant_prompts SET is_active = FALSE WHERE tenant_id = %s AND prompt_id != %s
# 2. INSERT ... ON CONFLICT ... DO UPDATE SET is_active = TRUE
```

---

### 2. Adicionar Testes Unitários
**Arquivo:** `tests/unit/test_prompt_manager_sync.py`  
**Tempo:** 15 min  
**Dependência:** Tarefa 1

#### Descrição
Criar 3 testes para validar comportamento de desativação de vínculos.

#### Checklist
- [ ] `test_sync_tenant_prompt_deactivates_old_links` — verifica que vínculo antigo fica inativo
- [ ] `test_sync_tenant_prompt_reactivates_old_prompt` — verifica reativação de prompt anterior
- [ ] `test_get_active_prompt_returns_only_active` — verifica que LIMIT 1 retorna correto
- [ ] Todos os testes usam fixture com tenant + múltiplos prompts
- [ ] Testes passam localmente

#### Verificação
```bash
pytest tests/unit/test_prompt_manager_sync.py -v
# Todos os 3 testes devem passar
```

---

### 3. Testes Manuais no Painel Admin
**Tempo:** 10 min  
**Dependência:** Tarefa 1, 2

#### Descrição
Validar na UI do painel admin que vínculo de prompt reflete corretamente.

#### Cenários
- [ ] **Cenário 1:** Abrir tenant 1234 → Vincular novo prompt → Verificar que tela mostra novo prompt + guardrails novos
- [ ] **Cenário 2:** Vincular prompt antigo → Verificar que volta ao anterior (reativação)
- [ ] **Cenário 3:** Abrir chat → Enviar mensagem → Verificar que resposta usa guardrails do novo prompt

#### Verificação
```
UI Painel: /prompt-manager/tenant/1234
Chat Widget: teste com novo guardrail (ex: "Avoid too many spaces...")
```

---

### 4. Code Review
**Tempo:** 10 min  
**Dependência:** Tarefa 1, 2, 3

#### Descrição
Revisar mudanças de código e testes.

#### Checklist
- [ ] Lógica de negócio está clara
- [ ] Sem N+1 queries
- [ ] Sem race conditions (transação única)
- [ ] Testes cobrem cenários principais
- [ ] Documentação / comentários adequados

---

### 5. Deploy
**Tempo:** 5 min  
**Dependência:** Tarefa 4

#### Descrição
Realizar deploy da correção.

#### Checklist
- [ ] Criar commit com mensagem descritiva
- [ ] Push para branch do EDI-38
- [ ] Criar PR
- [ ] Merge após aprovação
- [ ] Acompanhar CI/CD

#### Modelo de Commit
```
fix: desativa vínculos antigos ao vincular novo prompt a tenant (EDI-38)

Quando um tenant era vinculado a um novo prompt, o vínculo antigo
não era desativado, causando que múltiplos registros com is_active=TRUE
coexistissem. Queries com LIMIT 1 retornavam o antigo, refletindo na UI
e no chat.

Solução: Desativar todos os vínculos antigos (prompt_id != novo) antes
de ativar o novo vínculo na mesma transação.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

## Ordem de Execução

```
1. Implementar Correção (sync_tenant_prompt)
   ↓
2. Adicionar Testes Unitários
   ↓
3. Testes Manuais
   ↓
4. Code Review
   ↓
5. Deploy
```

## Critérios de Aceitação

- [ ] Apenas 1 vínculo com `is_active = TRUE` por tenant em qualquer momento
- [ ] UI mostra prompt ativo correto
- [ ] Chat aplica guardrails do novo prompt
- [ ] Todos os 3 testes passam
- [ ] Sem regressões em cenários existentes

## Notas

- Nenhuma migração de banco necessária
- Nenhuma mudança em serviços/endpoints
- Mudança é backward-compatible
