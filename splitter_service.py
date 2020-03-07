import ntpath
import os
import traceback
import subprocess
import requests
import tempfile
from datetime import datetime
import logging
import pika
import json
import yaml
from windows_extractor import get_windows_from_annotated_data
import vad_extract

# For DEBUG purpose
import sys
import numpy
numpy.set_printoptions(threshold=sys.maxsize)



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
        self.__amqp_port = config['port']
        self.__user_name = config['user_name']
        self.__password = config['password']

        self.__vad_labels_only = config['vad_labels_only']

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
        # Load file from url
        long_file_name = get_file_name_from_url(file_url)
        question_mark_index = long_file_name.find('?')
        if question_mark_index > -1:
            long_file_name = long_file_name[0:question_mark_index]
        long_file_path = os.path.join(tempfile.gettempdir(), long_file_name)
        if not os.path.exists(long_file_path):
            self.__logger.debug(f'TRY: Save initial file to {long_file_path}')
            upload_and_save_file(file_url, long_file_path)
            self.__logger.debug(f'SUCCESS: Initial file saved to {long_file_path}')

        # Convert file to wav extension
        target_sample_rate = 44100
        wav_file_name = get_file_name_from_path(long_file_path).replace('.mp3', '.wav')
        wav_file_path = os.path.join(tempfile.gettempdir(), wav_file_name)
        if not os.path.isfile(wav_file_path):
            self.__logger.debug(
                f'TRY: Convert initial mp3 file to wav extension ("{long_file_path}" -> "{wav_file_path}")')
            process = subprocess.Popen(["sox",
                                        long_file_path,
                                        '-r',
                                        str(target_sample_rate),
                                        wav_file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            logging.debug(stdout.decode('utf-8'))
            logging.debug(stderr.decode('utf-8'))
            assert os.path.isfile(wav_file_path)
            self.__logger.debug(f'SUCCESS: Convert initial mp3 file to wav extension')

        seconds_stamps = self.__vad.extract_voice(wav_file_path)

        # Initially we have a list of datetime values for transactions info
        # Need to transform it to relative timestamps
        time_windows = []
        if not (self.__vad_labels_only):
            end_timestamps_list = []
            if end_datetime_list is not None and len(end_datetime_list) > 0:
                file_absolute_time_start_dte = datetime.strptime(file_absolute_time_start, '%Y-%m-%dT%H:%M:%S')
                for end_datetime_str in end_datetime_list:
                    end_datetime = datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M:%S')
                    end_timestamp = end_datetime - file_absolute_time_start_dte
                    end_timestamps_list.append(end_timestamp.total_seconds())

                time_windows = get_windows_from_annotated_data(end_timestamps_list, seconds_stamps)

        res = {}
        res['Tokens'] = time_windows
        res['SecondsVADLabels'] = seconds_stamps.tolist()
        return res

    def __handle_delivery(self, channel, method_frame, header_frame, body):
        body_str = body.decode('utf-8')
        self.__logger.info('Got new splitting request: ', body_str)
        req = json.loads(body_str)
        self.__channel.basic_ack(delivery_tag=method_frame.delivery_tag)

        try:
            res_obj = self.__get_file_tokens(
                start_timestamps_list=req['StartTimeStampsList'],
                end_datetime_list=req['EndTimeStampsList'],
                file_url=req['FileUrl'],
                file_absolute_time_start=req['FileAbsoluteStartDate'])
            self.__push_message(header_frame.reply_to, header_frame.correlation_id, res_obj)
        except Exception as exc:
            str_exc = str(exc)
            tb = traceback.format_exc()
            str_exc += '\n' + tb
            self.__logger.error(str_exc)
            res_obj = {'ErrorMessage': str_exc}
            self.__push_message(header_frame.reply_to, header_frame.correlation_id, res_obj)

    def __push_message(self, reply_to_key, correlation_id, res_obj):
        res = res_obj
        body = json.dumps(res)
        msg_type = 'Loyalty.Audio.VAD.VADResponse, Loyalty.Audio.VAD'
        props = pika.BasicProperties(correlation_id=correlation_id, type=msg_type)
        self.__logger.debug(f'Publish message to queue {reply_to_key}. Body: {body}')
        self.__channel.basic_publish(exchange=self.__exchange_name, routing_key=reply_to_key, body=body, properties=props)

    def run_listener(self):
        try:
            self.__logger.debug(f'Connecting to AMQP server with username {self.__user_name}')
            credentials = pika.PlainCredentials(self.__user_name, self.__password)
            parameters = pika.ConnectionParameters(host=self.__amqp_host, port=self.__amqp_port,  credentials=credentials)
            connection = pika.BlockingConnection(parameters)

            self.__channel = connection.channel()
            self.__logger.debug(f'Channel created top host {self.__amqp_host}')

            self.__channel.queue_declare(queue=self.__in_queue_name, durable=True, exclusive=False, auto_delete=False)
            self.__channel.queue_bind(queue=self.__in_queue_name, exchange=self.__exchange_name, routing_key=self.__in_queue_name)
            self.__logger.debug(f'Exchange is "{self.__exchange_name}". Queue is "{self.__in_queue_name}'"")
            self.__channel.basic_consume(queue=self.__in_queue_name, on_message_callback=self.__handle_delivery)

            self.__logger.debug(f'Activate blocking listening for queue {self.__in_queue_name}')
            self.__channel.start_consuming()
        except KeyboardInterrupt:
            self.__channel.stop_consuming()
            connection.close()
            connection.ioloop.stop()
        except Exception as e:
            self.__logger.error(e)
            self.run_listener()


def main():
    config_file_path = 'config.yml'
    listener = SplitterAMQPService(config_file_path)
    print(f'Activating AMQP listener service')
    listener.run_listener()


if __name__ == "__main__":
    main()
