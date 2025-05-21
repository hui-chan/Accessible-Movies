import csv
import json
import os
import re
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
            

def read_gap_file(filepath,video_end):
    """读取并解析对白间隙信息文件。"""

    # video_end=get_video_duration(filepath)
    gaps = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                # 跳过空行或格式不正确的行
                if i == 0 :
                    continue
                start_time=float(row[0].strip())
                end_time=start_time+float(row[1].strip())-1
                gaps.append([round(max(0,start_time-10),1),round(start_time+1,1)])
                gaps.append([round(end_time,1),round(min(video_end,end_time+11),1)])
                # print("111:")
                # print(max(0,start_time-10))
                # print(start_time+1)
                # print({max(0,start_time-10),start_time+1})
                # print("222:")
                # print({end_time,min(video_end,end_time+11)})
                # print(round(max(0,start_time-10),1))
                # print(round(start_time+1,1))
                # print([round(max(0,start_time-10),1),round(start_time+1,1)])

        return gaps
    except FileNotFoundError:
        print(f"错误: 找不到间隙文件 {filepath}")
        return None
    except Exception as e:
        print(f"读取间隙文件时发生错误 {filepath}: {e}")
        return None

def auto_cutting(wav_file,timestamps,folder_path):    
    input_file = wav_file
    try:
        os.mkdir(folder_path)
        print(f"文件夹 '{folder_path}' 新建成功")
    except FileExistsError:
        print(f"文件夹 '{folder_path}' 已经存在")
    except Exception as e:
        print(f"新建文件夹时出错: {e}")
    
    out_file_list=[]
    new_tamps=[]
    for idx, (start_ms, end_ms) in enumerate(timestamps, start=0):
        # 转换毫秒为秒（保留两位小数）
        start_sec = start_ms
        end_sec = end_ms
        # 生成输出文件名并存入列表
        output_file0 = f"segment_{idx:04d}"
        output_file = f"{folder_path}\{output_file0}.wav"
        out_file_list.append(f"{output_file0}\t{output_file}")
        new_tamps.append([start_sec,end_sec]) 

        #print(new_tamps)  
        # 构建FFmpeg命令
        command = [
            "ffmpeg",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", input_file,
            "-c", "copy",
            "-y",
            output_file
        ]
        # 执行命令
        if idx > 0:
            command += ["-loglevel", "error"]
        subprocess.run(command)

    with open("wav.scp", "w") as f:
        f.write("\n".join(out_file_list))

    return new_tamps

def SenseVoice(wav_files,output_files):
    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
    
    try:
        os.mkdir(output_files)
        print(f"文件夹 '{output_files}' 新建成功")
    except FileExistsError:
        print(f"文件夹 '{output_files}' 已经存在")
    except Exception as e:
        print(f"新建文件夹时出错: {e}")
    
    
    model_dir = "iic/SenseVoiceSmall"
    model = AutoModel(
        model=model_dir, 
        trust_remote_code=True,
        remote_code="./SenseVoice-main/model.py",
        device="cuda:0",
        ban_emo_unk=True,
    )
    # en
    res = model.generate(
        input=wav_files,
        cache={},
        language="auto", # "zh", "en", "yue", "ja", "ko", "nospeech","auto"
        use_itn=True,
        batch_size=64, 
        output_dir = output_files
    )
    print(res)
    print(res[0])
    print(res[0]["text"])
    print(len(res))
    
    i=0
    result=[]
    while i<len(res)-1:
        temp_result0 = [item for item in re.findall(r'<\|(.*?)\|>', res[i]["text"]) if item]
        temp_result1 = [item for item in re.findall(r'<\|(.*?)\|>', res[i+1]["text"]) if item]
        if(temp_result0[1]==temp_result1[1]):
            result.append(temp_result0[1])
        else:
            result.append('nEUTRAL')
        i+=2
    print(result)
    return result

    # model = AutoModel(model=model_dir, trust_remote_code=True, device="cuda:0")

    # res = model.generate(
    #     input=wav_files,
    #     cache={},
    #     language="auto", # "zh", "en", "yue", "ja", "ko", "nospeech"
    #     use_itn=True,
    #     batch_size=64, 
    #     output_dir = output_files,
    # )

def Sense_add(filepath,videopath,certain_path):
    video_end=get_video_duration(videopath)
    split=read_gap_file(filepath,video_end)
    print(split)
    auto_cutting(videopath,split,f'{certain_path}/temp_sense_cut1')
    sense_res=SenseVoice("wav.scp",f'{certain_path}/temp_sense_cut2')
    df = pd.read_csv(filepath)
    df['Sense'] = sense_res
    df.to_csv(filepath, index=False)
    try:
        # shutil.rmtree("./test")
        # shutil.rmtree("./test1")
        # os.remove("./test1/*")
        os.remove("./wav.scp")
        print("文件wav.scp已删除")
    except Exception as e:
        print(f"文件wav.scp删除失败: {e}")


if __name__ == '__main__':
    filepath=r"C:\Users\19059\AppData\Local\AD\BloodyBattleInTaierzhuang_5min\video_seg\merged_AD_scripts.csv"
    videopath=r"C:\Users\19059\AppData\Local\AD\BloodyBattleInTaierzhuang_5min\BloodyBattleInTaierzhuang_5min.wav"
    #Sense_add(filepath,videopath,certain_path)

    
