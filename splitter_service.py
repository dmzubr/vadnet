import ntpath
import os
import subprocess
import requests
import tempfile
from datetime import datetime
import logging
# from pydub import AudioSegment
from collections import deque
import pika
import json
import yaml
import uuid
import vad_extract


class Window(object):
    def __init__(self, start, end, frames):
        self.start = start
        self.end = end
        self.frames = frames


def get_file_name_from_url(url):
    res = url.rsplit('/', 1)[1]
    return res


def get_file_extension_from_url(url):
    file_name = get_file_name_from_url(url)
    res = file_name.rsplit('.', 1)[1]
    return res


def get_file_name_from_path(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


def get_dir_path_from_file_path(path):
    head, tail = ntpath.split(path)
    return head


def upload_and_save_file(file_url, out_file_path):
    r = requests.get(file_url, allow_redirects=True)
    open(out_file_path, 'wb').write(r.content)


class TimeWindow:
    def __init__(self, start_milliseconds, end_milliseconds):
        self.StartMilliseconds = start_milliseconds
        self.EndMilliseconds = end_milliseconds


class SplitterAMQPService:
    def __init__(self, config_file_path):
        self.__init_logger()

        if not os.path.isfile(config_file_path):
            self.__logger.error(f'Config file not found: {config_file_path}')
            raise FileNotFoundError

        with open(config_file_path, 'r') as stream:
            try:
                config = yaml.safe_load((stream))
            except yaml.YAMLError as exc:
                self.__logger.error(f"Can't parse config file")
                self.__logger.error(exc)

        self.__channel = None
        self.__in_queue_name = 'Loyalty.Audio.VAD.VADRequest, Loyalty.Audio.VAD'
        self.__exchange_name = config['exchange_name']  # 'easy_net_q_rpc'
        self.__amqp_host = config['amqp_host']
        self.__user_name = config['user_name']
        self.__password = config['password']

        # Init VAD nn service
        self.__vad = vad_extract.CNNNetVAD(256)

    def __init_logger(self):
        logging.getLogger('pika').setLevel(logging.WARNING)

        self.__logger = logging.getLogger()
        self.__logger.setLevel(logging.DEBUG)
        now = datetime.now()
        logs_dir = './logs'
        os.makedirs(logs_dir, exist_ok=True)

        fh = logging.FileHandler(f'./logs/audio_splitter-{now.strftime("%Y%m%d")}.log')
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        self.__logger.addHandler(fh)
        self.__logger.addHandler(ch)

    def __get_file_tokens(self, start_timestamps_list, end_datetime_list, file_url, file_absolute_time_start):
        target_windows = []

        # Initially we have a list of datetime values for transactions info
        # Need to transform it to relative timestamps
        end_timestamps_list = []
        file_absolute_time_start_dte = datetime.strptime(file_absolute_time_start, '%Y-%m-%dT%H:%M:%S')
        for end_datetime_str in end_datetime_list:
            end_datetime = datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M:%S')
            end_timestamp = end_datetime - file_absolute_time_start_dte
            end_timestamps_list.append(end_timestamp.total_seconds())

        # Load file from url
        long_file_name = get_file_name_from_url(file_url)
        long_file_path = os.path.join(tempfile.gettempdir(), long_file_name)
        if not os.path.exists(long_file_path):
            self.__logger.debug(f'TRY: Save initial file to {long_file_path}')
            upload_and_save_file(file_url, long_file_path)
            self.__logger.debug(f'SUCCESS: Initial file saved to {long_file_path}')

        # Convert file to wav extension
        wav_file_name = get_file_name_from_path(long_file_path).replace('.mp3', '.wav')
        wav_file_path = os.path.join(tempfile.gettempdir(), wav_file_name)
        if not os.path.isfile(wav_file_path):
            self.__logger.debug(
                f'TRY: Convert initial mp3 file to wav extension ("{long_file_path}" -> "{wav_file_path}")')
            process = subprocess.Popen(["sox",
                             long_file_path,
                             wav_file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            logging.debug(stdout.decode('utf-8'))
            logging.debug(stderr.decode('utf-8'))
            assert os.path.isfile(wav_file_path)
            self.__logger.debug(f'SUCCESS: Convert initial mp3 file to wav extension')

        seconds_stamps = self.__vad.extract_voice(wav_file_path)
        logging.info(seconds_stamps)

        return target_windows

        # audio, sample_rate = read_wave(wav_file_path)
        # vad = webrtcvad.Vad(int(agressiveness))
        # data_frames = frame_generator(assesed_frame_size, audio, sample_rate)
        # data_frames = list(data_frames)
        # vad_collector(sample_rate, assesed_frame_size, padding_window, vad, data_frames)
        #
        # target_windows = []
        # minimal_transaction_left_part_seconds = 30
        # left_padding_window_size = 150
        # minimal_left_part_voiced_samples_percent = 60
        # minimal_transaction_right_part_seconds = 20
        # right_padding_window_size = 100
        #
        # for end_timestamp in end_timestamps_list:
        #     near_frames = [x for x in data_frames if abs(end_timestamp - x.timestamp) < 0.1]
        #     target_frame = near_frames[0]
        #     target_frame_index = data_frames.index(target_frame)
        #
        #     # Go left from time of transaction end
        #     left_shift_seconds = 400
        #     left_edge_frame = near_frames[0]
        #     left_index_shift = 0
        #
        #     overlapped_transactions = [x for x in end_timestamps_list if
        #                                x < target_frame.timestamp and x > target_frame.timestamp - left_shift_seconds]
        #     if len(overlapped_transactions) > 0:
        #         left_shift_seconds = overlapped_transactions[
        #                                  len(overlapped_transactions) - 1] + minimal_transaction_right_part_seconds
        #         logger.debug(
        #             f'There is a transaction in left padding of current transaction. So move left to {left_shift_seconds}s')
        #         left_edge_frame = [x for x in data_frames if abs(x.timestamp - left_shift_seconds) < 0.1][0]
        #         left_edge_frame_current_index = data_frames.index(left_edge_frame)
        #         left_index_shift = target_frame_index - left_edge_frame_current_index
        #     else:
        #         while target_frame.timestamp - left_edge_frame.timestamp < left_shift_seconds:
        #             if left_edge_frame.timestamp == 0:
        #                 left_index_shift -= 1
        #                 break
        #             left_edge_frame = data_frames[target_frame_index - left_index_shift]
        #             left_index_shift += 1
        #
        #     logger.debug(f'Initial left edge frame is on timestamp {left_edge_frame.timestamp}')
        #     logger.debug(f'Go to right to find empty (without voice) frames')
        #
        #     left_append_queue = deque(maxlen=left_padding_window_size)
        #
        #     while target_frame.timestamp > left_edge_frame.timestamp:
        #         left_edge_frame = data_frames[target_frame_index - left_index_shift]
        #
        #         #  Fill queue with current frame
        #         left_append_queue.append(left_edge_frame)
        #
        #         if len(left_append_queue) == left_padding_window_size:
        #             # Check do not we already go too far right. Because there is a minimal left padding
        #             if left_edge_frame.timestamp > data_frames[
        #                 target_frame_index].timestamp - minimal_transaction_left_part_seconds:
        #                 break
        #
        #             # Check - do we need to stop moving right.
        #             # We should stop if see that current window state has enough voiced samples
        #             voiced_frames_count = len([x for x in left_append_queue if x.is_voiced])
        #             percentage_of_voiced_samples = voiced_frames_count / len(left_append_queue) * 100
        #             if percentage_of_voiced_samples > minimal_left_part_voiced_samples_percent:
        #                 break
        #
        #         left_index_shift -= 1
        #
        #     # right from time of transaction end
        #     maximal_inner_transaction_right_silence_frames_count = 35
        #     minimal_right_part_voiced_samples_percent = 60
        #     right_shift_seconds = 100
        #     right_edge_frame = near_frames[0]
        #     right_index_shift = 0
        #
        #     overlapped_transactions = [x for x in end_timestamps_list if
        #                                x > target_frame.timestamp and x < target_frame.timestamp + right_shift_seconds]
        #     if len(overlapped_transactions) > 0 and (overlapped_transactions[0] - target_frame.timestamp > 1):
        #         right_shift_seconds = overlapped_transactions[
        #                                   len(overlapped_transactions) - 1] - minimal_transaction_left_part_seconds
        #         logger.debug(
        #             f'There is a transaction in right padding of current transaction. So move right to {right_shift_seconds}s')
        #         right_edge_frame = [x for x in data_frames if abs(x.timestamp - right_shift_seconds) < 0.1][0]
        #         right_edge_frame_current_index = data_frames.index(right_edge_frame)
        #         right_index_shift = target_frame_index + right_edge_frame_current_index
        #     else:
        #         while right_edge_frame.timestamp - target_frame.timestamp < right_shift_seconds:
        #             if right_edge_frame.timestamp == 0:
        #                 right_index_shift += 1
        #                 break
        #             right_edge_frame = data_frames[target_frame_index + right_index_shift]
        #             right_index_shift += 1
        #
        #     logger.debug(f'Initial right edge frame is on timestamp {right_edge_frame.timestamp}')
        #     logger.debug(f'Go to left to find empty (without voice) frames')
        #
        #     right_append_queue = deque(maxlen=right_padding_window_size)
        #
        #     while right_edge_frame.timestamp > target_frame.timestamp:
        #         right_edge_frame = data_frames[target_frame_index + right_index_shift]
        #
        #         #  Fill queue with current frame
        #         right_append_queue.append(right_edge_frame)
        #
        #         if len(right_append_queue) == right_padding_window_size:
        #             # Check do not we already go too far left. Because there is a minimal right padding
        #             if right_edge_frame.timestamp < data_frames[
        #                 target_frame_index].timestamp + minimal_transaction_right_part_seconds:
        #                 break
        #
        #             # Check - do we need to stop moving left.
        #             # We should stop if see that current window state has enough voiced samples
        #             voiced_frames_count = len([x for x in right_append_queue if x.is_voiced])
        #             percentage_of_voiced_samples = voiced_frames_count / len(left_append_queue) * 100
        #             if percentage_of_voiced_samples > minimal_right_part_voiced_samples_percent:
        #                 break
        #
        #         right_index_shift -= 1
        #
        #     resulting_left_edge_stamp = data_frames[
        #         target_frame_index - left_index_shift - left_padding_window_size].timestamp
        #     logger.debug(f'Resulting left edge timestamp is: {resulting_left_edge_stamp}')
        #
        #     resulting_right_edge_stamp = data_frames[
        #         target_frame_index + right_index_shift + right_padding_window_size].timestamp
        #     # resulting_right_edge_stamp = target_frame.timestamp + minimal_transaction_right_part_seconds
        #     logger.debug(f'Resulting right edge timestamp is: {resulting_right_edge_stamp}')
        #
        #     window = {
        #         'StartMilliseconds': int(resulting_left_edge_stamp * 1000),
        #         'EndMilliseconds': int(resulting_right_edge_stamp * 1000)
        #     }
        #     target_windows.append(window)
        #
        # logger.debug('Ensure that chunks does not have overlaps')
        # for i in range(0, len(target_windows)):
        #     if i < len(target_windows) - 1:
        #         window = target_windows[i]
        #         next_window = target_windows[i + 1]
        #         if next_window['StartMilliseconds'] < window['EndMilliseconds']:
        #             window['EndMilliseconds'] = next_window['StartMilliseconds']
        #
        # logger.info('Resulting windows are')
        # logger.info(target_windows)

    def __handle_delivery(self, channel, method_frame, header_frame, body):
        #self.__
        body_str = body.decode('utf-8')
        self.__logger.info('Got new splitting request: ', body_str)
        req = json.loads(body_str)
        self.__channel.basic_ack(delivery_tag=method_frame.delivery_tag)

        windows_list = self.__get_file_tokens(
            start_timestamps_list=req['StartTimeStampsList'],
            end_datetime_list=req['EndTimeStampsList'],
            file_url=req['FileUrl'],
            file_absolute_time_start=req['FileAbsoluteStartDate'])

        self.__push_message(header_frame.reply_to, header_frame.correlation_id, windows_list)

    def __push_message(self, reply_ro_key, correlation_id, windows_list):
        res = {'Tokens': windows_list}
        body = json.dumps(res)
        msg_type = 'Loyalty.Audio.VAD.VADResponse, Loyalty.Audio.VAD'
        props = pika.BasicProperties(correlation_id=correlation_id, type=msg_type)
        self.__logger.debug(f'Publish message to queue {reply_ro_key}. Body: {body}')
        self.__channel.basic_publish(exchange=self.__exchange_name, routing_key=reply_ro_key, body=body, properties=props)

    def run_listener(self):
        self.__logger.debug(f'Connecting to AMQP server with username {self.__user_name}')
        credentials = pika.PlainCredentials(self.__user_name, self.__password)
        parameters = pika.ConnectionParameters(host=self.__amqp_host, credentials=credentials)
        connection = pika.BlockingConnection(parameters)

        self.__channel = connection.channel()
        self.__logger.debug(f'Channel created top host {self.__amqp_host}')

        self.__channel.queue_declare(queue=self.__in_queue_name, durable=True, exclusive=False, auto_delete=False)
        self.__channel.queue_bind(queue=self.__in_queue_name, exchange=self.__exchange_name, routing_key=self.__in_queue_name)
        self.__logger.debug(f'Exchange is "{self.__exchange_name}". Queue is "{self.__in_queue_name}'"")
        self.__channel.basic_consume(queue=self.__in_queue_name, on_message_callback=self.__handle_delivery)

        try:
            self.__logger.debug(f'Activate blocking listening for queue {self.__in_queue_name}')
            self.__channel.start_consuming()
        except KeyboardInterrupt:
            self.__channel.stop_consuming()
            connection.close()
            connection.ioloop.stop()


def main():
    config_file_path = '/root/vad_service/config.yml'
    listener = SplitterAMQPService(config_file_path)
    listener.run_listener()


if __name__ == "__main__":
    main()
