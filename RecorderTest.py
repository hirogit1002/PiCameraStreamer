import cv2
import sounddevice as sd
import numpy as np
import threading
import wave
import subprocess
import time

# 出力ファイル名
VIDEO_FILE = "output.avi"   # 映像のみ一時保存
AUDIO_FILE = "output.wav"   # 音声のみ一時保存
OUTPUT_FILE = "output_final.mp4"  # 映像＋音声

# パラメータ設定
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS = 20
CHANNELS = 1
RATE = 44100

# 音声録音用バッファ
audio_frames = []

def record_audio(duration=None):
    """マイク録音スレッド"""
    def callback(indata, frames, time_, status):
        audio_frames.append(indata.copy())

    with sd.InputStream(samplerate=RATE, channels=CHANNELS, callback=callback):
        if duration:
            sd.sleep(int(duration * 1000))
        else:
            while recording_flag:
                sd.sleep(100)

def save_audio():
    """録音データをwavに保存"""
    wf = wave.open(AUDIO_FILE, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)  # 16bit
    wf.setframerate(RATE)
    wf.writeframes(b''.join([f.tobytes() for f in audio_frames]))
    wf.close()

def merge_audio_video():
    """ffmpegで音声と映像を結合"""
    command = [
        "ffmpeg", "-y",
        "-i", VIDEO_FILE,
        "-i", AUDIO_FILE,
        "-c:v", "copy",
        "-c:a", "aac",
        OUTPUT_FILE
    ]
    subprocess.run(command)

# 録画開始
cap = cv2.VideoCapture(2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, FPS)

fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter(VIDEO_FILE, fourcc, FPS, (FRAME_WIDTH, FRAME_HEIGHT))

recording_flag = True
audio_thread = threading.Thread(target=record_audio)
audio_thread.start()

print("録画開始: qキーで終了")
while True:
    ret, frame = cap.read()
    if not ret:
        break
    out.write(frame)
    cv2.imshow("Recording", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 終了処理
recording_flag = False
audio_thread.join()

cap.release()
out.release()
cv2.destroyAllWindows()

save_audio()
merge_audio_video()

print(f"保存完了: {OUTPUT_FILE}")