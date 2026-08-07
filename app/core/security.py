import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import os

# COMENTÁRIO: Instancia o esquema de autenticação básica HTTP para capturar credenciais no header
security = HTTPBasic()

# COMENTÁRIO: Obtém usuário e senha das variáveis de ambiente com fallbacks de segurança
SWAGGER_USER = os.getenv("SWAGGER_USER", "admin")
SWAGGER_PASSWORD = os.getenv("SWAGGER_PASSWORD", "mudar_senha_123")

def get_swagger_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    COMENTÁRIO: Compara o usuário e senha informados com as variáveis do .env 
    usando compare_digest para prevenir ataques de tempo (timing attacks).
    """
    correct_username = secrets.compare_digest(credentials.username, SWAGGER_USER)
    correct_password = secrets.compare_digest(credentials.password, SWAGGER_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas para acessar a documentação",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username