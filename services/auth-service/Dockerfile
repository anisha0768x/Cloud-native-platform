FROM python:3.13-slim
WORKDIR /app
RUN useradd --create-home appuser
COPY services/auth-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/auth-service /app/service
WORKDIR /app/service
USER appuser
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
