import os
import traceback
from datetime import datetime
import logging
import pika
import json
import yaml

from message_handler import VADMEssageHandler

# For DEBUG purpose
import sys
import numpy
numpy.set_printoptions(threshold=sys.maxsize)


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

        self.__response_object_provider = VADMEssageHandler(config_file_path)

    def __init_logger(self):
        logging.getLogger('pika').setLevel(logging.WARNING)
        logging.getLogger('tf').setLevel(logging.INFO)

        self.__logger = logging.getLogger()
        self.__logger.setLevel(logging.DEBUG)
        now = datetime.now()
        logs_dir = '/logs/'
        os.makedirs(logs_dir, exist_ok=True)

        fh = logging.FileHandler(f'{logs_dir}vad-{now.strftime("%Y%m%d")}.log')
        fh.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        self.__logger.addHandler(fh)
        self.__logger.addHandler(ch)
        self.__logger.info('Logger is initialised')

    def __handle_delivery(self, channel, method_frame, header_frame, body):
        body_str = body.decode('utf-8')
        self.__logger.info('Got new splitting request: ', body_str)
        req = json.loads(body_str)
        self.__channel.basic_ack(delivery_tag=method_frame.delivery_tag)

        try:
            # -------------- Call main business logic here
            res_obj = self.__response_object_provider.get_vad_response_obj(req)
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
        while True:
            try:
                self.__logger.info(f'Connecting to AMQP server with username {self.__user_name}')
                credentials = pika.PlainCredentials(self.__user_name, self.__password)
                parameters = pika.ConnectionParameters(host=self.__amqp_host, port=self.__amqp_port,  credentials=credentials)
                connection = pika.BlockingConnection(parameters)

                self.__channel = connection.channel()
                self.__logger.debug(f'Channel created top host {self.__amqp_host}')

                self.__channel.queue_declare(queue=self.__in_queue_name, durable=True, exclusive=False, auto_delete=False)
                self.__channel.queue_bind(queue=self.__in_queue_name, exchange=self.__exchange_name, routing_key=self.__in_queue_name)
                self.__logger.debug(f'Exchange is "{self.__exchange_name}". Queue is "{self.__in_queue_name}'"")
                self.__channel.basic_consume(queue=self.__in_queue_name, on_message_callback=self.__handle_delivery)

                self.__logger.info(f'Activate blocking listening for queue {self.__in_queue_name}')
                try:
                    self.__channel.start_consuming()
                except KeyboardInterrupt:
                    self.__channel.stop_consuming()
                    connection.close()
                    connection.ioloop.stop()
            except Exception as e:
                self.__logger.error(e)
                continue


def main():
    config_file_path = 'config.yml'
    listener = SplitterAMQPService(config_file_path)
    print(f'Activating AMQP listener service')
    listener.run_listener()


if __name__ == "__main__":
    main()
