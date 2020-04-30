FROM docker-repo.cashee.ru/vad-service-base:latest

WORKDIR /app
COPY . /app

ENTRYPOINT ["python", "/app/splitter_service.py"]