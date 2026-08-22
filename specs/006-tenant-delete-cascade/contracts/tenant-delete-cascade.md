# Contrato: `DELETE /api/v1/tenants/{tenant_id}` — exclusão em cascata

**Requisitos**: FR-001 a FR-009, FR-011, FR-012

## Comportamento atual (defeito)

`TenantRepository.delete_tenant` (`modules/tenant/tenant_repository.py:152-160`) executa só `DELETE FROM tenants WHERE id = %s`. Não há verificação de uso nem cascata: linhas em `tenant_prompts` referenciando esse tenant ficam órfãs (sem FK hoje — ver `research.md` §2).

## Comportamento novo

| Situação | HTTP | Corpo |
| -- | -- | -- |
| Sucesso | `200` | `{"id": "...", "message": "Tenant deleted successfully"}` (formato inalterado) |
| Tenant não existe | `404` | `{"detail": "Tenant not found"}` (formato inalterado) |
| Falha durante a orquestração (erro de sistema) | `500` | nenhuma alteração persistida (rollback automático da transação) |

Não há mais nenhum código de bloqueio (`409`) para o tenant em si — a exclusão de tenant **sempre** é permitida; o que muda é o que acontece com prompts/guardrails associados, conforme a tabela de decisão abaixo. Não é necessário um novo `ErrorCode` em `app/schemas/prompt_manager.py` para este endpoint.

## Regra de decisão (por vínculo ativo do tenant)

| Prompt | Guardrail (do prompt) | Resultado |
| -- | -- | -- |
| Exclusivo (nenhum outro tenant ativo) | Exclusivo (não global, não usado por outro prompt) | Prompt **excluído**, guardrail **excluído** |
| Exclusivo | Global ou usado por outro prompt | Prompt **excluído**, guardrail **preservado** (só desvinculado) |
| Compartilhado (outro tenant ativo usa) | (irrelevante — prompt sobrevive) | Prompt **preservado** (só este vínculo desaparece), guardrail **inalterado** |

Tenant sem nenhum vínculo ativo: exclusão do tenant não tem nenhum efeito adicional.

## Verificação

- [ ] Prompt e guardrail exclusivos → tenant, prompt e guardrail deixam de existir
- [ ] Prompt compartilhado com outro tenant → só o vínculo desse tenant some; prompt continua ativo para o outro tenant
- [ ] Guardrail global vinculado a prompt exclusivo → prompt some, guardrail continua existindo e aplicado globalmente
- [ ] Guardrail vinculado a prompts de dois tenants (nenhum global) → ao excluir um dos tenants, o guardrail permanece (o outro prompt ainda o usa)
- [ ] Tenant sem vínculo nenhum → exclusão simples, sem efeitos colaterais
- [ ] Tenant inexistente → `404`, nenhum efeito colateral
- [ ] Resultado bate exatamente com o que `GET /tenants/{tenant_id}/delete-impact` informou antes da chamada
- [ ] Uma falha simulada no meio da orquestração não deixa nenhuma alteração parcial (tenant, prompts e guardrails permanecem exatamente como estavam)
