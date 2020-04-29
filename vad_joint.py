from webrtc_vad_result_handler import Handler


class VadJoint:
    def __init__(self):
        pass

    def conversion_vad_nn_result(self, timestamps_boolean: list):
        time_timestamps = []
        for i in range(len(timestamps_boolean)):
            if timestamps_boolean[i] == 1 and timestamps_boolean[i - 1] == 1 and i != 0:
                time_timestamps.append([i - 1, i])
            elif timestamps_boolean[i] == 1:
                time_timestamps.append([i, i + 1])

        return time_timestamps

    def vad_joint(self, timestamps_nn: list, timestamps_webrtc: list):
        result_joint = []
        func_handler = Handler()

        for i, j in zip(timestamps_nn, timestamps_webrtc):
            result_joint.append(i)
            result_joint.append(j)
        result_joint.sort()

        return func_handler.glue_borders(result_joint, 0)


if __name__ == '__main__':
    vad_joint = VadJoint()
    handler = Handler()

    boolean_timestamps = [0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1]
    timestamps_webrtc = [[0.0, 6.15], [9.35, 11.77], [14.12, 16.66], [18.05, 19.15], [21.48, 23.89], [26.15, 29.00]]

    timestamps_nn = handler.glue_borders(vad_joint.conversion_vad_nn_result(boolean_timestamps), 0)

    print(vad_joint.vad_joint(timestamps_nn, timestamps_webrtc))
