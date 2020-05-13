#sudo docker run --gpus=all -it --name vad_service --restart unless-stopped -v /home/dmzubr/gpn:/home/gpn docker-repo.rwad-tech.com/vad-service-prod:latest
#sudo docker run --gpus=all -it --name vad_service --restart always -v /home/dmzubr/gpn:/home/gpn docker-repo.cashee.ru/vad-service-prod:latest
sudo docker run --gpus=all -it --name vad_service --restart always docker-repo.cashee.ru/vad-service-prod:latest
# sudo docker run --gpus=all -it --name vad_service -v /home/dmzubr/vad:/vad --restart always docker-repo.cashee.ru/vad-service-prod:latest
# $sudo docker exec -it vad_service
