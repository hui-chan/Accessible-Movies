import subprocess


def extract_audio_compress_video(video_path,audio_path,compressed_video_path):
    try:
        # Extract audio from video with ffmpeg
        command = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # Disable video recording
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            audio_path
        ]
        subprocess.run(command, check=True, text=True)
        print(f"Audio successfully extracted to: {audio_path}")

        # Compress video with ffmpeg
        video_command = [
            'ffmpeg',
            '-i', video_path,
            '-vf', 'scale=-2:360',
            '-r', '1',
            '-c:v', 'libx264',
            '-crf','28',
            '-c:a', 'libopus',
            '-ac','1',
            '-b:a', '1k',
            compressed_video_path
        ]
        subprocess.run(video_command, check=True, text=True)
        print(f"Video successfully compressed to: {compressed_video_path}")

    except subprocess.CalledProcessError as e:
        print(f"Error processing video: {e.stderr}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")