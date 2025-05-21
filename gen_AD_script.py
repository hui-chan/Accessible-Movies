import argparse  # 用于处理命令行参数
import csv
import os
import time
from pathlib import Path

import google.generativeai as genai

import simplify_sentence_ad

# --- 常量定义 ---
MODEL_NAME = 'gemini-2.0-flash-001'#gemini-2.5-pro-preview-03-25和gemini-2.0-flash-thinking-exp-01-21由于配额和限速原因不好用
OUTPUT_CSV_HEADER = ["start_time","duration", "description"]
# Gemini API 文件上传/处理的轮询间隔（秒）
FILE_PROCESSING_POLL_INTERVAL = 10
# Gemini API 文件上传/处理的超时时间（秒）
FILE_PROCESSING_TIMEOUT = 300 # 5 分钟
MAX_UPLOAD_ATTEMPTS = 3      # 最大上传尝试次数 (1次初始尝试 + 2次重试)
RETRY_DELAY = 10             # 每次重试前的等待时间（秒）
PROMPT_TEMPLATE = """任务：理解视频内容，生成文本描述。

输入信息：
1.  视频文件：{video_name} 
2.  对白间隙信息 (格式：起始时间(MM:SS),结束时间(MM:SS)，描述字数):
{gap_data_string}

要求：
请结合视频的视觉信息（人物的动作、神态、心理，以及场景），参考上面列出的对白间隙，生成文本描述，描述字数包含在每行对白间隙信息的末尾。文本描述不要包含人物语言信息！使用中文！这些描述是为了方便视障人士理解视频。

输出格式：
每个描述占独立的一行。每行包括文本描述起始时间、结束时间、文本内容，用','隔开，除此之外不要输出其他任何内容（如前导语、编号、结束语等）

输出样例：
00:01,01:05,甲飞快地奔跑。
02:10,02:47,乙低头不语。
04:23,04:51,两伙人扭打在一起。
"""


# --- 函数定义 ---
def format_seconds_rounded(seconds):
  """使用数学运算将以秒为单位的时间四舍五入并格式化为 MM:SS 格式。"""
  rounded_seconds = round(seconds)
  minutes = int(rounded_seconds // 60)
  remaining_seconds = int(rounded_seconds % 60)
  return f"{minutes:02d}:{remaining_seconds:02d}"
def time_to_seconds(time_str):
  """将 MM:SS 格式的时间字符串转换为总秒数。"""
  try:
    minutes, seconds = map(int, time_str.split(':'))
    total_seconds = (minutes * 60) + seconds
    return total_seconds
  except ValueError:
    return "输入格式错误，请使用 MM:SS 格式"
def write_csv(filepath, data, header):
    """将数据写入 CSV 文件。"""
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)
            for row in data:
                writer.writerow(row)
        print(f"成功将结果写入 CSV 文件: {filepath}")
    except IOError as e:
        print(f"写入 CSV 文件时发生 IO 错误 {filepath}: {e}")
    except Exception as e:
        print(f"写入 CSV 文件时发生未知错误 {filepath}: {e}")

def read_gap_file(filepath):
    """读取并解析对白间隙信息文件。"""
    res = ""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                # 跳过空行或格式不正确的行
                if not row or len(row) != 2:
                    print(f"警告: 跳过间隙文件第 {i+1} 行，格式不正确: {row}")
                    continue
                try:
                    start = format_seconds_rounded(float(row[0].strip()))#改成MM:SS的形式
                    end = format_seconds_rounded(float(row[0].strip())+float(row[1].strip()))
                    chars=int(float(row[1].strip())*5)
                    res=res+"\n"+str(start)+","+str(end)+","+str(chars)
                except ValueError:
                    print(f"警告: 跳过间隙文件第 {i+1} 行，无法解析为数字: {row}")
                    continue
        """将间隙数据格式化为插入到 Prompt 中的字符串。"""
        return res
    except FileNotFoundError:
        print(f"错误: 找不到间隙文件 {filepath}")
        return None
    except Exception as e:
        print(f"读取间隙文件时发生错误 {filepath}: {e}")
        return None


