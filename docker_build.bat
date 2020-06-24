docker build -t cr.yandex/crpmg9qeitngo9ui36lc/vad-service-base:latest -f ./Dockerfile-base .
docker build -t cr.yandex/crpmg9qeitngo9ui36lc/vad-service-prod:latest -f ./Dockerfile .
docker push cr.yandex/crpmg9qeitngo9ui36lc/vad-service-base:latest
docker push cr.yandex/crpmg9qeitngo9ui36lc/vad-service-prod:latest