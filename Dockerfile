FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rename_documents.py .

CMD ["python", "rename_documents.py"]