def upload_file_with_retry(filepath):
    """
    上传文件到 Gemini API，包含状态检查、超时和重试机制。

    如果上传或处理失败，最多会重试 MAX_UPLOAD_ATTEMPTS-1 次。

    Args:
        filepath: 要上传的文件的本地路径。

    Returns:
        成功上传并处理完成的 UploadedFile 对象，或在所有尝试失败后返回 None。
    """
    uploaded_file = None # 初始化，以便在最终失败时知道是否有文件对象尝试创建

    for attempt in range(MAX_UPLOAD_ATTEMPTS):
        print(f"\n--- 尝试上传文件: {filepath} (尝试 {attempt + 1}/{MAX_UPLOAD_ATTEMPTS}) ---")
        successful_attempt = False # 标记当前尝试是否成功

        try:
            # 1. 提交上传请求
            print(f"正在提交上传请求: {filepath} ...")
            uploaded_file = genai.upload_file(path=filepath)
            print(f"文件上传请求已提交。文件名: {uploaded_file.name}, URI: {uploaded_file.uri}")

            # 2. 检查文件处理状态
            start_time = time.time()
            print("正在等待文件处理完成", end='', flush=True)

            while True:
                # 检查是否超时 (针对当前尝试)
                if time.time() - start_time > FILE_PROCESSING_TIMEOUT:
                    print(f"\n错误: 文件处理超时 ({FILE_PROCESSING_TIMEOUT} 秒) 在尝试 {attempt + 1} 中。")
                    # 尝试删除可能未完成的文件
                    if uploaded_file and uploaded_file.name:
                        try:
                            genai.delete_file(uploaded_file.name)
                            print(f"已尝试删除超时的文件: {uploaded_file.name}")
                        except Exception as del_e:
                            print(f"警告: 删除超时文件时出错: {del_e}")
                    # 当前尝试失败
                    successful_attempt = False
                    break # 退出状态检查循环，进入下一次尝试或结束

                # 获取文件状态
                retrieved_file = None
                try:
                     retrieved_file = genai.get_file(uploaded_file.name)
                except Exception as get_e:
                     # 获取状态本身失败，可能是暂时性网络问题，重试获取状态
                     print(f"\n警告：获取文件状态时出错（可能是暂时性问题）: {get_e}。将在 {FILE_PROCESSING_POLL_INTERVAL} 秒后重试获取状态。")
                     time.sleep(FILE_PROCESSING_POLL_INTERVAL)
                     continue # 继续尝试获取状态

                if retrieved_file.state.name == "ACTIVE":
                    print("\n文件处理完成，状态: ACTIVE。")
                    successful_attempt = True # 当前尝试成功
                    uploaded_file = retrieved_file # 更新为带有最终状态的文件对象
                    break # 退出状态检查循环

                elif retrieved_file.state.name == "FAILED":
                    print(f"\n错误: 文件处理失败。状态: {retrieved_file.state.name} 在尝试 {attempt + 1} 中。")
                    # 失败后通常不需要手动删除，但可以尝试
                    if retrieved_file and retrieved_file.name:
                        try:
                            genai.delete_file(retrieved_file.name)
                            print(f"已尝试删除处理失败的文件: {retrieved_file.name}")
                        except Exception as del_e:
                            print(f"警告: 删除失败文件时出错: {del_e}")
                    # 当前尝试失败
                    successful_attempt = False
                    break # 退出状态检查循环

                elif retrieved_file.state.name == "PROCESSING":
                    print('.', end='', flush=True)
                    time.sleep(FILE_PROCESSING_POLL_INTERVAL)
                else:
                    # 处理其他未知或预期外的状态，等待并重试获取状态
                    print(f"\n警告：文件处于意外状态: {retrieved_file.state.name} 在尝试 {attempt + 1} 中。将在 {FILE_PROCESSING_POLL_INTERVAL} 秒后重试获取状态。")
                    time.sleep(FILE_PROCESSING_POLL_INTERVAL)

            # 检查状态检查循环的结果
            if successful_attempt:
                return uploaded_file # 成功，立即返回文件对象，结束整个函数

        except Exception as e:
            # 捕获在上传或状态检查过程中发生的任何其他异常
            print(f"\n上传或处理文件时发生未预期错误: {e} 在尝试 {attempt + 1} 中。")
            # 如果上传对象已创建但出错，尝试删除
            if uploaded_file and uploaded_file.name:
                 try:
                     genai.delete_file(uploaded_file.name)
                     print(f"已尝试删除出错的文件: {uploaded_file.name}")
                 except Exception as del_e:
                     print(f"警告: 删除出错文件时出错: {del_e}")
            successful_attempt = False # 标记当前尝试失败

        # 如果当前尝试不成功且不是最后一次尝试，则等待一段时间再重试
        if not successful_attempt and attempt < MAX_UPLOAD_ATTEMPTS - 1:
            print(f"上传尝试 {attempt + 1} 失败. 正在等待 {RETRY_DELAY} 秒后重试...")
            time.sleep(RETRY_DELAY)

    # 如果循环结束（所有尝试都失败了），则返回 None
    print(f"\n错误: 所有 {MAX_UPLOAD_ATTEMPTS} 次上传尝试均失败，文件 {filepath} 未能成功处理。")
    return None


