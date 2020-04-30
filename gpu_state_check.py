from subprocess import Popen, PIPE


def is_gpu_busy():
    gpu_check_cmd = 'nvidia-smi'
    process = Popen([gpu_check_cmd], stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    stdout_str = stderr.decode("utf-8")
    return is_gpu_busy_by_smi_output(stdout_str)


def is_gpu_busy_by_smi_output(smi_output: str):
    res = False

    process_line_marker = "MiB"
    compute_process_marker = " C "
    for line in smi_output.split('\n'):
        count_of_marker_entries = line.count(process_line_marker)
        if count_of_marker_entries == 1:
            if compute_process_marker in line:
                res = True
    return res
