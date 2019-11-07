# coding=utf-8
import os
import tempfile
import uuid

from pydub import AudioSegment
from pydub.generators import WhiteNoise
from tqdm import tqdm
import random
import ntpath
import shutil
import multiprocessing

from sound_helper import LiveCorpusHelper

TARGET_SAMPLE_RATE = 48000
TARGET_CHANNELS = 1
TARGET_FORMAT = 'wav'
MINIMAL_SRC_FILE_DURATION = 3
OUT_DIR = '/home/dmzubr/gpn/vadnet_train/out_files'
ANNOTATION_FILE_FORMAT = '.annotation'
ANNOTATION_FILES_ENCODING = 'latin-1'
GAIN_DENORM_VAL = -30
WINDOW_LENGTH = 500
MAX_OUT_FILE_DUR_SECONDS = 100
MAX_SILENCE_LENGTH_SECONDS = 4
WITH_CLEANUP = False


def get_file_name_from_path(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(path)


def apply_gain_to_file(src_file_obj: AudioSegment, gained_file_path, gained_file_format):
    noise = WhiteNoise().to_audio_segment(duration=len(src_file_obj))
    noise = noise.apply_gain(GAIN_DENORM_VAL)
    combined = src_file_obj.overlay(noise)
    combined.export(gained_file_path, format=gained_file_format)
    assert os.path.exists(gained_file_path)


def create_voice_annotation_file(annotation_file_path, voice_windows):
    with open(annotation_file_path, 'w', encoding=ANNOTATION_FILES_ENCODING) as annot_f:
        for voice_window in voice_windows:
            annot_line = f"{voice_window['start_secs']};{voice_window['end_secs']};0;1.0\n"
            annot_f.write(annot_line)


def create_corpus():
    def get_noise_segment_object():
        noise_file_path = random.choice(noises_files)
        noise_obj = AudioSegment.from_mp3(noise_file_path)
        if noise_obj.duration_seconds > MAX_SILENCE_LENGTH_SECONDS:
            start_pos = random.randint(0,int(noise_obj.duration_seconds * 1000) - MAX_SILENCE_LENGTH_SECONDS * 1000)
            noise_obj = noise_obj[start_pos: start_pos + MAX_SILENCE_LENGTH_SECONDS*1000]
        else:
            mode_div = noise_obj.duration_seconds * 1000 / WINDOW_LENGTH
            if mode_div != 0:
                appended_silence_obj = AudioSegment.silent(mode_div)
                noise_obj = noise_obj + appended_silence_obj
        return noise_obj

    def call_multithreaded_work(voice_files_list, initial_file_counter: int = 1,
                                inject_noises: bool = False, norm_noise: bool = False,
                                denorm_noise: bool = False, trim_src_file: bool = False):
        procs_quantity = 4
        jobs = []
        current_part_duration = multiprocessing.Value('d')
        out_file_iterator = multiprocessing.Value('i')
        out_file_iterator.value = initial_file_counter

        for proc in range(0, procs_quantity):
            process = multiprocessing.Process(target=fill_corpus_from_voiced_list,
                                              args=(voice_files_list,
                                                    current_part_duration, out_file_iterator,
                                                    inject_noises, norm_noise,
                                                    denorm_noise, trim_src_file))
            jobs.append(process)

        for job in jobs:
            job.start()
        for job in jobs:
            job.join()

        return out_file_iterator.value

    def fill_corpus_from_voiced_list(voice_files_list,
                                     current_part_duration, out_file_iterator,
                                     inject_noises: bool = False,
                                     norm_noise=False, denorm_noise=False, trim_src_file: bool = False):
        # Current_part_duration and out_file_iterator are multithreaded objects wrappers
        temp_files = []

        created_files_quantity = 0

        # Configure randomizer
        seed_starter = random.randint(1, 10000)
        random.seed(seed_starter)

        while current_part_duration.value < part_target_duration:
            # Start file from noise (unvoiced) part
            voice_windows = []
            start_noise_obj = get_noise_segment_object()
            current_file_obj = start_noise_obj
            current_stamp = current_file_obj.duration_seconds

            while current_file_obj.duration_seconds < MAX_OUT_FILE_DUR_SECONDS:
                el = random.choice(voice_files_list)
                print(f'Handle initial file selection: {el}')
                voice_file_obj = AudioSegment.from_mp3(el)
                if voice_file_obj.duration_seconds < MINIMAL_SRC_FILE_DURATION:
                    print(f'Too short file ({voice_file_obj.duration_seconds}s): "{el}"')
                    continue
                try:

                    # Append target voice fragment to created file
                    if inject_noises:
                        print(f'Noising file {el}')
                        noisered_file_name = get_file_name_from_path(el).replace('.mp3', '') + str(uuid.uuid4()) + '_noisered.mp3'
                        noisered_file_path = os.path.join(tempfile.gettempdir(), noisered_file_name)
                        sound_helper.inject_noise_to_file(
                            target_file_path=el,
                            noise_frame_rate=TARGET_SAMPLE_RATE,
                            normalize_voice=False,
                            normalize_noise=norm_noise,
                            denormalize_noise=denorm_noise,
                            noisered_audio_path=noisered_file_path)
                        assert os.path.exists(noisered_file_path)
                        el = noisered_file_path
                        temp_files.append(noisered_file_path)
                    if trim_src_file:
                        trimmed_file_path = get_file_name_from_path(el).replace('.mp3', '') + '_trimmed.mp3'
                        trim_threshold = -35
                        sound_helper.trim_edges(el, trimmed_file_path, trim_threshold)
                        el = trimmed_file_path
                        temp_files.append(trimmed_file_path)

                    voice_file_obj = AudioSegment.from_mp3(el)
                    if voice_file_obj.duration_seconds < MINIMAL_SRC_FILE_DURATION:
                        print(f'Too short file ({voice_file_obj.duration_seconds}s): "{el}"')
                        continue
                    else:
                        voice_window_start = current_stamp
                        current_file_obj = current_file_obj + voice_file_obj
                        current_stamp = current_file_obj.duration_seconds
                        voice_window_end = current_stamp
                        voice_windows.append({'start_secs': voice_window_start, 'end_secs': voice_window_end})

                        # Append noise (not voiced) interval
                        noise_intarval_obj = get_noise_segment_object()
                        current_file_obj = current_file_obj + noise_intarval_obj
                        current_stamp = current_file_obj.duration_seconds
                        # pbar.update(current_stamp - voice_window_start)
                except Exception as exc:
                    print(f'Error on handling file "{el}"')

            # Save megred file
            target_file_name = f'{out_file_iterator.value}.{TARGET_FORMAT}'
            target_file_path = os.path.join(OUT_DIR, target_file_name)
            current_file_obj = current_file_obj.set_frame_rate(TARGET_SAMPLE_RATE)
            current_file_obj = current_file_obj.set_channels(TARGET_CHANNELS)
            current_file_obj.export(target_file_path, format=TARGET_FORMAT)
            assert os.path.exists(target_file_path)

            # Create annotation file
            annotation_file_name = f'{out_file_iterator.value}{ANNOTATION_FILE_FORMAT}'
            annotation_file_path = os.path.join(OUT_DIR, annotation_file_name)
            create_voice_annotation_file(annotation_file_path, voice_windows)

            out_file_iterator.value += 1
            current_part_duration.value += current_file_obj.duration_seconds
            created_files_quantity += 1

        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return created_files_quantity

    # Init noise (not voiced) files
    all_noise_files = []
    for noise_dir_path in [x['dir'] for x in noise_dirs if x['inject']]:
        all_noise_files = all_noise_files + [os.path.join(noise_dir_path, x) for x in os.listdir(noise_dir_path)]

    part_target_duration = 7500

    # print(f'Create part of clean voice (from synthesized voice), no noise')
    # initial_file_counter = 1
    # initial_file_counter = call_multithreaded_work(clean_voice_files, initial_file_counter=initial_file_counter)
    # print(f'Creating part of corpus done')

    # print(f'Create part of recorded voice (from synthesized voice), no noise')
    # initial_file_counter += 1
    # initial_file_counter = call_multithreaded_work(recorded_voice_files, initial_file_counter=initial_file_counter,
    #                                                trim_src_file=True)
    # print(f'Creating part of corpus done')


    print(f'Create part of clean voice injecting noise, no normalization-denormalization')
    initial_file_counter = 152
    initial_file_counter = call_multithreaded_work(clean_voice_files, initial_file_counter=initial_file_counter,
                                                   inject_noises=True, norm_noise=False, denorm_noise=False)
    print(f'Creating part of corpus done')

    # print(f'Create part of clean voice injecting noise, with noise denormalization')
    # initial_file_counter += 1
    # initial_file_counter = call_multithreaded_work(clean_voice_files, initial_file_counter=initial_file_counter,
    #                                                inject_noises=True, norm_noise=False, denorm_noise=True)
    # print(f'Creating part of corpus done')


noise_dirs = [
    {'dir': '/home/dmzubr/denoising/audio/noises/long', 'inject': True},
    {'dir': '/home/dmzubr/denoising/audio/noises/long', 'inject': True},
    {'dir': '/home/dmzubr/gpn/Voice_emotion_zdy/cashier_data/true/initial/', 'inject': False}
]
noises_files = []
for noise_dir in [x['dir'] for x in noise_dirs if x['inject']]:
    noises_files = noises_files + [os.path.join(noise_dir, x) for x in os.listdir(noise_dir)]

sound_helper = LiveCorpusHelper(noises_files)

# At the first will try when files are strongly divided. File should contain voice only or no voice at all
clean_voice_dir_root = '/media/dmzubr/Dat/audio/synthesis/ya_synthesized_books'
clean_voice_dirs = [os.path.join(clean_voice_dir_root, x) for x in os.listdir(clean_voice_dir_root)
                    if os.path.isdir(os.path.join(clean_voice_dir_root, x))]
print(f'Init clean voice files')
clean_voice_files = []
for clean_voice_dir in tqdm(clean_voice_dirs):
    cur_dir_file_paths = [os.path.join(clean_voice_dir, x) for x in os.listdir(clean_voice_dir)]
    clean_voice_files = clean_voice_files + cur_dir_file_paths
print(f'Got total {len(clean_voice_files)} clean voice files')

recorded_voice_m100_files_dir = '/media/dmzubr/Dat/audio/synthesis/recorded-m100-usb-synth/'
print(f'Initialise list of recorded voice files from "{recorded_voice_m100_files_dir}"')
recorded_voice_files = [os.path.join(recorded_voice_m100_files_dir, x) for x in os.listdir(recorded_voice_m100_files_dir)
                        if '.mp3' in x if '_trimmed' not in x]
print(f'Got {len(recorded_voice_files)} files')

if WITH_CLEANUP:
    shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

create_corpus()
