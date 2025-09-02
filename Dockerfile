# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 1) Copiá SOLO requirements primero para que el cache dependa del archivo
COPY requirements.txt /app/requirements.txt

# 2) Instalá dependencias (y actualizá pip). Acá se aplica tu openai>=1.45.0
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# 3) Ahora sí copiá el resto del código
COPY . /app

# 4) (Opcional pero útil) imprimí la versión de openai en el build log
RUN python - << 'PY'
import openai
print("OpenAI SDK version:", openai.__version__)
PY

# 5) Port
EXPOSE 10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
