FROM cr.yandex/crpmg9qeitngo9ui36lc/vad-service-base:latest

WORKDIR /app
COPY . /app

RUN pip install PyEasyNetQAdapter.zip

ENTRYPOINT ["python", "/app/splitter_service.py"]