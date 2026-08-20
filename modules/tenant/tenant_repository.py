from infrastructure.connection import get_db_connection

class TenantRepository:
    def __init__(self):
        self.db_connection = get_db_connection()  # Initialize the repository with a database connection

    def create_tenant(self, tenant_data) -> dict:
        # Logic to create a new tenant in the database
        create_query = """
        INSERT INTO tenants (id, name, google_calendar_id, allowed_domains, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        RETURNING id, name, google_calendar_id, allowed_domains, created_at;
        """
        cursor = self.db_connection.cursor()
        cursor.execute(create_query, (tenant_data['tenant_id'], tenant_data['name'], tenant_data['google_calendar_id'], tenant_data['allowed_domains']))
        new_tenant = cursor.fetchone()
        self.db_connection.commit()
        cursor.close()
        # COMENTÁRIO: Retorna o novo tenant criado como um dicionário
        return {
            'id': new_tenant[0],
            'name': new_tenant[1],
            'google_calendar_id': new_tenant[2],
            'allowed_domains': new_tenant[3],
            'created_at': new_tenant[4]
        }

    def get_tenant(self, tenant_id) -> dict:
        # Logic to retrieve a tenant by ID from the database
        get_query = "SELECT id, name, google_calendar_id, allowed_domains, created_at FROM tenants WHERE id = %s;"
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
                'created_at': tenant[4]
            }
        return None

    def update_tenant(self, tenant_id, tenant_data) -> dict | None:
        # Logic to update an existing tenant in the database
        update_query = """
        UPDATE tenants  
        SET name = %s, google_calendar_id = %s, allowed_domains = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id, name, google_calendar_id, allowed_domains, created_at, updated_at;
        """
        cursor = self.db_connection.cursor()
        cursor.execute(update_query, (tenant_data['name'], tenant_data['google_calendar_id'], tenant_data['allowed_domains'], tenant_id))
        updated_tenant = cursor.fetchone()
        self.db_connection.commit()
        cursor.close()
        if updated_tenant:
            return {
                'id': updated_tenant[0],
                'name': updated_tenant[1],
                'google_calendar_id': updated_tenant[2],
                'allowed_domains': updated_tenant[3],
                'created_at': updated_tenant[4],
                'updated_at': updated_tenant[5]
            }
        return None

    def search_tenants(self, term: str, limit: int = 20) -> list:
        # Busca parcial e case-insensitive por id ou name
        search_query = """
        SELECT id, name, google_calendar_id, allowed_domains, created_at, updated_at
        FROM tenants
        WHERE id ILIKE %s OR name ILIKE %s
        ORDER BY name
        LIMIT %s;
        """
        pattern = f"%{term}%"
        cursor = self.db_connection.cursor()
        cursor.execute(search_query, (pattern, pattern, limit))
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                'id': row[0],
                'name': row[1],
                'google_calendar_id': row[2],
                'allowed_domains': row[3],
                'created_at': row[4],
                'updated_at': row[5],
            }
            for row in rows
        ]

    def delete_tenant(self, tenant_id) -> int | None:
        # Logic to delete a tenant from the database
        delete_query = "DELETE FROM tenants WHERE id = %s RETURNING id;"
        cursor = self.db_connection.cursor()
        cursor.execute(delete_query, (tenant_id,))
        deleted_tenant = cursor.fetchone()
        self.db_connection.commit()
        cursor.close()
        return deleted_tenant[0] if deleted_tenant else None