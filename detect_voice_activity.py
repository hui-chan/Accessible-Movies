import csv
import os

from funasr import AutoModel


def fsmn_vad(audio_path,vad_file_path,gap_file_path):
    # from funasr import AutoModel
    model = AutoModel(model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",disable_update=True)
    res = model.generate(input=audio_path)
    # print(res[0])
    vad_data=res[0]["value"]# 从fsmn-vad得到的时间戳
    #print(vad_data)
    
    # kongzhipanding
    if not vad_data:
        print("无间隙点。")
        return
    
    #处理vad数据
    processed_vad_data=[]
    for row in vad_data:
        # 除以 1000 并四舍五入保留一位小数
        processed_vad_data.append([round(row[0] / 1000, 1),round(row[1] / 1000, 1)])

    #将vad数据写入文件
    try:
        with open(vad_file_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerows(processed_vad_data)
        print(f"已将voice activity detection数据写入到文件: {vad_file_path}")
    except Exception as e:
        print(f"voice activity detection数据写入 CSV 文件时发生错误: {e}")

    #根据vad数据得到gap数据，并将gap数据写入文件
    gap_data=[]
    if processed_vad_data[0][0]>2:gap_data.append([0.0,processed_vad_data[0][0]])
    newstart= processed_vad_data[0][1]
    i=1
    j=0
    while i<len(processed_vad_data):
        if processed_vad_data[i][0]-processed_vad_data[j][1]>2 :
            gap_data.append([newstart,round(processed_vad_data[i][0]-processed_vad_data[j][1],1)])
        newstart=processed_vad_data[i][1]
        i+=1
        j+=1


    with open(gap_file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        #writer.writerow(['start_time(s)', 'duration(s)'])
        writer.writerows(gap_data)

    print(gap_data)



if __name__=="__main__":
    fsmn_vad(r"D:\Thunder\BloodyBattleTaierzhuang_0419test\BloodyBattleInTaierzhuang_1fps_30min.mp4")