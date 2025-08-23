import sounddevice as sd
import soundfile as sf

# 録音設定
samplerate = 48000  # サンプリング周波数
duration = 5        # 秒数
device_id = 4       # マイク入力のデバイス番号に変更してください

print(sd.query_devices(device_id))  # 例: device_id=9 の場合

print("Recording...")
audio = sd.rec(int(samplerate * duration), samplerate=samplerate, channels=1, device=device_id)
sd.wait()
print("Recording finished.")

# 保存
sf.write("test_record.wav", audio, samplerate)
print("Saved to test_record.wav") 
