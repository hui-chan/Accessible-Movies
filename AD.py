import os
import sys

import audio_extraction_video_compression
import character_recognition
import detect_voice_activity
import divide_video
import gen_AD_script
import merge_AD_script
import SenseVoice


def AD(certain_path,video_name_without_ext,video_path):
    # # Get video path from command line argument
    # if len(sys.argv) < 2:
    #     print("Usage: python AD.py <video_path>")
    #     sys.exit(1)
    # video_path = sys.argv[1]

    # # Create output directory structure
    # local_appdata = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    # program_path = os.path.join(local_appdata, 'AudioDescription')
    # os.makedirs(program_path, exist_ok=True)

    # # Generate output audio path
    # video_filename = os.path.basename(video_path)
    # video_name_without_ext = os.path.splitext(video_filename)[0]
    # certain_path=os.path.join(program_path, video_name_without_ext)
    # os.makedirs(certain_path, exist_ok=True)
    
    # 提取音频，压缩视频
    audio_path = os.path.join(certain_path, f"{video_name_without_ext}.wav")#视频的音频文件
    compressed_video_path = os.path.join(certain_path, f"{video_name_without_ext}_compressed.mp4")#压缩后的视频
    audio_extraction_video_compression.extract_audio_compress_video(video_path,audio_path,compressed_video_path)

    #人物角色识别
    identified_video_path=os.path.join(certain_path, f"{video_name_without_ext}_identified.mp4")#人物角色识别之后的视频
    CHARACTER_BANK_PATH=os.path.join(certain_path, 'photos')
    character_recognition.character_recognition(compressed_video_path,audio_path,identified_video_path,CHARACTER_BANK_PATH)
    
    #语音活动检测
    vad_file_path = os.path.join(certain_path, f"{video_name_without_ext}_vad.csv")#语音端点检测结果
    gap_file_path= os.path.join(certain_path, f"{video_name_without_ext}_gap.csv")#对白间隙
    detect_voice_activity.fsmn_vad(audio_path,vad_file_path,gap_file_path)
    
    #结合语音活动检测结果给视频分段，也给对白间隙进行分段
    video_seg_dir=os.path.join(certain_path, 'video_seg')#分段视频存放文件夹
    os.makedirs(video_seg_dir, exist_ok=True)
    valid_timestamps=divide_video.split_video_by_thresholds(vad_file_path,identified_video_path,video_seg_dir,600)#600s一段
    if valid_timestamps:divide_video.split_gap_csv(valid_timestamps,gap_file_path,video_seg_dir)
    
    # 生成AD脚本
    for video_file in os.listdir(video_seg_dir):
        if video_file.endswith('.mp4'):
            video_file_path = os.path.join(video_seg_dir, video_file)
            base_path, _ = os.path.splitext(video_file_path)# 分离路径的主干部分和扩展名
            gap_path = base_path + ".csv"# 拼接主干部分和新的 .csv  扩展名
            AD_script_path=base_path+"_AD_script.csv"
            with open(AD_script_path, 'w') as file:# 在 'w' 模式下打开文件时，如果文件是新的或者被清空了，它就是空的。
                pass # 'pass' 语句表示这里什么也不做
            gen_AD_script.gen_AD_script(video_file_path,gap_path,AD_script_path)
    #将AD脚本片段合成为一整个AD脚本
    merge_AD_script.merge_AD_script(video_seg_dir)

    SenseVoice.Sense_add(f'{video_seg_dir}/merged_AD_scripts.csv',audio_path,certain_path)
    