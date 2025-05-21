import glob  # 用于文件清理
import os
import re  # 用于正则表达式
import subprocess  # 用于调用FFmpeg
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import torch
import numpy as np
import pandas as pd
from pydub import AudioSegment
from pydub.utils import mediainfo
# 初始化支持中文TTS模型
from TTS.api import TTS

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"
# Init TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)


def text_to_speech(text, output_path, max_duration=None, style_wav=None):
    """将文本转换为语音，并确保音频时长不超过max_duration"""
    tts.tts_to_file(
        text=text,
        speaker_wav=style_wav,
        language="zh",
        file_path=output_path
    )

    # 获取生成音频的时长
    ad_audio = AudioSegment.from_wav(output_path)
    ad_duration = len(ad_audio)

    # 如果音频时长超过max_duration，调整速度
    if max_duration is not None and ad_duration > max_duration:
        speed_factor = ad_duration / max_duration
        ad_audio = ad_audio.speedup(playback_speed=speed_factor)
        ad_audio.export(output_path, format="wav")
        print(f"调整速度后的音频时长：{len(ad_audio)}ms")


def generate_background_audio(duration_seconds, output_path):
    """精确生成背景音频"""
    # 计算精确采样数（44.1kHz标准）
    samples = int(duration_seconds * 44100)
    # 生成静音波形数组
    silent_array = np.zeros((samples, 2), dtype=np.int16)
    # 创建音频段
    background = AudioSegment(
        silent_array.tobytes(),
        frame_rate=44100,
        sample_width=2,
        channels=2
    )
    # 精确导出
    background.export(output_path, format="wav")  # WAV格式更精确
    print(f"精确生成背景音频：{len(background) / 1000:.3f}秒")


def get_exact_duration(audio_path):
    """获取精确音频时长"""
    info = mediainfo(audio_path)
    return float(info['duration'])


def insert_ads_to_audio(background_path, ads, output_path, movie_duration_seconds):
    """精准插入音频描述"""
    # 按时间排序音频描述
    ads = sorted(ads, key=lambda x: x[0])

    # 加载高精度背景音频
    background = AudioSegment.from_wav(background_path)
    movie_duration_ms = movie_duration_seconds * 1000

    # 音频描述时间轴校准
    timeline = []
    for start_time, duration, ad_text, emotion in ads:  # 增加emotion参数
        start_time = float(start_time)
        duration = float(duration)
        insert_pos = int(start_time * 1000)
        max_ad_duration = int(duration * 1000)

        if insert_pos >= movie_duration_ms:
            continue
        
        
        emotion_wav_path = os.path.dirname(os.path.abspath(__file__))
        # 选择风格向量和参考音频文件
        # emotion_wav_path = "emotion_wav"  # 指定存放情感音频的文件夹路径

        if emotion == "HAPPY":
            style_wav = os.path.join(emotion_wav_path, "emotion_wav\\happy_6.wav")  # 指定开心风格的参考音频
        elif emotion == "SAD":
            style_wav = os.path.join(emotion_wav_path, "emotion_wav\\sad_6.wav")    # 指定悲伤风格的参考音频
        elif emotion == "NEUTRAL":
            style_wav = os.path.join(emotion_wav_path, "emotion_wav\\neutral_6.wav") 
        elif emotion == "ANGRY":
            style_wav = os.path.join(emotion_wav_path, "emotion_wav\\angry_6.wav")  # 指定愤怒风格的参考音频
        elif emotion == "SURPRISED":
            style_wav = os.path.join(emotion_wav_path, "emotion_wav\\surprised_6.wav")  # 指定惊讶风格的参考音频
        else:
            style_wav = os.path.join(emotion_wav_path, "emotion_wav\\neutral_6.wav")  # 未知情感默认使用中性风格且无参考音频

        #test
        # style_vector = angry_vector
        # style_wav = None  # 测试时强制使用愤怒风格

        # 生成音频描述音频
        ad_path = f"temp_ad_{insert_pos}.wav"
        text_to_speech(ad_text, ad_path, max_ad_duration, style_wav=style_wav)  # 传递风格向量和参考音频

        # 获取精确时长
        ad_audio = AudioSegment.from_wav(ad_path)
        ad_duration = len(ad_audio)

        # 动态调整插入策略
        available_space = movie_duration_ms - insert_pos
        if ad_duration > available_space:
            # 裁剪音频描述音频以适应可用空间
            adjusted_ad = ad_audio[:available_space]
            adjusted_ad.export(ad_path, format="wav")
            ad_audio = adjusted_ad

        timeline.append((insert_pos, ad_path))

    # 时间轴冲突检测
    prev_end = 0
    for i, (start, path) in enumerate(timeline):
        ad_audio = AudioSegment.from_wav(path)
        duration = len(ad_audio)
        end = start + duration

        if start < prev_end:
            # 解决重叠：顺延插入
            start = prev_end + 1000  # 留1秒间隔
            timeline[i] = (start, path)
            end = start + duration

        if end > movie_duration_ms:
            timeline[i] = (start, None)  # 标记无效
        else:
            prev_end = end

    # 执行插入
    background = AudioSegment.silent(duration=movie_duration_ms)
    for start, path in timeline:
        if not path:
            continue
        ad_audio = AudioSegment.from_wav(path)
        background = background.overlay(ad_audio, position=start)

    # 严格长度控制
    background = background[:movie_duration_ms]
    background.export(output_path, format="wav")
    print(f"最终音频精度：{len(background)}ms")


