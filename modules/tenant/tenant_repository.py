from infrastructure.connection import get_db_connection

class TenantRepository:
    def __init__(self, connection=None):
        """Se `connection` for informada, este repositório passa a operar sobre
        ela em vez de abrir a sua própria — usado pela exclusão em cascata
        (EDI-45) para participar da mesma transação de `PromptManagerRepository`.
        Nesse caso, quem controla commit/rollback é o dono da conexão (o
        `conn.transaction()` externo), não este repositório.
        """
        self._owns_connection = connection is None
        self.db_connection = connection or get_db_connection()

    def _commit(self):
        if self._owns_connection:
            self.db_connection.commit()

    def create_tenant(self, tenant_data) -> dict:
        # Logic to create a new tenant in the database
        create_query = """
        INSERT INTO tenants (id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        RETURNING id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at;
        """
        cursor = self.db_connection.cursor()
        cursor.execute(create_query, (
            tenant_data['tenant_id'],
            tenant_data['name'],
            tenant_data['google_calendar_id'],
            tenant_data['allowed_domains'],
            tenant_data.get('scheduling_enabled', True),
        ))
        new_tenant = cursor.fetchone()
        self._commit()
        cursor.close()
        # COMENTÁRIO: Retorna o novo tenant criado como um dicionário
        return {
            'id': new_tenant[0],
            'name': new_tenant[1],
            'google_calendar_id': new_tenant[2],
            'allowed_domains': new_tenant[3],
            'scheduling_enabled': new_tenant[4],
            'created_at': new_tenant[5]
        }

    def create_tenant_with_prompt(self, tenant_data, prompt_id) -> dict:
        """Cria o tenant E o vínculo com o prompt operacional numa ÚNICA transação.

        Por que os dois INSERT vivem juntos aqui, apesar de `tenant_prompts` ser
        conceitualmente do módulo prompt_manager: um tenant existir sem vínculo de
        prompt é exatamente o estado que o EDI-43 elimina. Se os dois INSERT forem
        separados em duas transações, existe uma janela — curta, mas real — em que
        esse estado proibido está gravado no banco, e a compensação (apagar o
        tenant) pode ela própria falhar.

        NÃO separe estes dois INSERT em chamadas independentes "para respeitar a
        fronteira do módulo": isso reabre a janela que este método existe para
        fechar. A validação do prompt acontece antes, no service, de modo que os
        erros comuns (prompt inexistente, node_type errado) nunca chegam aqui.
        """
        cursor = self.db_connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO tenants (id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at;
                """,
                (
                    tenant_data['tenant_id'],
                    tenant_data['name'],
                    tenant_data['google_calendar_id'],
                    tenant_data['allowed_domains'],
                    tenant_data.get('scheduling_enabled', True),
                ),
            )
            new_tenant = cursor.fetchone()

            cursor.execute(
                """
                INSERT INTO tenant_prompts (tenant_id, prompt_id, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (tenant_id, prompt_id)
                DO UPDATE SET is_active = TRUE, updated_at = NOW();
                """,
                (tenant_data['tenant_id'], prompt_id),
            )

            self._commit()
        except Exception:
            if self._owns_connection:
                self.db_connection.rollback()
            raise
        finally:
            cursor.close()

        return {
            'id': new_tenant[0],
            'name': new_tenant[1],
            'google_calendar_id': new_tenant[2],
            'allowed_domains': new_tenant[3],
            'scheduling_enabled': new_tenant[4],
            'created_at': new_tenant[5],
        }

    def get_tenant(self, tenant_id) -> dict:
        # Logic to retrieve a tenant by ID from the database
        get_query = "SELECT id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at FROM tenants WHERE id = %s;"
        cursor = self.db_connection.cursor()
        cursor.execute(get_query, (tenant_id,))
        tenant = cursor.fetchone()
        cursor.close()
        if tenant:
            return {
                'id': tenant[0],
                'name': tenant[1],
                'google_calendar_id': tenant[2],
                'allowed_domains': tenant[3],
                'scheduling_enabled': tenant[4],
                'created_at': tenant[5]
            }
        return None

    def update_tenant(self, tenant_id, tenant_data) -> dict | None:
        # Logic to update an existing tenant in the database
        update_query = """
        UPDATE tenants
        SET name = %s, google_calendar_id = %s, allowed_domains = %s, scheduling_enabled = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at, updated_at;
        """
        cursor = self.db_connection.cursor()
        cursor.execute(update_query, (
            tenant_data['name'],
            tenant_data['google_calendar_id'],
            tenant_data['allowed_domains'],
            tenant_data.get('scheduling_enabled', True),
            tenant_id,
        ))
        updated_tenant = cursor.fetchone()
        self._commit()
        cursor.close()
        if updated_tenant:
            return {
                'id': updated_tenant[0],
                'name': updated_tenant[1],
                'google_calendar_id': updated_tenant[2],
                'allowed_domains': updated_tenant[3],
                'scheduling_enabled': updated_tenant[4],
                'created_at': updated_tenant[5],
                'updated_at': updated_tenant[6]
            }
        return None

    def list_tenants(self, term: str | None, limit: int = 20, offset: int = 0) -> list:
        """Lista tenants paginada. Sem `term`, devolve todos (ordenado por
        nome); com `term`, filtra por match parcial case-insensitive em id/name."""
        if term:
            query = """
            SELECT id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at, updated_at
            FROM tenants
            WHERE id ILIKE %s OR name ILIKE %s
            ORDER BY name
            LIMIT %s OFFSET %s;
            """
            pattern = f"%{term}%"
            params = (pattern, pattern, limit, offset)
        else:
            query = """
            SELECT id, name, google_calendar_id, allowed_domains, scheduling_enabled, created_at, updated_at
            FROM tenants
            ORDER BY name
            LIMIT %s OFFSET %s;
            """
            params = (limit, offset)

        cursor = self.db_connection.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                'id': row[0],
                'name': row[1],
                'google_calendar_id': row[2],
                'allowed_domains': row[3],
                'scheduling_enabled': row[4],
                'created_at': row[5],
                'updated_at': row[6],
            }
            for row in rows
        ]

    def count_tenants(self, term: str | None) -> int:
        cursor = self.db_connection.cursor()
        if term:
            pattern = f"%{term}%"
            cursor.execute(
                "SELECT COUNT(*) FROM tenants WHERE id ILIKE %s OR name ILIKE %s;",
                (pattern, pattern),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM tenants;")
        total = cursor.fetchone()[0]
        cursor.close()
        return total

    def delete_tenant(self, tenant_id) -> int | None:
        # Logic to delete a tenant from the database
        delete_query = "DELETE FROM tenants WHERE id = %s RETURNING id;"
        cursor = self.db_connection.cursor()
        cursor.execute(delete_query, (tenant_id,))
        deleted_tenant = cursor.fetchone()
        self._commit()
        cursor.close()
        return deleted_tenant[0] if deleted_tenant else None