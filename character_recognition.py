import os
import subprocess
import time

import cv2
import insightface
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image, ImageDraw, ImageFont

# --- Global Setup (Model Initialization) ---
# Initialize these once if the script runs continuously or calls the function multiple times.
# If the script only calls the function once and exits, you could move this inside too.
app=None
def get_global_app():
    #global 关键字只在声明它的那个模块内部起作用。 它允许一个函数访问并修改该模块全局作用域中定义的变量。
    #要访问和修改其他模块的全局变量，你需要导入该模块并使用 模块名.变量名 的方式进行操作。
    global app
    if app is None:
        print("Initializing Face Analysis model...")
        try:
            # Prioritize GPU
            app = FaceAnalysis(providers=['CUDAExecutionProvider'])
            app.prepare(ctx_id=0, det_size=(480, 480))
            print("Model initialized successfully using CUDA.")
        except Exception as e:
            print(f"Error initializing model with CUDA: {e}")
            print("Attempting CPU only initialization...")
            try:
                # Fallback to CPU
                app = FaceAnalysis(providers=['CPUExecutionProvider'])
                app.prepare(ctx_id=-1, det_size=(480, 480)) # Use -1 for CPU context
                print("Model initialized successfully using CPU.")
            except Exception as cpu_e:
                print(f"Fatal error initializing model on CPU: {cpu_e}")
                # Set app to None or raise an exception to prevent function execution
                app = None
                # Or raise RuntimeError("Could not initialize FaceAnalysis model.") from cpu_e
    return app


# --- Configuration (Can be changed) ---

SIMILARITY_THRESHOLD = 0.45 # Adjust this threshold as needed


# --- Font Configuration ---
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),"simkai.ttf")# 中文楷体文件路径
FONT_SIZE = 20
TEXT_COLOR = (0, 255, 0)  # green
BOX_COLOR = (0, 255, 0) # green

# try:
#     font_face = freetype.Face(FONT_PATH)
# except freetype.FT_Exception as e:
#     print(f"Error loading font: {e}")
#     exit()

def load_pinyin_mapping(file_path):
    """Load pinyin initials to Chinese names mapping from a file."""
    mapping = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line:
                pinyin, name = line.split(',')
                mapping[pinyin] = name
    return mapping

def merge_video_audio(video_path, audio_path, output_path):
    """
    使用 FFmpeg 将视频和音频合并为一个新的视频文件。

    Args:
        video_path: 视频文件的路径。
        audio_path: 音频文件的路径。
        output_path: 合并后的视频文件的保存路径。
    """
    try:
        # 构建 FFmpeg 命令
        command = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",  # 使用 'copy' 编解码器直接复制视频
            "-c:a","libopus",
            '-ac','1',
            "-b:a","1k",
            "-map", "0:v:0",  # 选择第一个参数的第一个视频流
            "-map", "1:a:0",  # 选择第二个参数的第一个音频流
            "-shortest",       # 以最短的流为准
            output_path
        ]

        # 执行 FFmpeg 命令
        subprocess.run(command, check=True, capture_output=True, text=True)

        print(f"视频和音频已成功合并并保存到：{output_path}")

    except subprocess.CalledProcessError as e:
        print(f"FFmpeg 合并视频和音频时发生错误：")
        print(f"返回码: {e.returncode}")
        print(f"标准输出: {e.stdout}")
        print(f"标准错误: {e.stderr}")
    except FileNotFoundError:
        print("错误: FFmpeg 未找到。请确保已安装 FFmpeg 并将其添加到系统环境变量中。")
    except Exception as e:
        print(f"合并视频和音频时发生未知错误：{e}")


