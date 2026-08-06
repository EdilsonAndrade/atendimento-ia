# Usa a imagem oficial do Python
FROM python:3.11-slim

# Impede o Python de gravar arquivos .pyc e força o log sem buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Instala dependências do sistema caso necessário
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /lib/apt/lists/*

# Copia o arquivo de dependências do Python
COPY requirements.txt .

# Instala as dependências da aplicação
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código-fonte da API
COPY . .

# Expõe a porta interna 8001
EXPOSE 8001

# Comando para iniciar a API (ajuste main:app conforme o seu arquivo principal Python)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]