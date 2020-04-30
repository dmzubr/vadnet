docker build -t docker-repo.cashee.ru/vad-service-base:latest -f ./Dockerfile-base .
docker build -t docker-repo.cashee.ru/vad-service-prod:latest -f ./Dockerfile .
docker push docker-repo.cashee.ru/vad-service-prod:latest