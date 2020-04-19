'''
ssivad.py
author: Johannes Wagner <wagner@hcm-lab.de>
created: 2018/05/04
Copyright (C) University of Augsburg, Lab for Human Centered Multimedia

Returns energy of a signal (dimensionwise or overall)
'''

# https://stackoverflow.com/questions/35911252/disable-tensorflow-debugging-information
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import os, json, glob
import logging

import tensorflow as tf
tf.logging.set_verbosity(tf.logging.INFO)

import numpy as np
import librosa as lr
import subprocess
import pickle

from multiprocessing import Pool


def exec(file_path, cnn_batch_size, vad_model_path):
    vadnet = CNNNetVAD(cnn_batch_size, vad_model_path)
    vadnet.process(file_path)


class CNNNetVadExecutor:
    def __init__(self, cnn_batch_size, vad_model_path: str=''):
        self.__cnn_batch_size = cnn_batch_size
        self.__vad_model_path = vad_model_path
        pass

    def extract_voice(self, file_path):
        # https://github.com/tensorflow/tensorflow/issues/17048#issuecomment-368082470
        with Pool(1) as p:
            p.apply(exec, args=(file_path, self.__cnn_batch_size, self.__vad_model_path))

        assert os.path.isfile('vad_response.pickle')
        with open('vad_response.pickle', 'rb') as res_file_handle:
            res = pickle.load(res_file_handle)

        return res


class CNNNetVAD:
    def __init__(self, batch_size, model_path=''):
        self.__supported_extensions = ['wav']
        self.logger = logging.getLogger()
        self.batch_size = batch_size

        if len(model_path) == 0:
            model_path = '/app/models/vad'

        if os.path.isdir(model_path):
            candidates = glob.glob(os.path.join(model_path, 'model.ckpt-*.meta'))
            if candidates:
                candidates.sort()
                checkpoint_path, _ = os.path.splitext(candidates[-1])
        else:
            checkpoint_path = model_path

        self.__checkpoint_path = checkpoint_path
        self.logger.info(f'Model path is:  {checkpoint_path}')
        if not all([os.path.exists(checkpoint_path + x) for x in ['.data-00000-of-00001', '.index', '.meta']]):
            self.logger.error('ERROR: could not load model')
            raise FileNotFoundError

        vocabulary_path = checkpoint_path + '.json'
        if not os.path.exists(vocabulary_path):
            vocabulary_path = os.path.join(os.path.dirname(checkpoint_path), 'vocab.json')
        if not os.path.exists(vocabulary_path):
            self.logger.error(f'ERROR: could not load vocabulary. Was trying from {vocabulary_path}')
            raise FileNotFoundError

        # Vocab is a storage for some additional NN metadata
        with open(vocabulary_path, 'r') as fp:
            self.__vocab = json.load(fp)

    @staticmethod
    def __convert_file(input_file_path, output_file_path):
        subprocess.call(['sox',
                         input_file_path,
                         output_file_path])
        assert os.path.isfile(output_file_path)

    def __audio_from_file(self, path, sr=None):
        self.logger.debug(f'Try extract data from file: path={path}')
        if '.wav' not in path:
            in_file_name = os.path.basename(path).replace('.pckl', '')
            in_file_dir = path.replace(in_file_name, '')
            spl_name = in_file_name.split('.')
            ext = spl_name[len(spl_name)-1]
            out_file_name = in_file_name.replace(f'.{ext}', '.wav')
            out_file_path = os.path.join(in_file_dir, out_file_name)
            self.logger.debug(f'Convert "{path}" to {out_file_path}')
            self.__convert_file(path, out_file_path)
            os.remove(path)
            path = out_file_path
        return lr.load(path, sr=sr, mono=True, offset=0.0, duration=None, dtype=np.float32, res_type='kaiser_best')

    def __audio_to_file(self, path, x, sr):
        lr.output.write_wav(path, x.reshape(-1), sr, norm=False)

    def __audio_to_frames(self, x, n_frame, n_step=None):
        if n_step is None:
            n_step = n_frame

        if len(x.shape) == 1:
            x.shape = (-1,1)

        n_overlap = n_frame - n_step
        n_frames = (x.shape[0] - n_overlap) // n_step
        n_keep = n_frames * n_step + n_overlap

        strides = list(x.strides)
        strides[0] = strides[1] * n_step

        return np.lib.stride_tricks.as_strided(x[0:n_keep,:], (n_frames,n_frame), strides)

    def process(self, file):
        if not os.path.isfile(file):
            self.logger.error(f'Skip: [{file}] not found]')
            raise FileNotFoundError

        n_batch = self.batch_size
        checkpoint_path = self.__checkpoint_path
        vocab = self.__vocab

        graph = tf.Graph()

        labels = None

        with graph.as_default():

            saver = tf.train.import_meta_graph(checkpoint_path + '.meta')

            x = graph.get_tensor_by_name(vocab['x'])
            y = graph.get_tensor_by_name(vocab['y'])
            init = graph.get_operation_by_name(vocab['init'])
            logits = graph.get_tensor_by_name(vocab['logits'])
            ph_n_shuffle = graph.get_tensor_by_name(vocab['n_shuffle'])
            ph_n_repeat = graph.get_tensor_by_name(vocab['n_repeat'])
            ph_n_batch = graph.get_tensor_by_name(vocab['n_batch'])
            sr = vocab['sample_rate']

            with tf.Session() as sess:
                saver.restore(sess, checkpoint_path)
                self.logger.debug('Start processing {}'.format(file))

                sound, _ = self.__audio_from_file(file, sr=sr)
                input = self.__audio_to_frames(sound, x.shape[1])
                labels = np.zeros((input.shape[0],), dtype=np.int32)
                sess.run(init, feed_dict = { x : input, y : labels, ph_n_shuffle : 1, ph_n_repeat : 1, ph_n_batch : n_batch })
                count = 0
                n_total = input.shape[0]
                while True:
                    try:
                        output = sess.run(logits)
                        labels[count:count+output.shape[0]] = np.argmax(output, axis=1)
                        count += output.shape[0]
                        print('{:.2f}%\r'.format(100 * (count/n_total)), end='', flush=True)
                    except tf.errors.OutOfRangeError:
                        break

                # voiced_labels = [x for x in labels if x == 1]
                self.logger.info(f'VAD labels are:')
                self.logger.info(labels)
                # self.logger.debug(f'Total labels len is: {len(labels)}')
                # self.logger.debug(f'Voiced samples is: {len(voiced_labels)}')
                # self.logger.debug(f'Other samples is: {len([x for x in labels if x == 0])}')

                # noise = input[np.argwhere(labels==0),:].reshape(-1,1)
                # speech = input[np.argwhere(labels==1),:].reshape(-1,1)
                # self.__audio_to_file('/home/gpn/vadnet/res/out.speech.wav', speech, sr)
                # self.__audio_to_file('/home/gpn/vadnet/res/out.noise.wav', noise, sr)

                sess.close()

        # Save inference result to pickle file.
        # Don't return results directly, because this is executed in subprocess
        with open('vad_response.pickle', 'wb') as res_file_handle:
            pickle.dump(labels, res_file_handle)