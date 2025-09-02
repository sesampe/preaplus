# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Fuerza rebuild cuando cambie requirements (y permite “cache bust” manual)
ARG CACHEBUST=2025-09-02-02

# 1) Copiar SOLO requirements primero
COPY requirements.txt /app/requirements.txt

# 2) Instalar dependencias (incluye openai>=1.45.0)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# 3) Copiar el resto del código
COPY . /app

# 4) (Opcional) imprimir versión con comando simple (sin heredoc)
RUN python -c "import openai; print('OpenAI SDK version:', openai.__version__)"

EXPOSE 10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
