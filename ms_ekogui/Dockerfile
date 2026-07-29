FROM python:3.12.11-slim-bookworm

WORKDIR /home/app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# NOTA: el build context de esta imagen debe ser la RAIZ del repo (no
# ms_ekogui/), para poder copiar el certificado compartido con el
# consumidor. Ej: docker build -f ms_ekogui/Dockerfile -t ms-ekogui .
COPY ms_ekogui/ /home/app/
COPY shared/ /home/app/shared/

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
#uvicorn main:app --host 0.0.0.0 --port 8000
