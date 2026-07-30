FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libreoffice-writer/-calc: convierten Word (.doc/.docx) y Excel (.xls/.xlsx)
# a PDF sin tocar su contenido. wkhtmltopdf: convierte HTML a PDF (pdfkit).
# unar: extraer .rar (unrar es de licencia no-libre y no esta en main).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-calc \
    wkhtmltopdf \
    unar \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

COPY . /app

CMD ["python", "main.py"]
