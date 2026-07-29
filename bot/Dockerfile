FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# NOTA: el build context de esta imagen debe ser la RAIZ del repo (no bot/),
# para poder copiar el certificado compartido con ms_ekogui.
# Ej: docker build -f bot/Dockerfile -t bot .
COPY bot/requirements.txt /app/
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

COPY bot/ /app/
COPY shared/ /app/shared/

CMD ["python", "main.py"]
