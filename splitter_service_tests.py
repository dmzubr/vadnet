import os
from datetime import datetime
from pydub import AudioSegment

from splitter_service import get_file_tokens, get_file_name_from_path


def test_long_file_splitting():
    file_absolute_time_start_string = '2019-06-25T12:00:00'
    file_absolute_time_start = datetime.strptime(file_absolute_time_start_string, '%Y-%m-%dT%H:%M:%S')
    end_datetime_list = ['2019-06-25T12:18:15', '2019-06-25T12:21:43', '2019-06-25T12:23:44', '2019-06-25T12:26:50',
                         '2019-06-25T12:46:00', '2019-06-25T12:55:13']
    end_timestamps_list = []
    for end_datetime_str in end_datetime_list:
        end_datetime = datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M:%S')
        end_timestamp = end_datetime - file_absolute_time_start
        end_timestamps_list.append(end_timestamp.total_seconds())

    file_url = 'https://storage.yandexcloud.net/test-t/rigla_butirskaya_4_1.mp3'
    windows = get_file_tokens([], end_timestamps_list, file_url, file_absolute_time_start, 300)

    out_dir = '/home/dmzubr/Desktop/splitter/splitted/'
    full_file_name = '/tmp/rigla_butirskaya_4_1.wav'
    out_full_dir = os.path.join(out_dir, get_file_name_from_path(full_file_name).replace('.wav', ''))
    if not os.path.isdir(out_full_dir):
        os.makedirs(out_full_dir)

    full_file_seg = AudioSegment.from_wav(full_file_name)
    i = 1
    for window in windows:
        output_path = os.path.join(out_full_dir, 'chunk_%002d.mp3' % (i,))
        audio_part = full_file_seg[window['StartMilliseconds']:window['EndMilliseconds']]
        audio_part.export(output_path, format="mp3")
        i += 1

    exit(0)


def main():
    test_long_file_splitting()

