# ==================================================================
# module list
# ------------------------------------------------------------------
# ffmpeg libsndfile1 sox libsox-fmt-all              	(apt)
# librosa pyyaml pika requests pydub              	(pip)
# ==================================================================

FROM tensorflow/tensorflow:1.15.2-gpu-py3

RUN apt update
RUN apt install -y ffmpeg libsndfile1 sox libsox-fmt-all
RUN pip install librosa pyyaml pika requests pydub

WORKDIR /app
COPY . /app

ENTRYPOINT ["python", "/app/splitter_service.py"]
