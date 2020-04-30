import collections
import contextlib
import sys
import wave
import re
import os

from pydub import AudioSegment
import webrtcvad


def read_wave(path):
    """Reads a .wav file.
    Takes the path, and returns (PCM audio data, sample rate).
    """
    with contextlib.closing(wave.open(path, 'rb')) as wf:
        num_channels = wf.getnchannels()
        assert num_channels == 1
        sample_width = wf.getsampwidth()
        assert sample_width == 2
        sample_rate = wf.getframerate()
        assert sample_rate in (8000, 16000, 32000, 48000)
        pcm_data = wf.readframes(wf.getnframes())
        return pcm_data, sample_rate


def write_wave(path, audio, sample_rate):
    """Writes a .wav file.
    Takes path, PCM audio data, and sample rate.
    """
    with contextlib.closing(wave.open(path, 'wb')) as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio)


class Frame(object):
    """Represents a "frame" of audio data."""
    def __init__(self, bytes, timestamp, duration):
        self.bytes = bytes
        self.timestamp = timestamp
        self.duration = duration


def frame_generator(frame_duration_ms, audio, sample_rate):
    """Generates audio frames from PCM audio data.
    Takes the desired frame duration in milliseconds, the PCM data, and
    the sample rate.
    Yields Frames of the requested duration.
    """
    n = int(sample_rate * (frame_duration_ms / 1000.0) * 2)
    offset = 0
    timestamp = 0.0
    duration = (float(n) / sample_rate) / 2.0
    while offset + n < len(audio):
        yield Frame(audio[offset:offset + n], timestamp, duration)
        timestamp += duration
        offset += n


def vad_collector(sample_rate, frame_duration_ms,
                  padding_duration_ms, vad, frames, share_voiced_samples_in_ring_buffer):
    """Filters out non-voiced audio frames.
    Given a webrtcvad.Vad and a source of audio frames, yields only
    the voiced audio.
    Uses a padded, sliding window algorithm over the audio frames.
    When more than 90% of the frames in the window are voiced (as
    reported by the VAD), the collector triggers and begins yielding
    audio frames. Then the collector waits until 90% of the frames in
    the window are unvoiced to detrigger.
    The window is padded at the front and back to provide a small
    amount of silence or the beginnings/endings of speech around the
    voiced frames.
    Arguments:
    sample_rate - The audio sample rate, in Hz.
    frame_duration_ms - The frame duration in milliseconds.
    padding_duration_ms - The amount to pad the window, in milliseconds.
    vad - An instance of webrtcvad.Vad.
    frames - a source of audio frames (sequence or generator).
    Returns: A generator that yields PCM audio data.
    """
    num_padding_frames = int(padding_duration_ms / frame_duration_ms)
    # We use a deque for our sliding window/ring buffer.
    ring_buffer = collections.deque(maxlen=num_padding_frames)
    # We have two states: TRIGGERED and NOTTRIGGERED. We start in the
    # NOTTRIGGERED state.
    triggered = False

    voiced_frames = []
    for frame in frames:
        is_speech = vad.is_speech(frame.bytes, sample_rate)

        # sys.stdout.write('1' if is_speech else '0')
        if not triggered:
            ring_buffer.append((frame, is_speech))
            num_voiced = len([f for f, speech in ring_buffer if speech])
            # If we're NOTTRIGGERED and more than 90% of the frames in
            # the ring buffer are voiced frames, then enter the
            # TRIGGERED state.
            if num_voiced > share_voiced_samples_in_ring_buffer * ring_buffer.maxlen:
                triggered = True
                sys.stdout.write('%s' % round(float(ring_buffer[0][0].timestamp,), 2))
                # We want to yield all the audio we see from now until
                # we are NOTTRIGGERED, but we have to start with the
                # audio that's already in the ring buffer.
                for f, s in ring_buffer:
                    voiced_frames.append(f)
                ring_buffer.clear()
        else:
            # We're in the TRIGGERED state, so collect the audio data
            # and add it to the ring buffer.
            voiced_frames.append(frame)
            ring_buffer.append((frame, is_speech))
            num_unvoiced = len([f for f, speech in ring_buffer if not speech])
            # If more than 90% of the frames in the ring buffer are
            # unvoiced, then enter NOTTRIGGERED and yield whatever
            # audio we've collected.
            if num_unvoiced > share_voiced_samples_in_ring_buffer * ring_buffer.maxlen:
                sys.stdout.write(' - %s' % round(float(frame.timestamp + frame.duration), 2))
                triggered = False
                yield b''.join([f.bytes for f in voiced_frames])
                ring_buffer.clear()
                voiced_frames = []
    if triggered:
        sys.stdout.write(' - %s' % round(float(frame.timestamp + frame.duration), 2))
    sys.stdout.write('\n')
    # If we have any leftover voiced audio when we run out of input,
    # yield it.
    if voiced_frames:
        yield b''.join([f.bytes for f in voiced_frames])


