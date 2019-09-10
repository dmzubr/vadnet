from windows_extractor import get_windows_from_annotated_data

import os
import matplotlib.pyplot as plt


def test_windows_extractor_one_trsansaction():
    # get_windows_from_annotated_data(end_timestamps_list, seconds_stamps):
    end_timestamps_list = [600]
    second_timestamps = []
    first_voice_entry_index = 300
    voiced_samples_length = 380
    admission = 1

    for i in range(first_voice_entry_index):
        second_timestamps.append(0)
    for i in range(first_voice_entry_index, first_voice_entry_index + voiced_samples_length):
        second_timestamps.append(1)
    for i in range(voiced_samples_length, voiced_samples_length + 100):
        second_timestamps.append(0)

    windows = get_windows_from_annotated_data(end_timestamps_list, second_timestamps)
    assert windows[0]['StartMilliseconds'] == (first_voice_entry_index-admission) * 1000
    assert windows[0]['EndMilliseconds'] == (first_voice_entry_index + voiced_samples_length + admission) * 1000

def test_windows_extractor_2_overlapped_ransactions():
    # get_windows_from_annotated_data(end_timestamps_list, seconds_stamps):
    end_timestamps_list = [600, 840]
    second_timestamps = []
    first_voice_entry_index = 300
    voiced_samples_length = 380
    admission = 1

    for i in range(first_voice_entry_index):
        second_timestamps.append(0)
    for i in range(first_voice_entry_index, first_voice_entry_index + voiced_samples_length):
        second_timestamps.append(1)
    for i in range(voiced_samples_length, voiced_samples_length + 100):
        second_timestamps.append(0)

    windows = get_windows_from_annotated_data(end_timestamps_list, second_timestamps)
    assert windows[0]['StartMilliseconds'] == (first_voice_entry_index-admission) * 1000
    assert windows[0]['EndMilliseconds'] == (first_voice_entry_index + voiced_samples_length + admission) * 1000


import ast

def print_res():
    #Y = []
    res_dir = '/home/dmzubr/gpn/vadnet/res/'
    with open(os.path.join(res_dir, 'cur_iter_secs') , 'r') as f:
        data_txt = f.read().replace('[', '').replace(']', '')

    # Y = ast.literal_eval(data_txt)
    Y = [int(x) for x in data_txt.split(' ')]
    X = []
    for i in range(len(Y)):
        X.append(i)
    # spl = data_txt.split(' ')
    #
    # for item in spl:
    #     Y.append(int(item))

    plt.figure(figsize=(30, 5), dpi=100)
    plt.plot(X, Y)
    plt.ylabel('Is_Sound')
    image_path = os.path.join(res_dir, 'out.png')
    plt.savefig(image_path)

    # print(Y)


# test_windows_extractor_one_trsansaction()
# test_windows_extractor_2_overlapped_ransactions()
print_res()
