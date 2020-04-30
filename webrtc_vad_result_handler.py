class Handler:
    """
    Webrtc VAD result handler.
    """
    def __init__(self):
        pass

    def lap(self, timestamps: list, lap_value):
        """
        Extends the timestamps values to the lap_value
        """
        for i in range(len(timestamps)):
            if timestamps[i][0] - lap_value < 0:
                timestamps[i][0] = 0
            else:
                timestamps[i][0] -= lap_value

            if timestamps[i][1] + lap_value > timestamps[-1][1]:
                timestamps[i][1] = timestamps[-1][1]
            else:
                timestamps[i][1] += lap_value

            timestamps[i][0] = float("{0:.2f}".format(timestamps[i][0]))
            timestamps[i][1] = float("{0:.2f}".format(timestamps[i][1]))

        return timestamps

    def glue_borders(self, timestamps: list, unvoiced_value):
        """
        Combines overlapping timestamps and those that fall under the condition:
        left border interval right - right border interval left < unvoiced_value.
        """
        if len(timestamps) > 1:
            for x in range(1, len(timestamps)):
                if 0 <= x < len(timestamps):
                    try:
                        while timestamps[x][0] <= timestamps[x - 1][1] or timestamps[x][0] - timestamps[x - 1][1] <= unvoiced_value:
                            if timestamps[x][0] <= timestamps[x - 1][1]:
                                timestamps[x][0] = timestamps[x - 1][0]
                                timestamps[x][1] = max(timestamps[x][1], timestamps[x - 1][1])
                                del timestamps[x - 1]
                            elif timestamps[x][0] - timestamps[x - 1][1] <= unvoiced_value:
                                timestamps[x][0] = timestamps[x - 1][0]
                                timestamps[x][1] = max(timestamps[x][1], timestamps[x - 1][1])
                                del timestamps[x - 1]
                    except IndexError:
                        self.glue_borders(timestamps, unvoiced_value)
        else:
            print('Timestamps len must be > 1')

        return timestamps


reference_1 = [[0.0, 3.56], [2.56, 4.61], [3.76, 6.83], [7.65, 8.83], [14.76, 16.33]]  # lap_value = 0.5
reference_2 = [[0.0, 5.56], [0.56, 6.61], [1.76, 8.83], [5.65, 10.83], [12.76, 16.33]]  # lap_value = 2.5

reference_3 = [[0.0, 6.83], [7.65, 8.83], [14.76, 16.33]]  # lap_value = 0.5, unvoiced_value = 0
reference_4 = [[0.0, 9.33], [14.26, 16.33]]  # lap_value = 1, unvoiced_value = 0

reference_5 = [[0.36, 6.33], [8.15, 8.33], [15.26, 16.33]]  # lap_value = 0, unvoiced_value = 0.5
reference_6 = [[0.36, 8.33], [15.26, 16.33]]  # lap_value = 0, unvoiced_value = 2

if __name__ == '__main__':
    handler = Handler()

    timestamps_in = [[0.36, 3.06], [3.06, 4.11], [4.26, 6.33], [8.15, 8.33], [15.26, 16.33]]
    assert reference_1 == handler.lap(timestamps_in, 0.5)
    timestamps_in = [[0.36, 3.06], [3.06, 4.11], [4.26, 6.33], [8.15, 8.33], [15.26, 16.33]]
    assert reference_2 == handler.lap(timestamps_in, 2.5)

    timestamps_in = [[0.36, 3.06], [3.06, 4.11], [4.26, 6.33], [8.15, 8.33], [15.26, 16.33]]
    assert reference_3 == handler.glue_borders(handler.lap(timestamps_in, 0.5), 0)
    timestamps_in = [[0.36, 3.06], [3.06, 4.11], [4.26, 6.33], [8.15, 8.33], [15.26, 16.33]]
    assert reference_4 == handler.glue_borders(handler.lap(timestamps_in, 1), 2)

    timestamps_in = [[0.36, 3.06], [3.06, 4.11], [4.26, 6.33], [8.15, 8.33], [15.26, 16.33]]
    assert reference_5 == handler.glue_borders(handler.lap(timestamps_in, 0), 0.5)
    timestamps_in = [[0.36, 3.06], [3.06, 4.11], [4.26, 6.33], [8.15, 8.33], [15.26, 16.33]]
    assert reference_6 == handler.glue_borders(handler.lap(timestamps_in, 0), 2)