def audio_preparation(audio_file: str):
    """
    Create new file (if not wav), delete .mp3 and setting format, frame rate, channels parameters, sample width
    """
    wav = AudioSegment.from_file(audio_file)
    wav = wav.set_frame_rate(16000)
    wav = wav.set_channels(1)
    wav = wav.set_sample_width(2)
    wav.export(re.sub(r'\.(mp3|wav)', '.wav', audio_file), format='wav')
    if '.mp3' in audio_file:
        os.remove(audio_file)

    return os.path.realpath(re.sub(r'\.(mp3|wav)', '.wav', audio_file))


def conversion_str_to_float(in_list: list, out_list: list):
    """
    Convert list with str timestamp to list with float timestamp
    """
    for i in range(len(in_list)):
        timestamp_str = re.findall(r'\d+.\d+', in_list[i])
        result = [float(item) for item in timestamp_str]
        out_list.append(result)

    return out_list


def has_overlap(A_start, A_end, B_start, B_end):

    latest_start = max(A_start, B_start)
    earliest_end = min(A_end, B_end)

    return latest_start <= earliest_end


def filter_timestamp_vad(manually: list, vad_heap: list, vad: list):
    """
    Filters vad timestamps intersecting with manual timestamps.
    """
    for i in range(len(manually)):
        for j in range(len(vad_heap)):
            if has_overlap(manually[i][0], manually[i][1], vad_heap[j][0], vad_heap[j][1]):
                if manually[i][1] < vad_heap[j][1] or manually[i][0] > vad_heap[j][0]:
                    vad.append([max(vad_heap[j][0], manually[i][0]), min(manually[i][1], vad_heap[j][1])])

    return vad


def share_of_coincidence_vad(manually: list, vad: list):
    """
    Calculates the share of coincidence of the total time vad to manual time.
    """
    manually_sum_time = 0
    vad_sum_time = 0

    for i in range(len(manually)):
        manually_sum_time += (manually[i][1] - manually[i][0])
    for i in range(len(vad)):
        vad_sum_time += (vad[i][1] - vad[i][0])

    share = vad_sum_time / manually_sum_time

    return share


def main(args):
    if len(args) != 2:
        sys.stderr.write(
            'Usage: example.py <aggressiveness> <path to wav file>\n')
        sys.exit(1)
    audio, sample_rate = read_wave(args[1])
    vad = webrtcvad.Vad(int(args[0]))
    frames = frame_generator(30, audio, sample_rate)
    frames = list(frames)
    segments = vad_collector(sample_rate, 30, 300, vad, frames, 0.9)
    for i, segment in enumerate(segments):
        # path = 'chunk-%002d.wav' % (i,)
        print()
        # write_wave(path, segment, sample_rate)


if __name__ == '__main__':
    main([3, 'speaker_c.wav'])
    # with open('resemble_test/manually_1', 'r') as inf_m_1, open('resemble_test/vad_1', 'r') as inf_v_1, \
    #         open('resemble_test/manually_2', 'r') as inf_m_2, open('resemble_test/vad_2', 'r') as inf_v_2:
    #     manually_inf_1 = [row.strip() for row in inf_m_1]
    #     vad_inf_1 = [row.strip() for row in inf_v_1]
    #     manually_inf_2 = [row.strip() for row in inf_m_2]
    #     vad_inf_2 = [row.strip() for row in inf_v_2]
    #
    # manually_1 = []
    # vad_1_heap = []
    # vad_1 = []
    # manually_2 = []
    # vad_2_heap = []
    # vad_2 = []
    #
    # conversion_str_to_float(manually_inf_1, manually_1)
    # conversion_str_to_float(vad_inf_1, vad_1_heap)
    # conversion_str_to_float(manually_inf_2, manually_2)
    # conversion_str_to_float(vad_inf_2, vad_2_heap)
    #
    # filter_timestamp_vad(manually_1, vad_1_heap, vad_1)
    # filter_timestamp_vad(manually_2, vad_2_heap, vad_2)
    #
    # sorted_prices = sorted([share_of_coincidence_vad(manually_1, vad_1), share_of_coincidence_vad(manually_2, vad_2)])
    # print(sum(sorted_prices) / len(sorted_prices))
