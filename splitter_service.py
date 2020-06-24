import json

from message_handler import VADMEssageHandler
from PyEasyNetQAdapter.rpc_server import ServiceBus

# For DEBUG purpose
import sys
import numpy
numpy.set_printoptions(threshold=sys.maxsize)


def on_request(body):
    body_str = body.decode('utf-8')
    request_body = json.loads(body_str)

    response_obj = response_object_provider.get_vad_response_obj(request_body)
    response_body = json.dumps(response_obj)

    return response_body


if __name__ == "__main__":
    response_object_provider = VADMEssageHandler('config.yml')
    service_bus = ServiceBus.from_config_file('config.yml')
    print(f'Activating AMQP listener service')
    service_bus.respond('Loyalty.Audio.VAD.VADRequest, Loyalty.Audio.VAD',
                        'Loyalty.Audio.VAD.VADResponse, Loyalty.Audio.VAD', on_request)
