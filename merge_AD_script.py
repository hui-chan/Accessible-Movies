import json
import os
import subprocess

import pandas as pd


def get_video_duration(video_path):
    """Get video duration in seconds using ffprobe."""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        video_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    metadata = json.loads(result.stdout)
    return float(metadata['format']['duration'])

def merge_AD_script(video_seg_dir):
    # 获取所有AD_script.csv文件并按编号排序
    csv_files = sorted(
        [f for f in os.listdir(video_seg_dir) if f.endswith('_AD_script.csv')],
        key=lambda x: int(x.split('_')[1])
    )

    if csv_files:
        first_csv_path = os.path.join(video_seg_dir, csv_files[0])
        header = pd.read_csv(first_csv_path, nrows=0).columns.tolist()
    else:
        raise FileNotFoundError("No _AD_script.csv files found in video_seg directory")
    
    total_duration = 0.0
    all_data = []

    for csv_file in csv_files:
        # 获取对应的视频文件路径
        segment_num = csv_file.split('_')[1]
        video_file = f'segment_{segment_num}.mp4'
        video_path = os.path.join(video_seg_dir, video_file)

        # 获取视频时长
        duration = get_video_duration(video_path)

        # 读取CSV文件
        csv_path = os.path.join(video_seg_dir, csv_file)
        df = pd.read_csv(csv_path)

        # 前两列加上之前视频的总时长
        df.iloc[:, 0] = df.iloc[:, 0] + total_duration

        # 保留一位小数
        df = df.round(1)

        all_data.append(df)
        total_duration += duration

    # 合并所有数据并保存
    output_path=os.path.join(video_seg_dir, 'merged_AD_scripts.csv')
    merged_df = pd.concat(all_data, ignore_index=True)
    merged_df.to_csv(output_path, index=False, header=header)