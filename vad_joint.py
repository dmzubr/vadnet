class VadJoint:
    """
    Combines the VAD results of webrtc and neural network
    """
    def __init__(self):
        pass

    def convert_vad_nn_bool_result(self, timestamps_boolean: list):
        """
        Converts the VAD result of neural network to the form of the result webrtc VAD
        """
        time_timestamps = []
        cur_segm = []
        for i in range(len(timestamps_boolean)):
            if timestamps_boolean[i]:
                if len(cur_segm) == 0:
                    cur_segm.append(i)
            else:
                if len(cur_segm) > 0:
                    cur_segm.append(i)
                    time_timestamps.append(cur_segm)
                    cur_segm = []

        # If last bool el will be equal to zero - then need to finish last segment
        if len(cur_segm) > 0:
            cur_segm.append(len(timestamps_boolean))
            time_timestamps.append(cur_segm)

        return time_timestamps

    def join_stamp_windows_list(self, timestamps_nn: list, timestamps_webrtc: list):
        """
        Combines VAD results of webrtc and neural network on the principle of full outer join
        """
        trg_list = []
        # Create a replica of initial arrays content due to keep initial arrays immutable
        for nn_timestamp in timestamps_nn:
            # Add values explicitly to keep values in initial arrays immutable
            trg_list.append([nn_timestamp[0], nn_timestamp[1]])
        for webrtc_timestamp in timestamps_webrtc:
            trg_list.append([webrtc_timestamp[0], webrtc_timestamp[1]])

        trg_list = sorted(trg_list, key=lambda item: item[0])
        i = 0
        while i < len(trg_list):
            j = i + 1
            if j < len(trg_list):
                while j < len(trg_list) and trg_list[j][0] < trg_list[i][1]:
                    # Can be a situation when right edge of right window is even less than right edge of left window
                    # So - add this additional check
                    if trg_list[i][1] < trg_list[j][1]:
                        trg_list[i][1] = trg_list[j][1]
                    del trg_list[j]
                    continue
            i += 1

        return trg_list


if __name__ == '__main__':
    vad_joint = VadJoint()

    boolean_timestamps = [True, True]
    converted_nn_results = vad_joint.convert_vad_nn_bool_result(boolean_timestamps)
    ref_convert_res = [[0,2]]
    assert converted_nn_results == ref_convert_res

    boolean_timestamps = [False, True, True, False]
    converted_nn_results = vad_joint.convert_vad_nn_bool_result(boolean_timestamps)
    ref_convert_res = [[1, 3]]
    assert converted_nn_results == ref_convert_res

    boolean_timestamps = [False, True, True, False, True, True, False, True]
    converted_nn_results = vad_joint.convert_vad_nn_bool_result(boolean_timestamps)
    ref_convert_res = [[1, 3], [4, 6], [7, 8]]
    assert converted_nn_results == ref_convert_res


    # Test that will no throw an exception in case of real data
    nn_segments = [[12, 13], [27, 37], [41, 45], [62, 66], [79, 81], [86, 87], [91, 96], [97, 110], [111, 112],
                   [115,116], [118, 119],      [130, 131], [132, 135], [162, 165], [168, 169], [172, 173], [174, 180],
                   [181, 183], [185, 186], [187, 188],      [189, 190], [194, 195],
                   [198, 204], [209, 210], [211, 213], [214, 218], [222, 223], [225, 226], [231, 234], [235, 239]]

    webrtc_segments = [[0.4300000000000006, 4.849999999999992], [10.929999999999948, 13.489999999999915],
                       [29.050000000000363, 37.880000000000656], [41.20000000000082, 45.89000000000096],
                       [62.23000000000162, 67.04000000000175], [68.17000000000183, 70.13000000000187],
                       [78.49000000000223, 81.68000000000231], [85.45000000000249, 88.34000000000256],
                       [90.40000000000268, 113.75000000000352], [130.6300000000042, 135.92000000000436],
                       [160.99000000000535, 186.35000000000628], [187.75000000000637, 190.91000000000645],
                       [193.6600000000066, 196.58000000000666], [198.73000000000678, 208.76000000000712],
                        [211.75000000000728, 222.71000000000765], [229.15000000000794, 239.98897916666667]]
    joined_windows = vad_joint.join_stamp_windows_list(nn_segments, webrtc_segments)

    timestamps_webrtc = [[0.0, 6.15], [9.35, 11.77], [14.12, 16.66], [18.05, 19.15], [21.48, 23.89], [26.15, 29.00]]
    joined_windows = vad_joint.join_stamp_windows_list(converted_nn_results, timestamps_webrtc)
    print(f"NN    : {converted_nn_results}")
    print(f"WebRtc: {timestamps_webrtc}")
    print(f"Joined: {joined_windows}")
