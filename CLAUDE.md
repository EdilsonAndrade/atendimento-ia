<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
specs/012-grafana-loki-observability/plan.md
## RULES
1. Always speak in Portugese in the chat
2. EVITE ao máximo detalhar muito, SOMENTE quando solicito ou não compreensivo pelo usuário

## GUARDRAILS
1. SEMPRE acesse o linear via MCP configurado no arquivo `./.mcp.json` quando mencionado algum numero de ticket, card, ou issue pelo usuário
2. SE houver dúvidas ou incertezas SEMPRE questionar.
3. Quando estiver tudo esclarecido iniciar na seguinte ordem os comandos
   1. /speckit-specify
   2. /speckit-plan
   3. /speckit-tasks
   4. /speckit-implement
4. O nome da branch sempre levará o NOME da ISSUE do Linear, se não houver, pergunte.
5. CASO não haja ticket no linear, atuar pontualmente após entendimento
6. Revision ID de migration do Alembic (nome do arquivo em `migrations/versions/`, sem o `.py`) DEVE ter no máximo 32 caracteres — é o limite da coluna `alembic_version.version_num`. Usar um slug curto (ex.: `0009_conversation_followup`, não `0009_conversation_history_followup`) e conferir com `len(revision_id)` antes de criar o arquivo.

## MANDATORY
1. WHEN you want to execute tests MUST pass the command to the user can test.
2. Todo ticket que for criar no LIENEAR deve conter os endpoints se houver, descritos em detalhe para o front-end saber como criar as chamadas corretamente.
<!-- SPECKIT END -->
