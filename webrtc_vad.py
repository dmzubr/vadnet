import collections
import contextlib
import wave
import os

from pydub import AudioSegment
import webrtcvad


class Frame(object):
    """Represents a "frame" of audio data."""

    def __init__(self, bytes, timestamp, duration):
        self.bytes = bytes
        self.timestamp = timestamp
        self.duration = duration


class WebrtcvadWrapper:
    def __init__(self, share_voiced_samples_in_ring_buffer: float, frame_duration_ms,
                 padding_duration_ms, aggressiveness):
        self.__share_voiced_samples_in_ring_buffer = share_voiced_samples_in_ring_buffer
        self.__frame_duration_ms = frame_duration_ms
        self.__padding_duration_ms = padding_duration_ms
        self.__aggressiveness = aggressiveness

    @staticmethod
    def __get_vad_available_sample_rates():
        return [8000, 16000, 32000, 48000]

    def read_wave(self, path):
        """Reads a .wav file.
        Takes the path, and returns (PCM audio data, sample rate).
        """
        with contextlib.closing(wave.open(path, 'rb')) as wf:
            num_channels = wf.getnchannels()
            assert num_channels == 1
            sample_width = wf.getsampwidth()
            assert sample_width == 2
            sample_rate = wf.getframerate()
            assert sample_rate in self.__get_vad_available_sample_rates()
            pcm_data = wf.readframes(wf.getnframes())
            return pcm_data, sample_rate

    def frame_generator(self, audio, sample_rate):
        """Generates audio frames from PCM audio data.
        Takes the desired frame duration in milliseconds, the PCM data, and
        the sample rate.
        Yields Frames of the requested duration.
        """
        n = int(sample_rate * (self.__frame_duration_ms / 1000.0) * 2)
        offset = 0
        timestamp = 0.0
        duration = (float(n) / sample_rate) / 2.0
        while offset + n < len(audio):
            yield Frame(audio[offset:offset + n], timestamp, duration)
            timestamp += duration
            offset += n

    def vad_collector(self, sample_rate, vad, frames):
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
        num_padding_frames = int(self.__padding_duration_ms / self.__frame_duration_ms)
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
                if num_voiced > self.__share_voiced_samples_in_ring_buffer * ring_buffer.maxlen:
                    triggered = True
                    # sys.stdout.write('%s' % round(float(ring_buffer[0][0].timestamp, ), 2))
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
                if num_unvoiced > self.__share_voiced_samples_in_ring_buffer * ring_buffer.maxlen:
                    triggered = False
                    pure_stamps = [f.timestamp for f in voiced_frames]
                    yield [pure_stamps[0], pure_stamps[-1] + frame.duration]

                    ring_buffer.clear()
                    voiced_frames = []
        # If we have any leftover voiced audio when we run out of input,
        # yield it.
        if voiced_frames:
            pure_stamps = [f.timestamp for f in voiced_frames]
            yield [pure_stamps[0], pure_stamps[-1] + frame.duration]

    def prepare_audio(self, audio_file_path: str):
        """
        Create new file (if not wav), delete .mp3 and setting format, frame rate, channels parameters, sample width
        """
        in_file_name = audio_file_path.replace('\\', '/').split('/')[-1]
        in_file_ext = in_file_name.split('.')[-1]
        target_audio_path = audio_file_path
        audio_obj = AudioSegment.from_file(audio_file_path)
        need_export = False

        if in_file_ext != 'wav':
            need_export = True
        if audio_obj.frame_rate not in self.__get_vad_available_sample_rates():
            # Set maximal available sample rate to avoid lost of quality
            # In most cases in audio will be in 44100
            audio_obj = audio_obj.set_frame_rate(self.__get_vad_available_sample_rates()[-1])
            need_export = True

        if need_export:
            target_audio_path = audio_file_path.replace(in_file_name, in_file_name.replace(in_file_ext, 'wav'))
            audio_obj.export(target_audio_path, format='wav')
            audio_file_path = target_audio_path

        return target_audio_path

    def get_vad_segments(self, audio_file_path: str):
        assert os.path.isfile(audio_file_path)
        prepared_file_path = self.prepare_audio(audio_file_path)
        audio, sample_rate = self.read_wave(prepared_file_path)

        vad = webrtcvad.Vad(self.__aggressiveness)
        frames = self.frame_generator(audio, sample_rate)
        frames = list(frames)
        segments = self.vad_collector(sample_rate, vad, frames)
        return list(segments)


class VadSegmentsAdjuster:
    def __init__(self):
        pass

    def get_adjusted_segments(self, initial_vad_segments, audio_dur_seconds, admissions=0.5, min_unvoiced_dur=1):
        segments = initial_vad_segments
        for segment in segments:
            segment[0] -= admissions
            if segment[0] < 0:
                segment[0] = 0
            segment[1] += admissions
            if segment[1] > audio_dur_seconds:
                segment[1] = audio_dur_seconds

        i = 0
        while i < len(segments):
            j = i+1
            if j < len(segments):
                diff = segments[j][0] - segments[i][1]
                if diff < min_unvoiced_dur:
                    segments[i][1] = segments[j][1]
                    del segments[j]
                    continue
            i += 1

        return segments


if __name__ == '__main__':
    var_adjuster = VadSegmentsAdjuster()
    initial_vad_segments = [[0.36, 2.10], [3.06, 4.11], [4.26, 5.33], [8.15, 8.33], [15.26, 16.33]]
    changed_segments = var_adjuster.get_adjusted_segments(initial_vad_segments, audio_dur_seconds=16.5)
    ref_res = [[0, 5.83], [7.65, 8.83], [14.76, 16.5]]
    assert changed_segments == ref_res
