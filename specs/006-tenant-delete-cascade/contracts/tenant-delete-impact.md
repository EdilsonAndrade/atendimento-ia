# Contrato: `GET /api/v1/tenants/{tenant_id}/delete-impact`

**Requisitos**: FR-010 · Consumido pelo EDI-46 (frontend)

## Propósito

Endpoint somente-leitura que calcula, sem executar nenhuma exclusão, o que aconteceria se `DELETE /tenants/{tenant_id}` fosse chamado agora: o que seria excluído de fato (prompt/guardrail exclusivo) e o que seria apenas desvinculado (compartilhado ou global). Usa exatamente a mesma lógica de decisão de `DELETE /tenants/{tenant_id}` (ver `data-model.md`), para que a UI nunca mostre um resumo que diverge do resultado real.

## Requisição

Nenhum parâmetro além do `tenant_id` na URL.

## Resposta

| Situação | HTTP | Corpo |
| -- | -- | -- |
| Sucesso | `200` | ver schema abaixo |
| Tenant não existe | `404` | `{"detail": "Tenant not found"}` (mesmo formato do `GET /tenants/{id}` atual) |

```json
{
  "tenant_id": "acme",
  "prompts_to_delete": [
    { "id": "uuid-1", "titulo": "Atendimento Acme", "node_type": "operational" }
  ],
  "prompts_to_unlink_only": [
    { "id": "uuid-2", "titulo": "Institucional Padrão", "node_type": "institutional" }
  ],
  "guardrails_to_delete": [
    { "id": "uuid-3", "titulo": "Guardrail específico da Acme" }
  ],
  "guardrails_to_unlink_only": [
    { "id": "uuid-4", "titulo": "Guardrail de segurança padrão", "is_global": true }
  ]
}
```

## Campos

| Campo | Tipo | Descrição |
| -- | -- | -- |
| `prompts_to_delete` | array | Prompts que serão excluídos de fato (vínculo ativo exclusivo deste tenant) |
| `prompts_to_unlink_only` | array | Prompts que serão preservados; só o vínculo com este tenant desaparece |
| `guardrails_to_delete` | array | Guardrails que serão excluídos de fato (não globais, não usados por outro prompt) |
| `guardrails_to_unlink_only` | array | Guardrails preservados (globais ou usados por outro prompt); `is_global` informado |

Todas as quatro listas podem vir vazias (tenant sem vínculos). Nenhuma delas é omitida — sempre as quatro chaves presentes.

## Verificação

- [ ] Tenant com prompt exclusivo + guardrail exclusivo → ambos aparecem em `*_to_delete`
- [ ] Tenant com prompt compartilhado → prompt aparece em `prompts_to_unlink_only`
- [ ] Tenant com guardrail global → guardrail aparece em `guardrails_to_unlink_only` com `is_global: true`
- [ ] Tenant sem nenhum vínculo → as quatro listas vêm vazias, HTTP 200
- [ ] Tenant inexistente → `404`
- [ ] Resultado bate exatamente com o efeito real de um `DELETE /tenants/{tenant_id}` executado em seguida
