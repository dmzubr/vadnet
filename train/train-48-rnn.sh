python code/main.py \
--source source.audio_vad_files.AudioVadFiles \
--model model.model.Model \
--trainer trainer.adam.SceAdam \
--retrain False \
--output_dir nets \
--learning_rate 0.0001 \
--n_batch 512 \
--network network.crnn.Conv7Rnn \
\
--rnn_apply True \
--n_rnn_layers 2 \
--n_rnn_units 128 \
\
--sample_rate=48000 \
--n_frame 48000 \
--n_step 24000 \
\
--conv_stride 2 \
--conv_pool_stride 2 \
--conv_pool_size 4 \
\
--files_root /home/gpn/vadnet_train/out_files \
--files_audio_ext .wav \
--files_anno_ext .annotation \
\
--n_epochs 25