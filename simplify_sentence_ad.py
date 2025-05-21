import re
from collections import deque

import jieba
import jieba.posseg as pseg
import numpy as np
import torch  # sentence-transformers 通常需要 torch 或 tensorflow
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model_name='shibing624/text2vec-base-chinese'
sentence_model=None
def get_global_model():
    global sentence_model
    if sentence_model is None:
        try:            
            print("\nInitializing sentence model...\n")
            # 尝试自动选择设备 (GPU if available, else CPU)
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            sentence_model = SentenceTransformer(model_name, device=device)
            print(f"Using device: {device}")
        except Exception as e:
            print(f"Error loading Sentence Transformer sentence_model '{model_name}': {e}")
            print("Falling back to basic truncation.")
            sentence_model=None# 如果模型加载失败，可以回退到之前的 safe_truncate 或简单截断
    return sentence_model
    

# --- Helper function from previous version (slightly modified) ---
def split_clauses_v2(text):
    """按标点分句，标点符号归属于前面的子句。"""
    clauses = []
    last_idx = 0
    # 匹配常见的结束性或分隔性标点, 增加对换行符的处理
    # (?<=[...]) 是正向后行断言, 确保标点前有字符
    # | \n+ 匹配一个或多个换行符作为分隔
    pattern = r'(?<=[，,。;；！!？?、])(?![」』])|(?<=[」』])|\n+'
    for match in re.finditer(pattern, text):
        end_pos = match.end()
        clause = text[last_idx:end_pos].strip() # 去除子句前后空格
        if clause: # 避免添加空子句
            clauses.append(clause)
        last_idx = end_pos
    # 添加最后一个标点或换行符后的剩余部分（如果存在）
    if last_idx < len(text):
        remaining = text[last_idx:].strip()
        if remaining:
            clauses.append(remaining)
    
    return clauses 


# --- Advanced NLP Shortening Function ---

def shorten_sentence(text, max_len):
    """
    使用句子嵌入进行抽取式摘要来缩短句子。

    Args:
        text (str): 输入文本。
        max_len (int): 最大目标长度。

    Returns:
        str: 缩短后的文本。
    """
    # 0. 预处理和长度检查
    text = re.sub(r'\s+', '', text).strip()
    text = re.sub(r'[a-zA-Z0-9]+', '', text).strip()#出去字母和数字，因为tts无法正常读取字母和数字。
    text = text.replace("字", "")
    
    last_char = text[-1]
    chinese_punctuation = r'[，。、？！；‘’“”【】（）《》]'
    chinese_period = "。"
    if re.match(chinese_punctuation, last_char):
        if last_char != chinese_period:
            text= text[:-1] + chinese_period
    else:
        text=text + chinese_period
    # 使用正则表达式匹配中文字符
    chinese_characters = re.findall(r'[\u4e00-\u9fa5]', text)
    if len(chinese_characters) <= max_len:
        return text

    # 1. 加载模型 (如果需要多次调用，建议在外部加载模型)
    sentence_model=get_global_model()
    if sentence_model is None:
        return safe_truncate_v2(text, max_len) # 复用之前的安全截断
    
    # 2. 分割成子句
    clauses = split_clauses_v2(text)
    if not clauses:
        # 如果无法分割，直接截断
        return safe_truncate_v2(text, max_len)
    if len(clauses) == 1:
         # 如果只有一个子句（无法有效分割），也直接截断
         return safe_truncate_v2(text, max_len)

    # 3. 计算子句嵌入
    # 使用 show_progress_bar=True 可以看到编码进度
    embeddings = sentence_model.encode(clauses, convert_to_numpy=True, show_progress_bar=False)

    # 4. 计算句子（或文本段落）的中心嵌入 (所有子句嵌入的平均值)
    centroid_embedding = np.mean(embeddings, axis=0)

    # 5. 计算每个子句与中心嵌入的相似度 (作为重要性分数)
    similarities = cosine_similarity(embeddings, centroid_embedding.reshape(1, -1))
    # similarities 是一个 N x 1 的矩阵，将其展平成一维数组
    scores = similarities.flatten()

    # 6. 选择最重要的子句，直到达到长度限制
    selected_indices = []
    current_length = 0
    # 按原始顺序存储选中的子句，方便最后组合
    result_clauses_map = {}

    # 将分数和原始索引配对，按分数从高到低排序
    indexed_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    # 优先选择分数高的子句，但要保证不超过长度，并尽量保持原顺序
    selected_indices_set = set() # 记录已选择的索引，避免重复计算长度
    temp_result_clauses = [None] * len(clauses) # 按原顺序占位

    for index, score in indexed_scores:
        clause_text = clauses[index]
        clause_len = len(re.findall(r'[\u4e00-\u9fa5]', clause_text))#只计算中文字符的长度

        # 检查加入这个子句是否会超长
        if current_length + clause_len <= max_len:
            # 只有当这个索引还没被最终选定时才加入
            if index not in selected_indices_set:
                 temp_result_clauses[index] = clause_text # 放入正确的位置
                 current_length += clause_len
                 selected_indices_set.add(index)

    # 7. 按原始顺序组合选出的子句
    final_clauses = [clause for clause in temp_result_clauses if clause is not None]
    shortened_text = "".join(final_clauses)

    # 8. 后处理和返回
    # 如果结果为空或太短，可能需要回退策略
    if not shortened_text or len(shortened_text) < 0.3 * max_len: # 设置一个最小长度阈值，例如30%
        # print("Embedding selection result too short, falling back to truncation.")
        # 回退到安全截断可能更稳妥
        return safe_truncate_v2(text, max_len)

    # 如果缩短后的文本末尾不是结束性标点，且原文本有，可以尝试添加一个
    # (这个逻辑比较复杂，暂时省略，避免引入错误)

    last_char_=shortened_text[-1]
    if re.match(chinese_punctuation, last_char_):
        if last_char_ != chinese_period:
            shortened_text= shortened_text[:-1] + chinese_period
    else:
        shortened_text=shortened_text + chinese_period
    return shortened_text.strip()


