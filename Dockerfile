FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends antiword poppler-utils tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng libarchive13 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home workspace && mkdir -p /app/runtime && chown workspace:workspace /app/runtime
USER workspace
EXPOSE 8000
CMD ["python","serve.py","--host","0.0.0.0","--port","8000"]
