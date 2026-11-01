import cv2
import threading
import datetime
import time
import signal
import atexit
import sounddevice as sd
import soundfile as sf
import numpy as np

from pathlib import Path
from flask import Flask, Response


# =========================================================
# 設定
# =========================================================

# Frontカメラ：IW 2000（/dev/video1）
CAMERA_ID = "/dev/video1"

# USBオーディオデバイス
def find_audio_device():

    devices = sd.query_devices()

    for i, device in enumerate(devices):

        name = device["name"]
        channels = device["max_input_channels"]

        if channels > 0 and "IW 2000" in name:

            print(f"Audio device found: {i} - {name}")

            return i

    raise RuntimeError(
        "IW 2000 USB Audio input device not found."
    )

# 録画時間（秒）
RECORD_INTERVAL_SECONDS = 60

# Front動画フォルダの最大容量
MAX_FOLDER_SIZE_GB = 2.5
MAX_FOLDER_SIZE = int(MAX_FOLDER_SIZE_GB * 1024 ** 3)

# 保存先
BASE_FOLDER = Path("recorded")
FRONT_FOLDER = BASE_FOLDER / "front"
AUDIO_FOLDER = BASE_FOLDER / "audio"

# 動画形式
FOURCC = cv2.VideoWriter_fourcc(*"mp4v")

# カメラ再接続設定
CAMERA_RETRY_SECONDS = 3
CAMERA_FAILURE_LIMIT = 10

# 音声再接続設定
AUDIO_RETRY_SECONDS = 3

# 音声設定
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 1


# =========================================================
# カメラ・録画クラス
# =========================================================

