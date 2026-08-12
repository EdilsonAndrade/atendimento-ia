# Usa a imagem oficial do Python
FROM python:3.11-slim

# Impede o Python de gravar arquivos .pyc e força o log sem buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Define o diretório de trabalho dentro do container
WORKDIR /app

# COMENTÁRIO: Adiciona o diretório /app ao PYTHONPATH para o Python localizar o módulo 'app.main' sem erros de importação
ENV PYTHONPATH=/app

# Instala dependências do sistema caso necessário
# COMENTÁRIO: ca-certificates é ESSENCIAL para que o google-api-python-client
# consiga validar conexões SSL/TLS com os servidores do Google.
# Sem ele, ocorre: SSLError: [SSL] record layer failure (_ssl.c:2590)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates && rm -rf /lib/apt/lists/*

# Copia o arquivo de dependências do Python
COPY requirements.txt .

# Instala as dependências da aplicação
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código-fonte da API
COPY . .

# Expõe a porta interna 8001
EXPOSE 8001

# COMENTÁRIO: Torna o script de inicialização executável
RUN sed -i -e 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# Comando para iniciar a API (ajuste main:app conforme o seu arquivo principal Python)
CMD ["/app/start.sh"]