def generate_descriptions(api_key, video_path, gap_data_string):
    """配置 API，上传文件，调用 Gemini 模型生成描述。"""
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"配置 Gemini API 时出错: {e}")
        return None

    uploaded_video = None
    try:
        # 1. 上传视频文件
        uploaded_video = upload_file_with_retry(video_path)
        if not uploaded_video:
            print("视频文件上传或处理失败，无法继续。")
            return None # 上传失败，直接返回

        # 2.--- 初始化 Gemini 模型和聊天 ---
        print(f"初始化 Gemini 模型: {MODEL_NAME}")
        model = None
        try:
            model = genai.GenerativeModel(MODEL_NAME)
        except Exception as e:
            print(f"错误：初始化 Gemini 模型失败: {e}")
            # 如果模型初始化失败，也需要清理已上传的视频文件
            if uploaded_video and uploaded_video.name:
                try:
                    print(f"清理: 删除已上传的文件 {uploaded_video.name}")
                    genai.delete_file(uploaded_video.name)
                except Exception as delete_e:
                    print(f"警告: 清理上传文件时出错: {delete_e}")
            return None # 返回 None 表示严重错误

        print("开始与 Gemini 进行聊天会话...")

        chat = model.start_chat(history=[])
        response=chat.send_message([uploaded_video, "这个视频片段中的主要人物已用绿色文字标注角色名称，请给出这段视频中出现的主要人物。"])
        print(response.text)

        # 3. 准备 Prompt
        video_name = Path(video_path).name
        full_prompt = PROMPT_TEMPLATE.format(
            video_name=video_name,
            gap_data_string=gap_data_string
        )
        print("\n--- 发送给 Gemini 的 Prompt ---")
        print(full_prompt)
        print("-----------------------------\n")

        
        # 4. 调用模型生成内容
        response = chat.send_message(full_prompt)

        # 5. 处理响应
        print("已收到 Gemini 的回复。")

        # 检查是否有阻止原因
        if response.prompt_feedback.block_reason:
            print(f"错误: 请求被阻止。原因: {response.prompt_feedback.block_reason}")
            if response.prompt_feedback.safety_ratings:
                 print("安全评级:")
                 for rating in response.prompt_feedback.safety_ratings:
                     print(f"  - {rating.category}: {rating.probability}")
            return None

        # 检查候选内容
        if not response.candidates:
            print("错误: Gemini 回复中没有候选内容。")
            # 打印回复详情以供调试
            # print("原始回复详情:", response)
            return None

        # 检查第一个候选内容的完成原因和安全评级
        candidate = response.candidates[0]
        if candidate.finish_reason != 'STOP':
            print(f"警告: 内容生成可能未完全完成。原因: {candidate.finish_reason}")
        if candidate.safety_ratings:
            print("内容安全评级:")
            for rating in candidate.safety_ratings:
                print(f"  - {rating.category}: {rating.probability}")
                # 你可以根据需要在这里添加更严格的安全检查逻辑

        # 提取文本内容
        if not candidate.content or not candidate.content.parts:
             print("错误：Gemini 回复的候选内容中缺少文本部分。")
             # print("原始候选内容:", candidate)
             return None

        raw_descriptions_text = candidate.content.parts[0].text
        print("\n--- Gemini 返回的原始描述文本 ---")
        print(raw_descriptions_text)
        print("---------------------------------\n")

        # 将返回的文本按行分割成描述列表，并去除前导ascii字符串
        descriptions = [line.strip() for line in raw_descriptions_text.strip().split('\n') if line.strip() and line.strip()[0].isdigit()]
        return descriptions

    except Exception as e:
        print(f"\n调用 Gemini API 或处理响应时发生错误: {e}")
        import traceback
        traceback.print_exc() # 打印详细错误堆栈
        return None
    finally:
        # 6. 清理上传的文件 (无论成功或失败都尝试删除)
        if uploaded_video and uploaded_video.name:
            try:
                print(f"正在删除已上传的视频文件: {uploaded_video.name}")
                genai.delete_file(uploaded_video.name)
                print("视频文件已删除。")
            except Exception as e:
                print(f"警告: 删除上传的视频文件时发生错误: {e}")