class Camera:

    def __init__(self):

        self.stop_event = threading.Event()
        self.audio_done = threading.Event()

        self.frame_lock = threading.Lock()
        self.audio_lock = threading.Lock()

        self.frame = None

        self.audio_buffers = {}

        self.width = 640
        self.height = 480
        self.fps = 20.0

        # セッション開始時刻
        self.start_monotonic = time.monotonic()
        self.start_datetime = datetime.datetime.now()

        # 同じ録画区間内でのファイル名重複防止
        self.part_numbers = {}

        # 保存フォルダ作成
        FRONT_FOLDER.mkdir(parents=True, exist_ok=True)
        AUDIO_FOLDER.mkdir(parents=True, exist_ok=True)

        # 起動時に古い動画を整理
        self.cleanup_old_files()

        # 音声デバイス確認
        try:
            self.audio_device_id = find_audio_device()

            device_info = sd.query_devices(
                self.audio_device_id,
                "input"
            )

            print("Audio device:", device_info["name"])

        except Exception as e:
            raise RuntimeError(
                f"音声デバイス {AUDIO_DEVICE_ID} を使用できません: {e}"
            )

        # スレッド起動
        self.threads = []

        self.camera_thread = threading.Thread(
            target=self.camera_worker,
            daemon=True
        )

        self.audio_thread = threading.Thread(
            target=self.record_audio,
            daemon=True
        )

        self.audio_writer_thread = threading.Thread(
            target=self.audio_writer,
            daemon=True
        )

        self.threads.extend([
            self.camera_thread,
            self.audio_thread,
            self.audio_writer_thread
        ])

        for thread in self.threads:
            thread.start()

        print("Front camera recording started.")


    # =====================================================
    # 録画区間管理
    # =====================================================

    def get_segment(self):

        elapsed = time.monotonic() - self.start_monotonic

        return int(elapsed // RECORD_INTERVAL_SECONDS)


    def get_segment_datetime(self, segment):

        return self.start_datetime + datetime.timedelta(
            seconds=segment * RECORD_INTERVAL_SECONDS
        )


    def get_segment_filename(self, segment, extension):

        segment_datetime = self.get_segment_datetime(segment)

        timestamp = segment_datetime.strftime("%Y%m%d_%H%M%S")

        return f"{timestamp}.{extension}"


    # =====================================================
    # 動画フォルダ容量管理
    # =====================================================

    def cleanup_old_files(self):

        files = sorted(
            FRONT_FOLDER.glob("*.mp4"),
            key=lambda f: f.stat().st_mtime
        )

        total_size = sum(
            f.stat().st_size for f in files
        )

        while total_size > MAX_FOLDER_SIZE and files:

            old_file = files.pop(0)

            try:
                file_size = old_file.stat().st_size
                old_file.unlink()

                total_size -= file_size

                print("Deleted old video:", old_file)

            except Exception as e:
                print("File cleanup error:", e)


    # =====================================================
    # カメラ接続
    # =====================================================

    def open_camera(self):

        print(f"Opening Front camera: {CAMERA_ID}")

        cap = cv2.VideoCapture(
            CAMERA_ID,
            cv2.CAP_V4L2
        )

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():

            print("Front camera open failed.")

            cap.release()

            return None

        fps = cap.get(cv2.CAP_PROP_FPS)

        if fps <= 0:
            fps = 20.0

        self.fps = fps

        print(
            f"Front camera opened: "
            f"{self.width}x{self.height}, {self.fps}fps"
        )

        return cap


    # =====================================================
    # カメラ録画処理
    # =====================================================

    def camera_worker(self):

        cap = None
        writer = None

        current_segment = None
        failure_count = 0

        try:

            while not self.stop_event.is_set():

                # カメラ未接続なら再接続
                if cap is None:

                    cap = self.open_camera()

                    if cap is None:

                        self.stop_event.wait(
                            CAMERA_RETRY_SECONDS
                        )

                        continue

                    failure_count = 0

                ret, frame = cap.read()

                # フレーム取得失敗
                if not ret:

                    failure_count += 1

                    print(
                        f"Camera read failed: "
                        f"{failure_count}/{CAMERA_FAILURE_LIMIT}"
                    )

                    if failure_count >= CAMERA_FAILURE_LIMIT:

                        print("Reconnecting Front camera.")

                        if writer is not None:
                            writer.release()
                            writer = None

                        cap.release()
                        cap = None

                        current_segment = None

                        self.stop_event.wait(
                            CAMERA_RETRY_SECONDS
                        )

                    continue

                failure_count = 0

                height, width = frame.shape[:2]

                self.width = width
                self.height = height

                segment = self.get_segment()

                # 録画区間が変わった場合
                if segment != current_segment:

                    if writer is not None:

                        writer.release()
                        writer = None

                        print("Video segment closed.")

                        self.cleanup_old_files()

                    current_segment = segment

                # 動画ファイル作成
                if writer is None:

                    part_number = self.part_numbers.get(
                        segment,
                        0
                    )

                    filename = self.get_segment_filename(
                        segment,
                        "mp4"
                    )

                    stem = Path(filename).stem

                    if part_number > 0:
                        filename = (
                            f"{stem}_part{part_number:03d}.mp4"
                        )

                    else:
                        filename = f"{stem}.mp4"

                    self.part_numbers[segment] = (
                        part_number + 1
                    )

                    filepath = FRONT_FOLDER / filename

                    writer = cv2.VideoWriter(
                        str(filepath),
                        FOURCC,
                        self.fps,
                        (width, height)
                    )

                    if not writer.isOpened():

                        print(
                            "VideoWriter open failed:",
                            filepath
                        )

                        writer.release()
                        writer = None

                        self.stop_event.wait(1)

                        continue

                    print("Recording video:", filepath)

                # 時刻表示
                now = datetime.datetime.now()

                timestamp = now.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                cv2.putText(
                    frame,
                    timestamp,
                    (10, height - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA
                )

                # 動画保存
                writer.write(frame)

                # Web配信用フレーム更新
                with self.frame_lock:
                    self.frame = frame.copy()

        finally:

            if writer is not None:
                writer.release()

            if cap is not None:
                cap.release()

            print("Front camera stopped.")


    # =====================================================
    # 音声録音
    # =====================================================

    def record_audio(self):

        try:

            while not self.stop_event.is_set():

                try:

                    def audio_callback(
                        indata,
                        frames,
                        time_info,
                        status
                    ):

                        if status:
                            print("Audio status:", status)

                        segment = self.get_segment()

                        audio_data = indata.copy()

                        with self.audio_lock:

                            if segment not in self.audio_buffers:
                                self.audio_buffers[segment] = []

                            self.audio_buffers[segment].append(
                                audio_data
                            )


                    with sd.InputStream(
                        device=self.audio_device_id,
                        channels=AUDIO_CHANNELS,
                        samplerate=AUDIO_SAMPLE_RATE,
                        dtype="int16",
                        callback=audio_callback
                    ):

                        print("Audio recording started.")

                        while not self.stop_event.is_set():

                            time.sleep(0.2)

                except Exception as e:

                    print("Audio recording error:", e)

                    if not self.stop_event.is_set():

                        self.stop_event.wait(
                            AUDIO_RETRY_SECONDS
                        )

        finally:

            self.audio_done.set()

            print("Audio recording stopped.")


    # =====================================================
    # 音声ファイル保存
    # =====================================================

    def audio_writer(self):

        while True:

            current_segment = self.get_segment()

            with self.audio_lock:

                segments = list(
                    self.audio_buffers.keys()
                )

                ready_segments = [
                    segment
                    for segment in segments
                    if (
                        segment < current_segment
                        or self.audio_done.is_set()
                    )
                ]

                audio_data_list = {}

                for segment in ready_segments:

                    audio_data_list[segment] = (
                        self.audio_buffers.pop(segment)
                    )

            # 保存処理
            for segment, chunks in audio_data_list.items():

                if not chunks:
                    continue

                try:

                    audio_data = np.concatenate(
                        chunks,
                        axis=0
                    )

                    filename = self.get_segment_filename(
                        segment,
                        "wav"
                    )

                    filepath = AUDIO_FOLDER / filename

                    sf.write(
                        str(filepath),
                        audio_data,
                        AUDIO_SAMPLE_RATE,
                        subtype="PCM_16"
                    )

                    print("Saved audio:", filepath)

                except Exception as e:

                    print("Audio save error:", e)

            if self.audio_done.is_set():

                with self.audio_lock:

                    if not self.audio_buffers:
                        break

            time.sleep(0.2)

        print("Audio writer stopped.")


    # =====================================================
    # Web配信用画像
    # =====================================================

    def get_frame(self):

        with self.frame_lock:

            if self.frame is None:
                return None

            ret, buffer = cv2.imencode(
                ".jpg",
                self.frame
            )

            if not ret:
                return None

            return buffer.tobytes()


    # =====================================================
    # 停止処理
    # =====================================================

    def stop(self):

        if self.stop_event.is_set():
            return

        print("Stopping recorder...")

        self.stop_event.set()

        for thread in self.threads:

            if thread.is_alive():

                thread.join(timeout=10)

        print("Recorder stopped.")


# =========================================================
# Flask
# =========================================================

app = Flask(__name__)

camera = Camera()


def generate_frames():

    while not camera.stop_event.is_set():

        frame = camera.get_frame()

        if frame is None:

            time.sleep(0.1)

            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame
            + b"\r\n"
        )

        time.sleep(0.03)


@app.route("/")
def index():

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Front Camera Stream</title>
    </head>

    <body>
        <h2>Front Camera</h2>

        <img
            src="/stream"
            width="640"
            height="480"
        >

    </body>
    </html>
    """


@app.route("/stream")
def stream():

    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# =========================================================
# 終了処理
# =========================================================

def shutdown_handler(signum=None, frame=None):

    atexit.register(camera.stop)


# =========================================================
# 起動
# =========================================================

if __name__ == "__main__":

    try:

        app.run(
            host="0.0.0.0",
            port=5000,
            threaded=True,
            use_reloader=False
        )

    except KeyboardInterrupt:

        print("Keyboard interrupt received.")

    finally:

        camera.stop()