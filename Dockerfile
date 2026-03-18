FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY google_scraper.py api.py .
RUN mkdir -p output

CMD ["python", "api.py"]
