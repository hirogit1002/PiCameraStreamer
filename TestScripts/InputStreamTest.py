import sounddevice as sd
import soundfile as sf
import numpy as np

device_id = 12  # B525 HD Webcam マイク
duration = 5   # 録音時間（秒）

# デバイス情報
info = sd.query_devices(device_id)
samplerate = int(info["default_samplerate"])
channels = info["max_input_channels"]

print(f"Recording from {info['name']} at {samplerate} Hz, {channels} channel(s)")

# バッファ用リスト
recorded_frames = []

# コールバック関数
def callback(indata, frames, time, status):
    if status:
        print("Status:", status)
    recorded_frames.append(indata.copy())  # データをコピーして保存

# InputStream を開く
with sd.InputStream(device=device_id,
                    samplerate=samplerate,
                    channels=channels,
                    callback=callback):
    print("Recording...")
    sd.sleep(int(duration * 1000))  # ミリ秒単位で待機
    print("Recording finished.")

# リストを NumPy 配列に変換
audio_data = np.concatenate(recorded_frames, axis=0)

# WAV に保存
sf.write("recorded_inputstream.wav", audio_data, samplerate)
print("Saved to recorded_inputstream.wav")