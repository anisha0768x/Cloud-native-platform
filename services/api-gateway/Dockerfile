FROM python:3.13-slim
WORKDIR /app
RUN useradd --create-home appuser
COPY services/api-gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . .
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
WORKDIR /app/services/api-gateway
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
