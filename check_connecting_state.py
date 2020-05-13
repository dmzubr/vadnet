import pika
import yaml

# For DEBUG purpose
import sys
import numpy
numpy.set_printoptions(threshold=sys.maxsize)


class SplitterAMQPService:
    def __init__(self, config_file_path):

        with open(config_file_path, 'r') as stream:
            config = yaml.safe_load(stream)

        self.__channel = None
        self.__in_queue_name = 'Loyalty.Audio.VAD.StabReq, Loyalty.Audio.VAD'
        self.__exchange_name = config['exchange_name']  # 'easy_net_q_rpc'
        self.__amqp_host = config['amqp_host']
        self.__amqp_port = config['port']
        self.__user_name = config['user_name']
        self.__password = config['password']

    def __handle_delivery(self, channel, method_frame, header_frame, body):
        pass

    def __push_message(self, reply_to_key, correlation_id, res_obj):
        pass

    def run_listener(self):
        while True:
            try:
                print('Try to connect')
                credentials = pika.PlainCredentials(self.__user_name, self.__password)
                parameters = pika.ConnectionParameters(host=self.__amqp_host, port=self.__amqp_port,  credentials=credentials)
                connection = pika.BlockingConnection(parameters)

                self.__channel = connection.channel()

                self.__channel.queue_declare(queue=self.__in_queue_name, durable=True, exclusive=False, auto_delete=False)
                self.__channel.queue_bind(queue=self.__in_queue_name, exchange=self.__exchange_name, routing_key=self.__in_queue_name)
                self.__channel.basic_consume(queue=self.__in_queue_name, on_message_callback=self.__handle_delivery)
                try:
                    self.__channel.start_consuming()
                except KeyboardInterrupt:
                    self.__channel.stop_consuming()
                    connection.close()
                    connection.ioloop.stop()
            except Exception as e:
                print(e)
                continue


def main():
    config_file_path = 'config.yml'
    listener = SplitterAMQPService(config_file_path)
    print(f'Activating AMQP listener service')
    listener.run_listener()


if __name__ == "__main__":
    main()
