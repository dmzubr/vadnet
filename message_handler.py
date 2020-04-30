import ntpath
import os
import subprocess
import requests
import tempfile
import logging
import yaml
from pydub import AudioSegment

import vad_extract
from vad_joint import VadJoint
from webrtc_vad import WebrtcvadWrapper, VadSegmentsAdjuster


class VADMEssageHandler:
    def __init__(self, config_file_path):
        self.__logger = logging.getLogger()

        if not os.path.isfile(config_file_path):
            self.__logger.error(f'Config file not found: {config_file_path}')
            raise FileNotFoundError

        with open(config_file_path, 'r') as stream:
            try:
                config = yaml.safe_load((stream))
            except yaml.YAMLError as exc:
                self.__logger.error(f"Can't parse config file")
                self.__logger.error(exc)

        self.__vad_labels_only = config['vad_labels_only']

        # Init VAD nn service
        vad_batch_size = config['vad_batch_size']
        vad_model_path = config['vad_model']
        self.__vad_manager = vad_extract.CNNNetVadExecutor(vad_batch_size, vad_model_path)

        self.__vad_joint = VadJoint()
        self.__webrtc_vad = WebrtcvadWrapper(share_voiced_samples_in_ring_buffer=0.9,  frame_duration_ms=30,
                                             padding_duration_ms=300, aggressiveness=3)
        self.__webrtc_vad_adjuster = VadSegmentsAdjuster()

        self.__temp_files = []

    @staticmethod
    def __get_file_name_from_path(path):
        head, tail = ntpath.split(path)
        return tail or ntpath.basename(head)

    @staticmethod
    def __upload_and_save_file(file_url, out_file_path):
        r = requests.get(file_url, allow_redirects=True)
        open(out_file_path, 'wb').write(r.content)

    @staticmethod
    def __get_file_name_from_url(url):
        res = url.rsplit('/', 1)[1]
        return res

    def __get_nn_vad_second_labels(self, initial_file_path):
        # Convert file to wav extension
        target_sample_rate = 44100
        wav_file_name = self.__get_file_name_from_path(initial_file_path).replace('.mp3', '.wav')
        wav_file_path = os.path.join(tempfile.gettempdir(), wav_file_name)
        if not os.path.isfile(wav_file_path):
            self.__logger.info(
                f'TRY: Convert initial mp3 file to wav extension for NN VAD ("{initial_file_path}" -> "{wav_file_path}")')
            process = subprocess.Popen(["sox",
                                        initial_file_path,
                                        '-r',
                                        str(target_sample_rate),
                                        wav_file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            logging.debug(stdout.decode('utf-8'))
            logging.debug(stderr.decode('utf-8'))
            assert os.path.isfile(wav_file_path)
            self.__logger.info(f'SUCCESS: Convert initial mp3 file to wav extension for NN VAD')
            self.__temp_files.append(wav_file_path)

        seconds_stamps = self.__vad_manager.extract_voice(wav_file_path)
        return seconds_stamps.tolist()

    def get_vad_response_obj(self, req_obj):
        def cleanup_temp_files():
            for file_path in self.__temp_files:
                if os.path.isfile(file_path):
                    os.remove(file_path)

        t = req_obj['VADType'].upper()
        use_nn_vad = t == 'NEURAL' or t == 'NN_AND_WEBRTC'
        use_webrtc_vad = t == 'WEBRTC' or t == 'NN_AND_WEBRTC'

        # Load file from url
        file_url = req_obj['FileUrl']
        long_file_name = self.__get_file_name_from_url(file_url)
        question_mark_index = long_file_name.find('?')
        if question_mark_index > -1:
            long_file_name = long_file_name[0:question_mark_index]
        long_file_path = os.path.join(tempfile.gettempdir(), long_file_name)
        if not os.path.exists(long_file_path):
            self.__logger.info(f'TRY: Save initial file to {long_file_path}')
            self.__upload_and_save_file(file_url, long_file_path)
            self.__logger.info(f'SUCCESS: Initial file saved to {long_file_path}')
            self.__temp_files.append(long_file_path)

        nn_segments = []
        nn_seconds_labels = []
        if use_nn_vad:
            nn_seconds_labels = self.__get_nn_vad_second_labels(long_file_path)
            nn_segments = self.__vad_joint.convert_vad_nn_bool_result(nn_seconds_labels)
            self.__logger.info(f'NN segments are: {nn_segments}')

        adjusted_vad_segments = []
        if use_webrtc_vad:
            vad_segments = self.__webrtc_vad.get_vad_segments(long_file_path)
            file_obj = AudioSegment.from_file(long_file_path)
            admissions = req_obj['WebRtcAdmissions']
            min_unvoiced_dur = req_obj['WebRtcMinimalUnvoicedWindowSeconds']
            adjusted_vad_segments = self.__webrtc_vad_adjuster.get_adjusted_segments(
                vad_segments, file_obj.duration_seconds, admissions, min_unvoiced_dur)
            self.__logger.info(f'Adjusted VAD segments are: {adjusted_vad_segments}')

        res_segments = self.__vad_joint.join_stamp_windows_list(nn_segments, adjusted_vad_segments)

        res = {}
        res['VoicedSegments'] = res_segments
        if len(nn_seconds_labels) > 0:
            res['SecondsVADLabels'] = nn_seconds_labels
        cleanup_temp_files()
        return res
