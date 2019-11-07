# coding=utf-8

import os
import math
import ntpath
import random
import shutil
import subprocess
from subprocess import Popen, PIPE
import datetime
from pydub import AudioSegment
import tempfile
import uuid


class LiveCorpusHelper:
    def __init__(self, noise_files_list=[]):
        self.__maximal_volume_adjustment_for_noise_file = 2
        self.__minimal_volume_adjustment_for_clean_file = 3
        self.__minimal_volume_adjustment_for_noise = 1.75

        self.__noise_segments = []
        if len(noise_files_list) > 0:
            # Initialise noise files pydub segments
            print('AudioHelper: Try: Initialise noise files to pydub segments')
            noise_initialisation_start_time = datetime.datetime.now()
            for noise_file_path in noise_files_list:
                self.__init_noise_file(noise_file_path)

            noise_initialisation_end_time = datetime.datetime.now()
            print(f'AudioHelper: Success: Initialised {len(noise_files_list)} noise files')
            print(f'AudioHelper: Success: Initialisation of noise files done. Takes {noise_initialisation_end_time - noise_initialisation_start_time}')

    def __init_noise_file(self, noise_file_path):
        noise_segment = AudioSegment.from_mp3(noise_file_path)
        self.__noise_segments.append(noise_segment)

    @staticmethod
    def get_three_formatted_number(number):
        res = "{:03d}".format(number)
        return res

    def inject_noise_to_file(self, target_file_path, noise_frame_rate, normalize_voice, denormalize_noise, normalize_noise,
                             noise_file_path='', noise_file_segment=object(),
                             noisered_audio_path=''):
        input_file_segment = AudioSegment.from_mp3(target_file_path)
        input_file_duration = input_file_segment.duration_seconds * 1000

        if type(noise_file_segment) != AudioSegment:
            if len(self.__noise_segments) > 0:
                # Get noise segment object from existed array
                noise_index = random.randint(0, len(self.__noise_segments) - 1)
                noise_file_segment = self.__noise_segments[noise_index]
                while noise_file_segment.duration_seconds < input_file_segment.duration_seconds:
                    noise_index = random.randint(0, len(self.__noise_segments) - 1)
                    noise_file_segment = self.__noise_segments[noise_index]
            else:
                noise_file_segment = AudioSegment.from_mp3(noise_file_path)

        # Array with temp files that have to be cleaned
        artifacts_to_clean = []

        noise_file_duration = noise_file_segment.duration_seconds * 1000
        if noise_file_segment.duration_seconds < input_file_segment.duration_seconds:
            print(f'Selected noise object duration is: {noise_file_segment.duration_seconds}')
            # Repeat noise file until we will have enough length
            target_noise_part = noise_file_segment
            while target_noise_part.duration_seconds < input_file_segment.duration_seconds:
                target_noise_part = target_noise_part + noise_file_segment
            if target_noise_part.duration_seconds > input_file_segment.duration_seconds:
                target_noise_part = target_noise_part[0:input_file_segment.duration_seconds*1000]
            target_noise_part = target_noise_part[0:input_file_segment.duration_seconds * 1000]
        else:
            noise_file_start = random.randint(0, math.floor(noise_file_duration - input_file_duration))
            noise_file_end = noise_file_start + input_file_duration
            noise_file_segment = noise_file_segment.set_frame_rate(noise_frame_rate)
            target_noise_part = noise_file_segment[noise_file_start:noise_file_end]

        assert target_noise_part.duration_seconds == input_file_segment.duration_seconds

        noise_file_name = 'noise_{0}.mp3'.format(str(uuid.uuid4().hex))
        temp_noise_part_file_path = os.path.join(tempfile.gettempdir(), noise_file_name)
        target_noise_part.export(temp_noise_part_file_path, format="mp3")
        artifacts_to_clean.append(temp_noise_part_file_path)

        # Check that noise file has predicted duration
        noise_check_obj = AudioSegment.from_mp3(temp_noise_part_file_path)
        assert noise_check_obj.duration_seconds == input_file_segment.duration_seconds

        # Get volume adjustment values for noise temp file and downgrade it if necessary
        noise_file_vol_adj = self.get_volume_adjustment(temp_noise_part_file_path)
        if noise_file_vol_adj == 0:
            msg = f'0 Volume adjustment for file "{noise_file_name}"'
            print(msg)
            raise Exception(msg)
        if denormalize_noise and noise_file_vol_adj < self.__maximal_volume_adjustment_for_noise_file:
            target_va_val = 1 / noise_file_vol_adj
            if target_va_val < 1:
                print(f'Denormalize noise file for VA: {target_va_val}', flush=True)
                noise_file_normalised_name = noise_file_name.replace('.mp3', '' + '_normalized.mp3')
                noise_file_normalised_path = temp_noise_part_file_path.replace(noise_file_name, noise_file_normalised_name)
                self.normalize_volume(temp_noise_part_file_path, noise_file_normalised_path, target_va_val)
                temp_noise_part_file_path = noise_file_normalised_path
                artifacts_to_clean.append(temp_noise_part_file_path)
        if normalize_noise and noise_file_vol_adj > self.__minimal_volume_adjustment_for_noise:
            print(f'Normalize noise file for VA: {noise_file_vol_adj}', flush=True)
            noise_file_normalised_name = noise_file_name.replace('.mp3', '' + '_normalized.mp3')
            noise_file_normalised_path = temp_noise_part_file_path.replace(noise_file_name, noise_file_normalised_name)
            self.normalize_volume(temp_noise_part_file_path, noise_file_normalised_path, noise_file_vol_adj)
            temp_noise_part_file_path = noise_file_normalised_path
            artifacts_to_clean.append(temp_noise_part_file_path)

        output_file_path = noisered_audio_path
        if len(noisered_audio_path) == 0:
            file_name = ntpath.basename(target_file_path)
            dir = ntpath.dirname(target_file_path)
            output_file_path = os.path.join(dir, 'noisered_' + file_name)

        self.merge_files_ffmpeg(target_file_path, temp_noise_part_file_path, output_file_path)

        # Cleanup temp noise file
        for tmp_file_path in artifacts_to_clean:
            os.remove(tmp_file_path)

    def inject_noise_dir(self, noise_file_path, target_dir_path):
        noise_files_list = [f for f in os.listdir(target_dir_path) if os.path.isfile(os.path.join(target_dir_path, f))]
        for file_to_noise in noise_files_list:
            file_to_noise_full_path = os.path.join(target_dir_path, file_to_noise)
            self.inject_noise_to_file(noise_file_path, file_to_noise_full_path)

    @staticmethod
    def merge_files_sox(file_1_full_path, file_2_full_path, output_file_path):
        # Example of sox call is
        # sox -m new_input.wav myrecording.wav output_test.aiff
        process = Popen(["sox",
                        '-m',
                        file_1_full_path,
                        file_2_full_path,
                        output_file_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()

    @staticmethod
    def merge_files_ffmpeg(file_1_full_path, file_2_full_path, output_file_path):
        # Example of sox call is
        # ffmpeg -i input0.mp3 -i input1.mp3 -filter_complex amix=inputs=2:duration=longest output.mp3
        process = Popen(["ffmpeg",
                        '-i',
                        file_1_full_path,
                         '-i',
                        file_2_full_path,
                        '-filter_complex',
                        'amix=inputs=2:duration=longest',
                        output_file_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        # print(stdout.decode("utf-8"))
        # print(stderr.decode("utf-8"))

    @staticmethod
    def is_file_stereo(file_full_path):
        # Example of ffmpeg call is
        # ffmpeg -i some_rec.mp3
        process = Popen(["ffmpeg", '-i', file_full_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stderr_str = stderr.decode("utf-8")
        res = stderr_str.find('stereo') > -1
        return res

    @staticmethod
    def get_file_diration(file_full_path) -> float:
        # Example of ffmpeg call is
        # ffmpeg -i some_rec.mp3
        process = Popen(["ffmpeg", '-i', file_full_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stderr_str = stderr.decode("utf-8")
        for line in stderr_str.split('\n'):
            # example of line is:  Duration: 00:29:07.04, start: 0.000000, bitrate: 128 kb/s
            if 'Duration' in line:
                entries = line.split(' ')
                entries = [x for x in entries if len(x)>0]
                cleaned_entry = entries[1].replace('\r', '').replace('\n', '').replace('\t', '').replace(',', '')
                time_entries = cleaned_entry.split(':')
                hours_secs = float(time_entries[0]) * 60 * 60
                mins_secs = float(time_entries[1]) * 60
                secs_secs = float(time_entries[2])
                res = hours_secs + mins_secs + secs_secs
                return res

    @staticmethod
    def merge_stereo_sox(file_full_path, output_file_path=''):
        # Example of sox call is
        # sox in_file.mp3 out_file.mp3 remix 1,2
        need_to_replace_with_buf = len(output_file_path) == 0

        if need_to_replace_with_buf:
            file_name_with_ext = os.path.basename(file_full_path)
            file_name_without_ext = file_name_with_ext.replace('.mp3', '')
            temp_file_path = os.path.join(os.path.dirname(file_full_path), '{0}_merged.mp3'.format(file_name_without_ext))
            output_file_path = temp_file_path

        subprocess.call(["sox",
                         file_full_path,
                         output_file_path,
                         'remix',
                         '1,2'])

        if need_to_replace_with_buf:
            os.remove(file_full_path)
            shutil.copy(output_file_path, file_full_path)
            os.remove(output_file_path)

    @staticmethod
    def get_volume_adjustment(file_path):
        def float_try_parse(value):
            try:
                return float(value)
            except ValueError:
                return False

        # sox somefile.mp3 -n stat
        process = Popen([
            "sox",
            file_path,
            "-n",
            "stat"], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        stderr_str = stderr.decode("utf-8")

        volume_adjustment_val = 0

        for line in stderr_str.split('\n'):
            # example of line is: Volume adjustment:    3.585
            if 'Volume adjustment' in line:
                entries = line.split(' ')
                for entry in entries:
                    cleaned_entry = entry.replace('\r', '').replace('\n', '').replace('\t', '')
                    parsed_val = float_try_parse(cleaned_entry)
                    if parsed_val != False:
                        volume_adjustment_val = parsed_val

        return volume_adjustment_val

    def normalize_volume(self, file_path, out_file_path, vol_adjustment=0):
        # Get value of volume adjustment parameter
        if vol_adjustment == 0:
            vol_adjustment = self.get_volume_adjustment(file_path)

        # sox -v 2.9 somefile.mp3 -
        process = Popen(['sox',
                         '-v',
                         str(vol_adjustment),
                         file_path,
                         out_file_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        # print(stderr.decode("utf-8"))
        assert os.path.isfile(out_file_path)

    @staticmethod
    def create_track_fragment(in_file_path, out_file_path, start_str, end_str):
        # example of call is "ffmpeg -acodec copy -ss 00:00:00 -to 00:00:15 /out/path/file.mp3"
        process = Popen(['ffmpeg',
                         '-i',
                         in_file_path,
                         '-acodec',
                         'copy',
                         '-ss',
                         start_str,
                         '-to',
                         end_str,
                         out_file_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        assert os.path.isfile(out_file_path)

    def trim_edges(self, in_file_path, out_file_path, silence_threshold=-35.0):
        def detect_leading_silence(sound_obj, silence_threshold=-35.0, chunk_size=10):
            '''
            sound_obj is a pydub.AudioSegment
            silence_threshold in dB
            chunk_size in ms

            iterate over chunks until you find the first one with sound
            '''

            trim_ms = 0  # ms
            assert chunk_size > 0  # to avoid infinite loop
            while sound_obj[trim_ms:trim_ms + chunk_size].dBFS < silence_threshold and trim_ms < len(sound_obj):
                trim_ms += chunk_size

            return trim_ms

        base_admission = 50
        sound = AudioSegment.from_mp3(in_file_path)

        start_trim = detect_leading_silence(sound, silence_threshold)
        end_trim = detect_leading_silence(sound.reverse(), silence_threshold)

        duration = len(sound)
        start_trim = start_trim - base_admission
        end_trim = duration - end_trim + base_admission
        trimmed_sound = sound[start_trim: end_trim]
        trimmed_sound.export(out_file_path, format='mp3')