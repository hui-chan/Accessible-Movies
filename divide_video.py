import csv
import math  # 用于 ceil
import os
import subprocess
import sys
from pathlib import Path


def get_video_duration(video_path):
    """使用 ffprobe 获取视频时长 (秒)"""
    command = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        duration = float(result.stdout.strip())
        return duration
    except FileNotFoundError:
        print(f"错误：找不到 'ffprobe' 命令。请确保 ffmpeg 已安装并在系统 PATH 中。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"错误：ffprobe 获取视频 '{video_path}' 时长失败。")
        print(f"命令: {' '.join(command)}")
        print(f"错误信息: {e.stderr}")
        sys.exit(1)
    except ValueError:
        print(f"错误：无法将 ffprobe 的输出解析为时长。")
        sys.exit(1)

def split_video_by_thresholds(vad_file_path, video_file_path, output_dir, threshold_step=600):
    """
    根据 CSV 文件中的时间戳阈值分割视频，并返回分割点时间戳列表。

    Args:
        vad_file_path (str): VAD CSV 文件的路径。
        video_file_path (str): 原始视频文件的路径。
        output_dir (str): 分割后视频片段的输出目录。
        threshold_step (int): 时间阈值的步长 (例如 600 秒)。

    Returns:
        list or None: 成功时返回分割点时间戳列表 [0.0, time1, time2, ..., video_duration]，
                      失败时返回 None。
    """
    if not os.path.exists(video_file_path):
        print(f"错误：视频文件未找到: {video_file_path}")
        return None

    if not os.path.exists(vad_file_path):
        print(f"错误：CSV 文件未找到: {vad_file_path}")
        return None

    # 创建输出目录 (如果不存在)
    os.makedirs(output_dir, exist_ok=True)

    segment_timestamps = [0.0] # 初始化分割时间戳列表，包含起始点 0
    video_duration = 0.0

    # 获取视频总时长
    try:
        video_duration = get_video_duration(video_file_path)
        print(f"视频总时长: {video_duration:.2f} 秒")
    except SystemExit:
        return None

    current_threshold = threshold_step
    start_time = 0.0
    segment_index = 1
    found_split_point = False # 标记是否至少找到一个分割点

    print(f"开始处理 VAD CSV 文件: {vad_file_path} 以分割视频")
    try:
        with open(vad_file_path, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            #header = next(reader, None) # 跳过表头
            # print(f"CSV 表头 (已跳过): {header}" if header else "CSV 文件无表头") # Optional debug print

            for i, row in enumerate(reader):
                if len(row) < 2:
                    # print(f"警告：VAD CSV 第 {i+2} 行数据列数不足，跳过。行内容: {row}") # Optional debug print
                    continue

                try:
                    timestamp = float(row[1]) # 对白结束时间戳在第二列
                except (ValueError, IndexError):
                    # print(f"警告：VAD CSV 第 {i+2} 行的第二列无法解析为数字，跳过。行内容: {row}") # Optional debug print
                    continue

                # 检查是否达到或超过当前寻找的阈值
                if timestamp >= current_threshold:
                    end_time = timestamp
                    output_filename = f"segment_{segment_index}.mp4"
                    output_filepath = os.path.join(output_dir, output_filename)
                    print(f"找到阈值点: {timestamp:.2f} (>= {current_threshold})。切割视频片段 {segment_index}: [{start_time:.2f}s - {end_time:.2f}s]")

                    command = [
                        'ffmpeg', '-y', # Overwrite output files without asking
                        '-i', video_file_path,
                        '-ss', str(start_time),
                        '-to', str(end_time),
                        '-vf', 'scale=-2:360',
                        '-r', '1',
                        '-c:v', 'libx264',
                        '-crf','28',
                        '-c:a', 'libopus',
                        '-ac','1',
                        '-b:a', '1k',
                        output_filepath
                    ]
                    try:
                        # print(f"执行命令: {' '.join(command)}") # Optional debug print
                        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        print(f"视频片段已保存到: {output_filepath}")

                        segment_timestamps.append(end_time) # 记录分割点
                        found_split_point = True
                        start_time = end_time
                        segment_index += 1
                        current_threshold += threshold_step

                    except FileNotFoundError:
                        print(f"错误：找不到 'ffmpeg' 命令。请确保已安装并在 PATH 中。")
                        return None # 停止处理
                    except subprocess.CalledProcessError as e:
                        print(f"错误：ffmpeg 分割视频失败。")
                        print(f"命令: {' '.join(command)}")
                        print(f"错误信息: {e.stderr.decode()}")
                        print("警告：上一个片段分割失败，将尝试继续处理。")
                        # 即使失败，也记录时间戳并尝试继续
                        segment_timestamps.append(end_time)
                        found_split_point = True
                        start_time = end_time
                        segment_index += 1
                        current_threshold += threshold_step

    except FileNotFoundError:
        print(f"错误：VAD CSV 文件打开失败: {vad_file_path}")
        return None
    except Exception as e:
        print(f"读取 VAD CSV 文件时发生未知错误: {e}")
        return None

    # --- 处理视频尾部 ---
    # 只有在最后一个找到的时间戳 < 视频总长时才需要处理尾部
    if start_time < video_duration :
        print(f"处理最后一个视频片段: [{start_time:.2f}s - {video_duration:.2f}s]")
        output_filename = f"segment_{segment_index}.mp4"
        output_filepath = os.path.join(output_dir, output_filename)

        command = [
            'ffmpeg', '-y', # Overwrite output files without asking
            '-i', video_file_path,
            '-ss', str(start_time),
            '-to', str(video_duration),
            '-vf', 'scale=-2:360',
            '-r', '1',
            '-c:v', 'libx264',
            '-crf','28',
            '-c:a', 'libopus',
            '-ac','1',
            '-b:a', '1k',
            output_filepath
        ]
        try:
            # print(f"执行命令: {' '.join(command)}") # Optional debug print
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"最后一个视频片段已保存到: {output_filepath}")
            # 不需要在这里加 segment_timestamps.append(video_duration)
            # 因为后面的逻辑会自动添加
        except FileNotFoundError:
            print(f"错误：找不到 'ffmpeg' 命令。")
            # 即使尾部失败，我们仍然有之前的时间戳，可能可以继续处理 gap 文件
        except subprocess.CalledProcessError as e:
            print(f"错误：ffmpeg 分割最后一个片段失败。")
            print(f"命令: {' '.join(command)}")
            print(f"错误信息: {e.stderr.decode()}")
            # 同上，可能继续处理 gap 文件

    # --- 最终确定时间戳列表 ---
    # 确保最后一个时间戳是视频总时长
    segment_timestamps.append(video_duration)

    print(f"视频分割处理完成。最终分割时间点 (秒): {segment_timestamps}")
    with open(os.path.join(output_dir, "divide_timastamps.txt"), 'w') as file:
        for item in segment_timestamps:
            file.write(f"{item}\n")
    return segment_timestamps



def split_gap_csv(segment_timestamps, gap_file_path, output_dir):
    """
    遍历gap_file_path的第一列（已按顺序排列），将处于segment_timestamps
    中相邻两个时间戳（含前不含后的区间）的若干行分离出一个新的csv文件,
    这些行的每个时间戳都减去区间左端点，将输出到 output_dir文件夹中，
    文件名segment_1.csv、segment_2.csv等。

    Args:
        segment_timestamps (list): 有序的时间戳列表，用于分割数据。
        gap_file_path (str): 输入的包含按顺序排列的时间戳的CSV文件路径
                             （第一列为时间戳）。
        output_dir (str): 输出CSV文件的目录。
    """
    os.makedirs(output_dir, exist_ok=True)
    segment_count = 1

    with open(gap_file_path, 'r', newline='') as infile:
        reader = csv.reader(infile)

        data_buffer = []
        for row in reader:
            if row:
                try:
                    #timestamp = float(row[0])
                    data_buffer.append([float(row[0]),float(row[1])])
                except ValueError:
                    print(f"警告: 在文件 {gap_file_path} 中发现无法转换为浮点数的时间戳: {row[0]}")

        data_index = 0
        for i in range(len(segment_timestamps) - 1):
            start_time = segment_timestamps[i]
            end_time = segment_timestamps[i+1]

            output_file_path = os.path.join(output_dir, f'segment_{segment_count}.csv')
            segment_count += 1

            with open(output_file_path, 'w', newline='') as outfile:
                writer = csv.writer(outfile)

                while data_index < len(data_buffer):
                    timestamp=data_buffer[data_index][0]
                    duration=data_buffer[data_index][1]
                    if start_time-0.00001 <= timestamp < end_time-0.00001:
                        processed_row = [round(timestamp-start_time , 1) ,duration]
                        writer.writerow(processed_row)
                        data_index += 1
                    else:
                        break  # 由于输入文件已排序，超出当前区间即可停止内部循环
                    


# --- 主程序部分 ---
if __name__ == "__main__":
    # --- 请修改以下路径和参数 ---
    vad_csv_file = 'path/to/your/vad_results.csv'  # VAD CSV 文件路径
    video_file = 'path/to/your/video.mp4'        # 原始视频文件路径
    gap_csv_file = 'path/to/your/sorted_gaps.csv' # <--- 确保这个文件按时间排序！
    video_output_folder = 'output_video_segments' # 输出分割后视频的文件夹
    gap_output_folder = 'output_gap_segments'   # 输出分割后静默 CSV 的文件夹
    time_threshold_step = 600                     # VAD 时间阈值步长 (秒)
    gap_start_time_column_index = 0
    gap_duration_column_index = 1
    # --- 执行 ---
    print("--- 开始视频分割 ---")
    # 假设 split_video_by_thresholds 函数已经更新或存在，并返回时间戳列表
    # from previous_script import split_video_by_thresholds # 或者直接包含在这里
    segment_timestamps = split_video_by_thresholds(
        vad_csv_file,
        video_file,
        video_output_folder,
        time_threshold_step
    )

    if segment_timestamps:
        print("\n--- 开始处理静默 CSV 文件 (优化流式处理) ---")
        # 使用优化后的函数
        split_gap_csv(
            segment_timestamps,
            gap_csv_file,
            gap_output_folder
        )
    else:
        print("\n视频分割失败或未产生有效时间戳，跳过静默 CSV 文件处理。")

    print("\n--- 全部处理完成 ---")