def character_recognition(input_video_path, audio_path,output_video_path,CHARACTER_BANK_PATH):
    """
    Processes an input video file to detect faces, recognize known characters
    based on a character bank, and saves a new video with annotations.

    Args:
        input_video_path (str): Path to the input video file (e.g., .mp4).
        temp_video_path (str): Path where the annotated output video will be saved.

    Returns:
        bool: True if processing completed successfully, False otherwise.
    """
    
    app=get_global_app() # Use the globally initialized model

    if app is None:
        print("Error: FaceAnalysis model is not initialized. Cannot proceed.")
        return False
    
    temp_video_path="temp_no_voice.mp4"
    print("-" * 20)
    print(f"Starting character recognition for: {input_video_path}")
    print(f"Output will be saved to: {temp_video_path}")
    print(f"Using character bank: {CHARACTER_BANK_PATH}")
    print(f"Similarity Threshold: {SIMILARITY_THRESHOLD}")
    print("-" * 20)

    zh_txt_path=os.path.join(CHARACTER_BANK_PATH,"zh.txt")

    # --- Character Bank Loading (Inside Function) ---
    character_feats = {}
    character_names = []
    print("Loading character bank...")
    if not os.path.isdir(CHARACTER_BANK_PATH):
        print(f"Error: Character bank path not found: {CHARACTER_BANK_PATH}")
        return False

    loaded_count = 0
    for file in os.listdir(CHARACTER_BANK_PATH):
        if file.lower().endswith((".png", ".jpg", ".jpeg")):
            character_name_base = os.path.splitext(file)[0]
            character_img_path = os.path.join(CHARACTER_BANK_PATH, file)
            pinyin2name=load_pinyin_mapping(zh_txt_path)
            if character_name_base in pinyin2name:
                character_name=pinyin2name[character_name_base]
            else:
                print(f"Warning: Pinyin '{character_name_base}' not found in zh.txt, using filename as label.")
                character_name = character_name_base

            try:
                character_img = cv2.imread(character_img_path)
                if character_img is None:
                    print(f"Warning: Could not read image file: {character_img_path}")
                    continue

                character_faces = app.get(character_img)

                if character_faces and len(character_faces) == 1:
                    character_feats[character_name] = character_faces[0].normed_embedding
                    character_names.append(character_name)
                    loaded_count += 1
                    # print(f"  Loaded character: {character_name}") # Optional: Verbose loading
                elif not character_faces:
                    print(f"Warning: No face detected in character image: {character_img_path}")
                else:
                    print(f"Warning: Multiple faces ({len(character_faces)}) detected in character image: {character_img_path}. Using the first one.")
                    character_feats[character_name] = character_faces[0].normed_embedding
                    character_names.append(character_name)
                    loaded_count += 1
                    # print(f"  Loaded character (first face): {character_name}") # Optional

            except Exception as e:
                print(f"Error processing character image {character_img_path}: {e}")

    if loaded_count == 0:
        print("Error: No character features loaded from the bank. Cannot proceed.")
        return False
    else:
        print(f"Character bank loaded successfully. {loaded_count} characters found.")


    # --- Video Processing ---
    print(f"Opening video file: {input_video_path}")
    cap = cv2.VideoCapture(input_video_path)

    if not cap.isOpened():
        print(f"Error: Could not open video file: {input_video_path}")
        return False

    # Get video properties for the writer
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps <= 0: # Handle cases where FPS might not be read correctly
        print("Warning: Could not determine video FPS. Defaulting to 3.")
        fps = 3.0

    print(f"Video properties: {frame_width}x{frame_height} @ {fps:.2f} FPS, Total Frames: {total_frames if total_frames > 0 else 'Unknown'}")

    # Define the codec and create VideoWriter object
    # Ensure the output directory exists
    output_dir = os.path.dirname(temp_video_path)
    if output_dir and not os.path.exists(output_dir):
        print(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Codec for .mp4
    out = cv2.VideoWriter(temp_video_path, fourcc, fps, (frame_width, frame_height))

    if not out.isOpened():
         print(f"Error: Could not open VideoWriter for path: {temp_video_path}")
         cap.release()
         return False


    print(f"Processing video and saving to: {temp_video_path}")
    frame_count = 0
    start_time = time.time()
    success = True # Flag to track overall success

    try: # Use try...finally to ensure resources are released
        skip_frames = 2   #为2时， 处理 1 帧，跳过 1 帧 (可以调整这个值)
        last_known_faces = {} # 存储 {face_id: {'bbox': bbox, 'label': label}} 或类似结构 (更复杂的跟踪可能需要)
                                 # 简单实现：存储上一帧所有绘制信息
        previous_boxes_and_labels = []
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("Reached end of video or error reading frame.")
                break

            frame_count += 1
            processed_frame = frame # processed_frame = frame.copy() #Work on a copy to keep original frame clean if needed

            current_boxes_and_labels = [] # 存储当前帧要绘制的信息

            # --- 只在采样帧上进行检测和识别 ---
            if frame_count % skip_frames == 0:
                previous_boxes_and_labels = [] # 清空上一帧的结果，准备更新
                # --- Face Detection and Recognition on the current frame ---
                try:
                    input_faces = app.get(processed_frame) # Use the copy

                    if input_faces:
                        for face in input_faces:
                            feat = face.normed_embedding
                            max_sim = -1
                            best_match = "Unknown"

                            for name, char_feat in character_feats.items():
                                sim = np.dot(feat, char_feat)
                                if sim > max_sim:
                                    max_sim = sim
                                    if sim > SIMILARITY_THRESHOLD:
                                        best_match = name
                                        # --- Bounding Box and Label ---
                                        bbox = face.bbox.astype(int)
                                        label = f"{best_match}"
                                        # 存储当前帧的结果
                                        current_boxes_and_labels.append({'bbox': bbox, 'label': label})
                                        previous_boxes_and_labels.append({'bbox': bbox, 'label': label}) # 更新用于跳过帧的结果
                                    else:
                                        best_match = "Unknown" # Reset if below threshold
                except Exception as e:
                    print(f"Error processing frame {frame_count}: {e}")
                    # 如果处理失败，可以选择也清空上一帧结果，避免错误信息被传播
                    previous_boxes_and_labels = []
                    current_boxes_and_labels = []
            else:
                # --- 对于跳过的帧，使用上一帧的结果 ---
                current_boxes_and_labels = previous_boxes_and_labels

            # --- 统一绘制 ---
            # 无论是否是采样帧，都根据 current_boxes_and_labels 绘制
            for item in current_boxes_and_labels:
                bbox = item['bbox']
                label = item['label']

                # Convert OpenCV image to PIL Image
                pil_image = Image.fromarray(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(pil_image)

                try:
                    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
                except IOError:
                    print(f"Error: Could not load font at {FONT_PATH}. Using default font.")
                    font = ImageFont.load_default()

                text_x = bbox[0]
                text_y = bbox[1] - FONT_SIZE - 5
                if text_y < 0:
                    text_y = bbox[3] + 5

                # processed_frame = draw_text_freetype(processed_frame, label, (text_x, text_y), TEXT_COLOR, font_face, FONT_SIZE)#使用freetype

                # Draw bounding box
                # draw.rectangle([(bbox[0], bbox[1]), (bbox[2], bbox[3])], outline=BOX_COLOR, width=2)#为提升效率，选择每三帧（1s）采样一帧，若后两帧的边框与第一帧一致，会出现与人物面部对不上的情况

                # Draw text with Pillow
                draw.text((text_x, text_y), label, fill=TEXT_COLOR, font=font)

                # Convert PIL Image back to OpenCV image
                processed_frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

            # --- Write the processed frame ---
            out.write(processed_frame)

            # --- Progress Update ---
            if frame_count % 100 == 0: # Update progress less frequently for video
                elapsed_time = time.time() - start_time
                fps_proc = frame_count / elapsed_time if elapsed_time > 0 else 0
                if total_frames > 0:
                    print(f"  Processed frame {frame_count}/{total_frames} ({fps_proc:.2f} FPS)")
                else:
                    print(f"  Processed frame {frame_count} ({fps_proc:.2f} FPS)")
        
        

    except Exception as e:
        print(f"An unexpected error occurred during video processing: {e}")
        success = False # Mark as failed
    finally:
        # --- Cleanup ---
        print("Releasing video resources...")
        cap.release()
        out.release()

        end_time = time.time()
        total_time = end_time - start_time
        avg_fps = frame_count / total_time if total_time > 0 else 0
        print(f"Finished processing video. Processed {frame_count} frames.")
        print(f"Total processing time: {total_time:.2f} seconds")
        print(f"Average processing FPS: {avg_fps:.2f}")
        if success and frame_count > 0:
             print(f"Output video successfully saved to: {temp_video_path}")
        elif frame_count == 0 and success:
             print("Warning: No frames were processed (Input video might be empty or unreadable after opening).")
             success = False # Consider this not fully successful
        else:
             print(f"Video processing failed or encountered errors. Output file might be incomplete or corrupted: {temp_video_path}")
    
    merge_video_audio(temp_video_path,audio_path,output_video_path)
    os.remove(temp_video_path)
    return success