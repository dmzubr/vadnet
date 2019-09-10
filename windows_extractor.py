import logging
import collections


def get_windows_from_annotated_data(end_timestamps_list, seconds_stamps):

    def get_current_required_voiced_samples_percent(current_shift_val):
        diff = left_shift_seconds - minimal_transaction_left_part_seconds
        percent_for_one_frame = (percent_voiced_frames_in_window_max - percent_voiced_frames_in_window_min) / diff

        # Increasing when get closer to transaction time
        # res = percent_voiced_frames_in_window_min + (current_shift_val * percent_for_one_frame)

        # Decreasing when get closer to transaction time
        res = percent_voiced_frames_in_window_min + ((diff - current_shift_val) * percent_for_one_frame)
        return res

    target_windows = []
    minimal_transaction_left_part_seconds = 30
    minimal_transaction_right_part_seconds = 20
    left_shift_seconds = 300
    right_shift_seconds = 100

    # Quantity of frames that have to labeled as voiced to decode voice trigger
    # Required percent of voiced samples depends on distance from time of receipt
    # The more distant current window position is - tho lower is required voiced samples percentage
    percent_voiced_frames_in_window_max = 60
    percent_voiced_frames_in_window_min = 30
    calc_window_length = 15

    for end_timestamp in end_timestamps_list:
        transaction_timestamp_index = int(end_timestamp)
        transaction_minimal_left_index = transaction_timestamp_index - minimal_transaction_left_part_seconds
        transaction_minimal_right_index = transaction_timestamp_index + minimal_transaction_right_part_seconds

        overlapped_transactions = [x for x in end_timestamps_list if
                                   x < end_timestamp and x > end_timestamp - left_shift_seconds]

        if len(overlapped_transactions) > 0:
            left_edge_frame_index = int(overlapped_transactions[0] + minimal_transaction_right_part_seconds)
            logging.debug(
                f'There is a transaction in left padding of current transaction. So move left to {left_shift_seconds}s')
        else:
            # Go left from time of transaction end
            left_edge_frame_index = transaction_timestamp_index - left_shift_seconds

        if left_edge_frame_index < 0:
            left_edge_frame_index = 0

        change_from_initial_left_shift = 0

        window_buf = collections.deque(maxlen=calc_window_length)
        while calc_window_length < transaction_minimal_left_index:
            window_buf.append(seconds_stamps[left_edge_frame_index])
            if len(window_buf) >= calc_window_length:
                voiced_samples = [x for x in window_buf if x == 1]
                voiced_samples_percent = len(voiced_samples) / len(window_buf) * 100
                required_percent_voiced_frames_in_window = get_current_required_voiced_samples_percent(
                    change_from_initial_left_shift)
                # print(f'required_percent_voiced_frames_in_window is {required_percent_voiced_frames_in_window}')
                if voiced_samples_percent >= required_percent_voiced_frames_in_window:
                    # Return cursor to the start of padding window
                    left_edge_frame_index -= int(calc_window_length/2)
                    break
            left_edge_frame_index += 1
            change_from_initial_left_shift += 1

        # Go right from time of transaction end
        overlapped_transactions = [x for x in end_timestamps_list if
                                   x > end_timestamp and x < end_timestamp + right_shift_seconds]

        if len(overlapped_transactions) > 0:
            right_shift_seconds = int(overlapped_transactions[0] - minimal_transaction_left_part_seconds)
            logging.debug(
                f'There is a transaction in right padding of current transaction. So move right to {right_shift_seconds}s')

        right_edge_frame_index = transaction_timestamp_index + right_shift_seconds
        if right_edge_frame_index >= len(seconds_stamps):
            right_edge_frame_index = len(seconds_stamps) - 1

        window_buf.clear()
        while seconds_stamps[right_edge_frame_index] == 0 and right_edge_frame_index > transaction_minimal_right_index:
            window_buf.append(seconds_stamps[right_edge_frame_index])
            if len(window_buf) >= calc_window_length:
                voiced_samples = [x for x in window_buf if x == 1]
                voiced_samples_percent = len(voiced_samples) / len(window_buf) * 100
                if voiced_samples_percent >= percent_voiced_frames_in_window_max:
                    right_edge_frame_index += int(calc_window_length/2)
                    break
            right_edge_frame_index -= 1

        # Make admissions
        if left_edge_frame_index > 0:
            left_edge_frame_index -= 1
        if right_edge_frame_index < len(seconds_stamps):
            right_edge_frame_index += 2

        window = {
            'StartMilliseconds': int((left_edge_frame_index) * 1000),
            'EndMilliseconds': int(right_edge_frame_index * 1000)
        }
        target_windows.append(window)
        logging.info(window)

    logging.info('Resulting windows are')
    logging.info(target_windows)

    return target_windows