# --- 复用之前的 safe_truncate_v2 ---
def safe_truncate_v2(text, max_len):
    """三重保障安全截断 V2 (逻辑类似，可微调)"""
    search_end = max(0, max_len - 10)
    prefix=""
    for i in range(len(text)-1, search_end -1, -1):
        if len(re.findall(r'[\u4e00-\u9fa5]', text[:i+1])) <= max_len:
            prefix=text[:i+1]
            break

    # 优先在 max_len 附近寻找完整句子结束标点
    sentence_end_chars = '。！？!?…'
    best_cut = -1
    for i in range(len(prefix)-1, search_end -1, -1):
        if  text[i] in sentence_end_chars: # 边界检查
            best_cut = i + 1
            break
    if best_cut != -1:
        return text[:best_cut]

    # 第二层：在 max_len 附近寻找常用分隔标点
    split_chars = '，；,;'
    best_split_cut = -1
    for i in range(len(prefix) - 1, search_end -1, -1):
         if text[i] in split_chars: # 边界检查
            best_split_cut = i + 1 # 保留该标点
            break
    if best_split_cut != -1:
       return text[:best_split_cut-1]+"。"

    # 第三层：尝试在词语边界截断 (在 max_len 内)
    try:
        words = list(jieba.cut(prefix, cut_all=False))
        if len(words) > 1:
            truncated_by_word = ''.join(words[:-1])#-1 是切片的结束索引。在列表（或字符串）中，负数索引表示从末尾开始计数，-1 代表最后一个元素，-2 代表倒数第二个元素，以此类推。结束索引不包含该索引对应的元素。
            if len(truncated_by_word) >= max_len * 0.8:
                 # 简单返回去掉最后一个词的结果
                 return truncated_by_word.strip()+"。" # 去掉末尾可能多余的空格
    except Exception:
        # jieba分词可能出错，忽略此步骤
        pass

    # 第四层：硬截断 (最终保底)
    return prefix+"。"


# # --- 测试验证 ---
# test_cases = [
#     ("首先是祭拜王铭章师长的场景，战士们肃立，气氛庄严。镜头扫过挽联和花圈。然后，高级将领在军旗下祭拜后讲话，神情悲痛。之后，战士们将一把短剑扔入运河，象征着为国捐躯的决心。最后，两个军人走在古老的城墙之上，讨论战事。", 89),
#     ("由于近期市场波动较大，公司决定调整原本在第三季度进行的战略投资计划，具体安排将另行通知。", 40),
#     ("虽然当前经济形势复杂多变，但经过管理层多次讨论研究，我们仍决定按原计划推进新产品的研发工作。", 50),
#     ("重要通知：明日将进行系统升级维护，届时服务将中断2小时。", 25),
#     ("这是一个非常非常长但是没有什么实际分隔符的句子用来测试当split_clauses_v2无法有效分割时的情况看看会发生什么。", 30) # 测试无法分割的情况
# ]

# print("\n--- Advanced NLP (Embeddings) Version Test ---")
# # 注意：第一次运行会下载模型，可能需要一些时间
# for text, length in test_cases:
#     print(f"原句 ({len(text)}字): {text}")
#     result = shorten_sentence(text, length)
#     print(f"精简后 ({len(result)}字): {result}\n")