# --- 主程序入口 ---
def gen_AD_script(video_path,gap_path,output_path):
    # --- 检查输入文件是否存在 ---
    if not os.path.isfile(video_path):
        print(f"错误: 视频文件不存在 {video_path}")
        exit(1)
    if not os.path.isfile(gap_path):
        print(f"错误: 间隙信息文件不存在 {gap_path}")
        exit(1)

    # --- 获取 API Key ---
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("错误: 未找到 GEMINI_API_KEY 环境变量。请设置该变量后重试。")
        exit(1)
    print("成功获取 GEMINI_API_KEY。")

    # --- 读取间隙数据 ---
    print(f"正在读取间隙文件: {gap_path}")
    gap_data_string = read_gap_file(gap_path)
    if gap_data_string is None:
        print("无法读取间隙文件，程序终止。")
        exit(1)
    if not gap_data_string:
        print("警告: 间隙文件为空或未包含有效数据，程序终止。")
        #exit(0) # 文件有效但无内容，正常退出

    # --- 调用 Gemini 生成描述 ---
    descriptions = generate_descriptions(api_key, str(video_path), gap_data_string) # 确保路径是字符串

    if descriptions is None:
        print("未能从 Gemini 获取有效的描述。请检查错误信息。程序终止。")
        return

    print(f"Gemini 返回了 {len(descriptions)} 个描述。")

    # --- 写入 CSV 文件 ---
    # 简化部分
    print("descriptions未简化前：\n")
    print(descriptions)
    
    # 假设原始的 processed_descriptions 列表是字符串列表
    processed_descriptions = []
    
    for item_string in descriptions:
        # 按逗号分割字符串，最多分割前两项，以防描述文本中也包含逗号
        parts = item_string.split(',', 2)
        if len(parts) == 3: # 确保分割出了3部分
            processed_descriptions.append(parts) # parts 是一个包含 [start_time_str, end_time_str, description_str] 的列表
        else:
            print(f"警告：跳过格式不正确的行: {item_string}")

    filtered_descriptions=[]
    # 现在使用处理后的列表
    for i in range(len(processed_descriptions)):
        try:
            start_time = time_to_seconds(processed_descriptions[i][0]) # 现在 processed_descriptions[i][0] 是 '01:09' 这样的字符串
            end_time = time_to_seconds(processed_descriptions[i][1])   # processed_descriptions[i][1] 是 '04:07' 这样的字符串
            duration = end_time - start_time
            if duration <=0: continue # 避免负数时长
            simplified_desc = simplify_sentence_ad.shorten_sentence(processed_descriptions[i][2], int(duration * 5))
            processed_descriptions[i][0]=start_time
            processed_descriptions[i][1]=duration
            processed_descriptions[i][2] = simplified_desc # 更新处理后的列表中的描述部分
            if i==0:
                filtered_descriptions.append(processed_descriptions[i])
            else:
                if simplified_desc!=processed_descriptions[i-1][2]:
                    filtered_descriptions.append(processed_descriptions[i])

        except ValueError as e:
            print(f"错误：在处理第 {i} 项时无法转换时间戳 '{processed_descriptions[i][0]}' 或 '{processed_descriptions[i][1]}' 为数字: {e}. 跳过此项。")
            continue # 跳到下一个循环迭代
        except IndexError:
            print(f"错误：在处理第 {i} 项时索引超出范围。数据：{processed_descriptions[i]}. 跳过此项。")
            continue
    print("descriptions简化之后：\n")
    print(filtered_descriptions)
    # 简化完成

    if filtered_descriptions:
        write_csv(str(output_path), filtered_descriptions, OUTPUT_CSV_HEADER)
    else:
        print("没有成功匹配的描述和间隙数据可写入文件。")

    print("处理完成。")

if __name__=="__main__":
    gen_AD_script(r"D:\Thunder\BloodyBattleTaierzhuang_0419test\BloodyBattleInTaierzhuang_1fps_30min.mp4",
                 r"D:\Thunder\BloodyBattleTaierzhuang_0419test\BloodyBattleInTaierzhuang_1fps_30min.csv",
                 r"D:\Thunder\BloodyBattleTaierzhuang_0419test\BloodyBattleInTaierzhuang_1fps_30min_ADscript.csv")