#!/bin/sh
# Entrypoint do contêiner (EDI-37): aplica as migrations pendentes ANTES de a
# aplicação começar a atender requisições.
#
# POR QUE AQUI E NÃO NO start.sh: o docker-compose.yml de produção define
#   command: ["uvicorn", "app.main:app", ...]
# e no Docker o `command` do Compose substitui o CMD da imagem, mas NÃO o
# ENTRYPOINT. Ou seja, tudo que estivesse no CMD/start.sh simplesmente não roda
# em produção. No ENTRYPOINT, a migração roda independentemente de quem define o
# comando final.
#
# `set -e`: se o `alembic upgrade` falhar, o script morre aqui e o `exec` nunca
# acontece — a aplicação nunca sobe servindo requisições contra um banco em
# estado inconsistente.
set -e

echo "[entrypoint] Aplicando migrations pendentes (alembic upgrade head)..."
# `python -m alembic` em vez do executável `alembic`: não depende de o console script
# ter sido instalado no PATH da imagem.
python -m alembic upgrade head
echo "[entrypoint] Migrations em dia. Iniciando a aplicação: $*"

exec "$@"
