import os
import subprocess

import tqdm
from pydub import AudioSegment
# from vad_extract_outer import CNNNetVAD


VAD_SAMPLE_RATE = 44100


in_files_dir = '/home/gpn/gpn_production_check/src/'
tmp_dir_path = '/home/gpn/gpn_production_check/temp/'
out_dir = '/home/dmzubr/gpn/gpn_production_check/speech/'


def perform_vad_detection():
    files_to_vad = os.listdir(in_files_dir)
    # files_to_vad = files_to_vad[0:2]

    # files_to_vad = [
    #     'device-1_20190923-185902.mp3',
    #     'device-1_20190924-194700.mp3'
    # ]

    # vad = CNNNetVAD(256)

    handled_files_list = []

    for file_to_vad in files_to_vad:
        print('------------------------------------------------------------------------------------')
        print(f'Handle file {len(handled_files_list) + 1} of {len(files_to_vad)}')
        print('------------------------------------------------------------------------------------')

        full_in_path = os.path.join(in_files_dir, file_to_vad)
        wav_in_file_path = os.path.join(tmp_dir_path, file_to_vad.replace('.mp3', '.wav'))
        vad_out_wav_name = file_to_vad.replace('.mp3', '') + '_speech.wav'
        vad_out_mp3_name = file_to_vad.replace('.mp3', '') + '_speech.mp3'
        vad_out_path = os.path.join(tmp_dir_path, vad_out_wav_name)

        if not os.path.isfile(vad_out_mp3_name):
            # Transform mp3 file to wav with target sample rate
            process = subprocess.Popen(["sox",
                full_in_path,
                '-r',
                str(VAD_SAMPLE_RATE),
                wav_in_file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            # Call VAD
            vad.extract_voice(wav_in_file_path, vad_out_path)
            assert os.path.isfile(vad_out_path)

            # Transform speech file to mp3 format
            speech_mp3_file_path = os.path.join(out_dir, vad_out_mp3_name)
            process = subprocess.Popen(["sox",
                                        vad_out_path,
                                        speech_mp3_file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            os.remove(wav_in_file_path)
            os.remove(vad_out_path)

        handled_files_list.append(vad_out_mp3_name)


def calculate_total_time():
    total_duration = 0
    bad_files = []

    speech_files = [os.path.join(out_dir, x) for x in os.listdir(out_dir)]
    for speech_file_path in tqdm.tqdm(speech_files):
        try:
            segm = AudioSegment.from_mp3(speech_file_path)
            total_duration += segm.duration_seconds
        except Exception as e:
            bad_files.append(speech_file_path)

    print(f'Total length is {total_duration}s')
    print(f'Bad files are {bad_files}s')


calculate_total_time()