def get_audio_volume(file_path):
    """获取音频的音量信息"""
    command = [
        "ffmpeg",
        "-i", file_path,
        "-af", "volumedetect",
        "-f", "null", "-"
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    output = result.stderr

    # 提取平均音量和峰值音量
    mean_volume_match = re.search(r"mean_volume: ([+-]?[\d.]+) dB", output)
    max_volume_match = re.search(r"max_volume: ([+-]?[\d.]+) dB", output)

    mean_volume = float(mean_volume_match.group(1)) if mean_volume_match else None
    max_volume = float(max_volume_match.group(1)) if max_volume_match else None

    return mean_volume, max_volume


def combine_audio_with_volume_adjustment(video_path, audio_path, output_path, video_volume=1.0, ad_volume=1.0):
    """将生成的音频与原视频的音频混合，并调整音量关系，输出包含两条音轨的视频"""
    # 使用FFmpeg命令将生成的音频与原视频的音频混合，并调整音量
    command = [
        "ffmpeg",
        "-i", video_path,  # 输入视频
        "-i", audio_path,  # 输入音频
        "-filter_complex", f"[0:a]volume={video_volume}[v];[1:a]volume={ad_volume}[ad];[v][ad]amix=inputs=2:duration=longest[mixed];[0:a]volume={video_volume}[original]",
        "-map", "0:v",  # 使用视频流
        "-map", "[mixed]",  # 映射混合后的音频流
        "-map", "[original]",  # 映射原音频流
        "-c:v", "copy",  # 保留视频原始编码
        "-c:a", "aac",  # 使用AAC编码
        "-metadata:s:a:0", "title=Mixed Audio",  # 设置混合后音轨的名称
        "-metadata:s:a:1", "title=Original Audio",  # 设置原音轨的名称
        output_path  # 输出文件
    ]
    try:
        subprocess.run(command, check=True)
        print(f"音频与视频混合完成：{output_path}")
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg命令执行出错: {e}")


def cleanup_files(temp_files):
    """清理临时文件"""
    try:
        for file in temp_files:
            if os.path.exists(file):
                os.remove(file)
                print(f"已删除临时文件：{file}")

    except Exception as e:
        print(f"清理文件时出错：{e}")


def get_video_duration(video_path):
    """获取视频的时长（秒）"""
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    duration = float(result.stdout.strip())
    return duration


class VolumeAdjustmentGUI:
    # def __init__(self, root, video_path, audio_output_path):
    #     self.root = root
    #     self.video_path = video_path
    #     self.audio_output_path = audio_output_path

    #     # 获取原视频和插入音频的音量信息
    #     self.video_mean_volume, self.video_max_volume = get_audio_volume(video_path)
    #     self.ad_mean_volume, self.ad_max_volume = get_audio_volume(audio_output_path)

    #     print(f"原视频平均音量: {self.video_mean_volume} dB, 峰值音量: {self.video_max_volume} dB")
    #     print(f"插入音频平均音量: {self.ad_mean_volume} dB, 峰值音量: {self.ad_max_volume} dB")
    def __init__(self, root, video_path, audio_output_path,start_sec,end_sec,final_video_path):
        self.root = root
        self.video_path = video_path
        self.audio_output_path = audio_output_path
        self.final_video_path=final_video_path

        # 构建FFmpeg命令 音频切片
        self.video_path_cutted="temp_output_video_cutted.mp4"
        command = [
            "ffmpeg",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", self.video_path,
            "-c", "copy",
            "-y",
            self.video_path_cutted
        ]
        # 执行命令
        subprocess.run(command)
        self.audio_output_path_cutted="temp_ad_video_cutted.wav"
        command = [
            "ffmpeg",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", self.audio_output_path,
            "-c", "copy",
            "-y",
            self.audio_output_path_cutted
        ]
        # 执行命令
        subprocess.run(command)

        
        # 获取原视频和插入音频的音量信息
        self.video_mean_volume, self.video_max_volume = get_audio_volume(video_path)
        self.ad_mean_volume, self.ad_max_volume = get_audio_volume(audio_output_path)

        print(f"原视频平均音量: {self.video_mean_volume} dB, 峰值音量: {self.video_max_volume} dB")
        print(f"插入音频平均音量: {self.ad_mean_volume} dB, 峰值音量: {self.ad_max_volume} dB")
        # 创建GUI
        self.create_gui()

    def create_gui(self):
        # 设置窗口标题
        self.root.title("音量调整工具")

        # 创建标签和滑块
        ttk.Label(self.root, text="原视频音量调整:").grid(column=0, row=0, padx=10, pady=10, sticky="w")
        self.video_volume_scale = ttk.Scale(self.root, from_=0, to=2, value=1.0, command=self.update_video_volume)
        self.video_volume_scale.grid(column=1, row=0, padx=10, pady=10, sticky="ew")
        self.video_volume_label = ttk.Label(self.root, text="1.0")
        self.video_volume_label.grid(column=2, row=0, padx=10, pady=10, sticky="w")

        ttk.Label(self.root, text="旁白音量调整:").grid(column=0, row=1, padx=10, pady=10, sticky="w")
        self.ad_volume_scale = ttk.Scale(self.root, from_=0, to=2, value=1.0, command=self.update_ad_volume)
        self.ad_volume_scale.grid(column=1, row=1, padx=10, pady=10, sticky="ew")
        self.ad_volume_label = ttk.Label(self.root, text="1.0")
        self.ad_volume_label.grid(column=2, row=1, padx=10, pady=10, sticky="w")

        # 创建按钮
        ttk.Button(self.root, text="播放", command=self.play_audio).grid(column=0, row=2, padx=10, pady=10)
        ttk.Button(self.root, text="保存", command=self.save_audio).grid(column=1, row=2, padx=10, pady=10)

        # 设置窗口大小和位置
        self.root.geometry("400x150")

    def update_video_volume(self, value):
        self.video_volume_label.config(text=f"{float(value):.1f}")

    def update_ad_volume(self, value):
        self.ad_volume_label.config(text=f"{float(value):.1f}")

    def play_audio(self):
        # 获取当前的音量值
        video_volume = float(self.video_volume_scale.get())
        ad_volume = float(self.ad_volume_scale.get())

        # 临时输出文件
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_output_path = f"temp_output_{current_time}.mp4"

        # 混合音频并播放
        combine_audio_with_volume_adjustment(
            self.video_path_cutted,
            self.audio_output_path_cutted,
            temp_output_path,
            video_volume,
            ad_volume
        )

        # 使用默认播放器播放
        os.system(f'start {temp_output_path}')

    def save_audio(self):
        # 获取当前的音量值
        video_volume = float(self.video_volume_scale.get())
        ad_volume = float(self.ad_volume_scale.get())

        # 保存最终输出文件
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = self.final_video_path
        combine_audio_with_volume_adjustment(
            self.video_path,
            self.audio_output_path,
            output_path,
            video_volume,
            ad_volume
        )

        messagebox.showinfo("成功", f"音频已保存到 {output_path}")
        self.root.destroy()


def T2S(csv_file,final_video_path,video_path):
    # 1. 读取CSV文件
    # csv_file = 'test_emotion.csv'
    df = pd.read_csv(csv_file)

    # 2. 提取音频描述时间和文本
    ads = []
    for _, row in df.iterrows():
        start_time = row['start_time']
        duration = row['duration']
        ad_text = row['description']
        emotion = row['Sense']  # 增加emotion的读取
        ads.append((start_time, duration, ad_text, emotion))  # 增加emotion到ads列表

    # 3. 获取视频文件路径
    # video_path = "test.mp4"  # 视频文件与脚本在同一目录下

    # 4. 动态获取视频时长
    movie_duration_seconds = get_video_duration(video_path)
    print(f"视频时长：{movie_duration_seconds:.2f}秒")

    # 5. 生成背景音频
    current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
    background_path = f'background_{current_time}.wav'
    generate_background_audio(movie_duration_seconds, background_path)

    # 6. 插入音频描述音频
    audio_output_path = f'final_audio_{current_time}.wav'
    insert_ads_to_audio(background_path, ads, audio_output_path, movie_duration_seconds)

    # 7. 创建GUI
    # root = tk.Tk()
    # app = VolumeAdjustmentGUI(root, video_path, audio_output_path)
    # root.mainloop()
    root = tk.Tk()
    start_sec = max(ads[0][0] - 60, 0)
    end_sec = min(ads[0][0] + 60, movie_duration_seconds)
    app = VolumeAdjustmentGUI(root, video_path, audio_output_path,start_sec,end_sec,final_video_path)
    root.mainloop()

    # 8. 清理临时文件
    temp_files = glob.glob("background_*.wav") + glob.glob("final_audio_*.wav") + glob.glob("temp_ad_*.wav") + glob.glob("temp_output_*.mp4")
    cleanup_files(temp_files)


if __name__ == "__main__":
    T2S(r"D:\19059\Documents\Learning\JLUSE\CCFgy\血战台儿庄\merged_AD_scripts.csv",
        r"D:\19059\Documents\Learning\JLUSE\CCFgy\血战台儿庄\BloodyBattleInTaierzhuang_3min_.mp4",
        r"D:\19059\Documents\Learning\JLUSE\CCFgy\血战台儿庄\BloodyBattleInTaierzhuang_3min.mp4"
        )
    # emotion_wav_path = os.path.dirname(os.path.abspath(__file__))
    # print(emotion_wav_path)
