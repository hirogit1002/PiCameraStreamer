import cv2
import threading
import datetime
import time
import sounddevice as sd
import soundfile as sf
import numpy as np
import shutil
import io
import zipfile
import re

from pathlib import Path
from flask import (
    Flask,
    Response,
    send_from_directory,
    render_template_string,
    request,
    abort,
    send_file,
    redirect,
    url_for,
    jsonify
)


# =========================================================
# 設定
# =========================================================

# Frontカメラ
CAMERA_ID = "/dev/video1"

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

# カメラ再接続
CAMERA_RETRY_SECONDS = 3
CAMERA_FAILURE_LIMIT = 10

# 音声再接続
AUDIO_RETRY_SECONDS = 3

# 音声設定
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 1

# Web設定
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000

# ファイル一覧自動更新（秒）
AUTO_REFRESH_SECONDS = 30


# =========================================================
# 音声デバイス検索
# =========================================================

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


# =========================================================
# Cameraクラス
# =========================================================

class Camera:

    def __init__(self):

        self.stop_event = threading.Event()
        self.audio_done = threading.Event()

        self.frame_lock = threading.Lock()
        self.audio_lock = threading.Lock()
        self.active_lock = threading.Lock()

        self.frame = None

        self.audio_buffers = {}

        # 録画中のファイル
        self.active_files = set()

        self.width = 640
        self.height = 480
        self.fps = 20.0

        # セッション開始時刻
        self.start_monotonic = time.monotonic()
        self.start_datetime = datetime.datetime.now()

        # 同一録画区間内のファイル名重複防止
        self.part_numbers = {}

        # 保存フォルダ作成
        FRONT_FOLDER.mkdir(parents=True, exist_ok=True)
        AUDIO_FOLDER.mkdir(parents=True, exist_ok=True)

        # 起動時の古い動画整理
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
                f"IW 2000 USB Audioを使用できません: {e}"
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

        return int(
            elapsed // RECORD_INTERVAL_SECONDS
        )


    def get_segment_datetime(self, segment):

        return self.start_datetime + datetime.timedelta(
            seconds=segment * RECORD_INTERVAL_SECONDS
        )


    def get_segment_filename(self, segment, extension):

        segment_datetime = self.get_segment_datetime(
            segment
        )

        timestamp = segment_datetime.strftime(
            "%Y%m%d_%H%M%S"
        )

        return f"{timestamp}.{extension}"


    # =====================================================
    # 録画中ファイル管理
    # =====================================================

    def add_active_file(self, filepath):

        with self.active_lock:
            self.active_files.add(filepath.name)


    def remove_active_file(self, filepath):

        with self.active_lock:
            self.active_files.discard(filepath.name)


    def is_active_file(self, filename):

        with self.active_lock:
            return filename in self.active_files


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

            if self.is_active_file(old_file.name):
                continue

            try:

                file_size = old_file.stat().st_size

                old_file.unlink()

                total_size -= file_size

                print("Deleted old video:", old_file)

            except Exception as e:

                print("File cleanup error:", e)


    # =====================================================
    # ディスク容量
    # =====================================================

    def get_disk_info(self):

        usage = shutil.disk_usage(
            BASE_FOLDER.resolve()
        )

        return {
            "total": round(
                usage.total / (1024 ** 3), 2
            ),

            "used": round(
                usage.used / (1024 ** 3), 2
            ),

            "free": round(
                usage.free / (1024 ** 3), 2
            ),

            "percent": round(
                usage.used / usage.total * 100, 1
            )
        }


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
        active_video = None

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

                        if active_video is not None:

                            self.remove_active_file(
                                active_video
                            )

                            active_video = None

                        cap.release()
                        cap = None

                        current_segment = None

                        self.stop_event.wait(
                            CAMERA_RETRY_SECONDS
                        )

                    else:

                        self.stop_event.wait(0.05)

                    continue

                failure_count = 0

                height, width = frame.shape[:2]

                self.width = width
                self.height = height

                segment = self.get_segment()

                # 録画区間変更
                if segment != current_segment:

                    if writer is not None:

                        writer.release()
                        writer = None

                        if active_video is not None:

                            self.remove_active_file(
                                active_video
                            )

                            active_video = None

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

                    active_video = filepath

                    self.add_active_file(
                        active_video
                    )

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

            if active_video is not None:

                self.remove_active_file(
                    active_video
                )

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

                        # デバイスIDを再取得
                        try:

                            self.audio_device_id = find_audio_device()

                        except Exception as device_error:

                            print(
                                "Audio device search error:",
                                device_error
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

                filename = self.get_segment_filename(
                    segment,
                    "wav"
                )

                filepath = AUDIO_FOLDER / filename

                self.add_active_file(filepath)

                try:

                    audio_data = np.concatenate(
                        chunks,
                        axis=0
                    )

                    sf.write(
                        str(filepath),
                        audio_data,
                        AUDIO_SAMPLE_RATE,
                        subtype="PCM_16"
                    )

                    print("Saved audio:", filepath)

                except Exception as e:

                    print("Audio save error:", e)

                finally:

                    self.remove_active_file(filepath)

            if self.audio_done.is_set():

                with self.audio_lock:

                    if not self.audio_buffers:
                        break

            time.sleep(0.2)

        print("Audio writer stopped.")


    # =====================================================
    # 保存ファイル一覧
    # =====================================================

    def get_recorded_files(self, selected_date=None):

        result = {
            "front": [],
            "audio": []
        }

        folders = {
            "front": FRONT_FOLDER,
            "audio": AUDIO_FOLDER
        }

        for category, folder in folders.items():

            if category == "front":
                extension = ".mp4"
            else:
                extension = ".wav"

            files = sorted(
                folder.glob(f"*{extension}"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            for file in files:

                if not file.is_file():
                    continue

                # 録画中ファイルを除外
                if self.is_active_file(file.name):
                    continue

                # 日付検索
                if selected_date:

                    if not file.name.startswith(
                        selected_date.replace("-", "").replace("_", "") + "_"
                    ):
                        continue

                try:

                    stat = file.stat()

                    size_mb = stat.st_size / (
                        1024 * 1024
                    )

                    result[category].append({

                        "name": file.name,

                        "size": round(size_mb, 2),

                        "date": datetime.datetime.fromtimestamp(
                            stat.st_mtime
                        ).strftime("%Y-%m-%d %H:%M:%S")

                    })

                except OSError:

                    continue

        return result


    # =====================================================
    # ファイル削除
    # =====================================================

    def delete_file(self, category, filename):

        folders = {
            "front": FRONT_FOLDER,
            "audio": AUDIO_FOLDER
        }

        if category not in folders:
            return False

        if Path(filename).name != filename:
            return False

        folder = folders[category]

        if category == "front":

            if not filename.lower().endswith(".mp4"):
                return False

        else:

            if not filename.lower().endswith(".wav"):
                return False

        if self.is_active_file(filename):
            return False

        filepath = folder / filename

        try:

            if not filepath.is_file():
                return False

            filepath.unlink()

            print("Deleted file:", filepath)

            return True

        except Exception as e:

            print("Delete error:", e)

            return False


    # =====================================================
    # 日付指定一括削除
    # =====================================================

    def delete_date_files(self, selected_date):

        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            selected_date
        ):
            return 0

        date_prefix = selected_date.replace("-", "") + "_"

        deleted_count = 0

        for category, folder in [
            ("front", FRONT_FOLDER),
            ("audio", AUDIO_FOLDER)
        ]:

            extension = ".mp4" if category == "front" else ".wav"

            files = folder.glob(f"*{extension}")

            for file in files:

                if not file.name.startswith(date_prefix):
                    continue

                if self.delete_file(
                    category,
                    file.name
                ):
                    deleted_count += 1

        return deleted_count


    # =====================================================
    # ZIP一括ダウンロード
    # =====================================================

    def create_daily_zip(self, selected_date):

        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            selected_date
        ):
            return None

        date_prefix = selected_date.replace("-", "") + "_"

        memory_file = io.BytesIO()

        file_count = 0

        with zipfile.ZipFile(
            memory_file,
            "w",
            compression=zipfile.ZIP_DEFLATED
        ) as zip_file:

            for category, folder in [
                ("front", FRONT_FOLDER),
                ("audio", AUDIO_FOLDER)
            ]:

                extension = ".mp4" if category == "front" else ".wav"

                files = sorted(folder.glob(f"*{extension}"))

                for file in files:

                    if not file.name.startswith(date_prefix):
                        continue

                    if self.is_active_file(file.name):
                        continue

                    try:

                        if not file.is_file():
                            continue

                        zip_file.write(
                            file,
                            arcname=f"{category}/{file.name}"
                        )

                        file_count += 1

                    except Exception as e:

                        print("ZIP file error:", e)

        if file_count == 0:
            return None

        memory_file.seek(0)

        return memory_file


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


# =========================================================
# トップページ
# =========================================================

@app.route("/")
def index():

    return """
    <!DOCTYPE html>
    <html>

    <head>

        <meta charset="UTF-8">

        <title>Front Camera</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                text-align: center;
                background: #f4f4f4;
                margin: 20px;
            }

            h2 {
                color: #333;
            }

            img {
                width: 100%;
                max-width: 640px;
                height: auto;
                border: 2px solid #333;
            }

            button {
                padding: 14px 25px;
                font-size: 18px;
                background: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }

            button:hover {
                background: #0b7dda;
            }

        </style>

    </head>

    <body>

        <h2>Front Camera</h2>

        <img src="/stream">

        <br><br>

        <a href="/files">
            <button>
                Recording Files / Download
            </button>
        </a>

    </body>

    </html>
    """


# =========================================================
# カメラ映像配信
# =========================================================

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


@app.route("/stream")
def stream():

    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# =========================================================
# ファイル一覧ページ
# =========================================================

@app.route("/files")
def files():

    selected_date = request.args.get("date", "")

    if selected_date:

        try:
            datetime.date.fromisoformat(selected_date)

        except ValueError:
            abort(400)

    recorded_files = camera.get_recorded_files(
        selected_date if selected_date else None
    )

    disk = camera.get_disk_info()

    html = """

    <!DOCTYPE html>
    <html>

    <head>

        <meta charset="UTF-8">

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>Recording Files</title>

        {% if auto_refresh %}
        <meta http-equiv="refresh"
              content="{{ refresh_seconds }}">
        {% endif %}

        <style>

            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                background: #f4f4f4;
                color: #333;
            }

            h1 {
                margin-bottom: 20px;
            }

            h2 {
                margin-top: 35px;
                border-bottom: 2px solid #555;
                padding-bottom: 8px;
            }

            .panel {
                background: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 8px;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
            }

            th, td {
                padding: 12px 8px;
                border-bottom: 1px solid #ddd;
                text-align: left;
                word-break: break-word;
            }

            th {
                background: #333;
                color: white;
            }

            tr:hover {
                background: #f1f1f1;
            }

            .button {
                display: inline-block;
                padding: 9px 14px;
                border: none;
                border-radius: 5px;
                color: white;
                text-decoration: none;
                cursor: pointer;
                font-size: 14px;
                margin: 3px;
            }

            .download {
                background: #2196F3;
            }

            .delete {
                background: #e53935;
            }

            .zip {
                background: #4CAF50;
                font-size: 17px;
                padding: 12px 20px;
            }

            .back {
                background: #555;
            }

            input[type=date] {
                padding: 10px;
                font-size: 16px;
            }

            .progress {
                width: 100%;
                height: 20px;
                background: #ddd;
                border-radius: 10px;
                overflow: hidden;
            }

            .progress-bar {
                height: 100%;
                background: #4CAF50;
            }

            .info {
                font-size: 17px;
                line-height: 1.8;
            }

            .count {
                color: #666;
                font-size: 14px;
            }

            .empty {
                padding: 20px;
                text-align: center;
                color: #888;
                background: white;
            }

            @media(max-width: 650px) {

                body {
                    margin: 8px;
                }

                th, td {
                    padding: 8px 4px;
                    font-size: 12px;
                }

                .button {
                    padding: 7px;
                    font-size: 12px;
                }

            }

        </style>

    </head>

    <body>

        <h1>Recording Files</h1>

        <a class="button back" href="/">
            Back to Camera
        </a>


        <!-- ディスク容量 -->

        <div class="panel">

            <h2>Disk Usage</h2>

            <div class="info">

                Total: {{ disk.total }} GB<br>

                Used: {{ disk.used }} GB<br>

                Free: {{ disk.free }} GB<br>

                Usage: {{ disk.percent }} %

            </div>

            <div class="progress">

                <div class="progress-bar"
                     style="width: {{ disk.percent }}%">
                </div>

            </div>

        </div>


        <!-- 日付検索 -->

        <div class="panel">

            <h2>Date Search</h2>

            <form method="GET" action="/files">

                <input
                    type="date"
                    name="date"
                    value="{{ selected_date }}"
                    required
                >

                <button class="button download"
                        type="submit">

                    Search

                </button>

                <a class="button back" href="/files">

                    Show All

                </a>

            </form>

        </div>


        <!-- ZIP -->

        {% if selected_date %}

        <div class="panel">

            <h2>Daily ZIP Download</h2>

            <p>
                Selected date: {{ selected_date }}
            </p>

            <a class="button zip"
               href="{{ url_for('download_zip', selected_date=selected_date) }}">

                Download All as ZIP

            </a>

            <br><br>

            <form
                method="POST"
                action="{{ url_for('delete_date', selected_date=selected_date) }}"
                onsubmit="return confirm('この日の動画・音声をすべて削除しますか？');"
            >

                <button class="button delete"
                        type="submit">

                    Delete All Files of This Date

                </button>

            </form>

        </div>

        {% endif %}


        <!-- 動画 -->

        <h2>Front Videos</h2>

        <p class="count">
            {{ videos|length }} files
        </p>

        {% if videos %}

        <table>

            <tr>

                <th>Filename</th>
                <th>Date</th>
                <th>Size</th>
                <th>Download</th>
                <th>Delete</th>

            </tr>

            {% for file in videos %}

            <tr>

                <td>{{ file.name }}</td>

                <td>{{ file.date }}</td>

                <td>{{ file.size }} MB</td>

                <td>

                    <a class="button download"
                       href="{{ url_for('download_file', category='front', filename=file.name) }}">

                        Download

                    </a>

                </td>

                <td>

                    <form
                        method="POST"
                        action="{{ url_for('delete_file', category='front', filename=file.name) }}"
                        onsubmit="return confirm('この動画を削除しますか？');"
                    >

                        <button class="button delete"
                                type="submit">

                            Delete

                        </button>

                    </form>

                </td>

            </tr>

            {% endfor %}

        </table>

        {% else %}

        <div class="empty">
            No video files found.
        </div>

        {% endif %}


        <!-- 音声 -->

        <h2>Audio Files</h2>

        <p class="count">
            {{ audio|length }} files
        </p>

        {% if audio %}

        <table>

            <tr>

                <th>Filename</th>
                <th>Date</th>
                <th>Size</th>
                <th>Download</th>
                <th>Delete</th>

            </tr>

            {% for file in audio %}

            <tr>

                <td>{{ file.name }}</td>

                <td>{{ file.date }}</td>

                <td>{{ file.size }} MB</td>

                <td>

                    <a class="button download"
                       href="{{ url_for('download_file', category='audio', filename=file.name) }}">

                        Download

                    </a>

                </td>

                <td>

                    <form
                        method="POST"
                        action="{{ url_for('delete_file', category='audio', filename=file.name) }}"
                        onsubmit="return confirm('この音声を削除しますか？');"
                    >

                        <button class="button delete"
                                type="submit">

                            Delete

                        </button>

                    </form>

                </td>

            </tr>

            {% endfor %}

        </table>

        {% else %}

        <div class="empty">
            No audio files found.
        </div>

        {% endif %}


        <br><br>

        <p>
            Auto refresh: {{ refresh_seconds }} seconds
        </p>

    </body>

    </html>

    """

    return render_template_string(
        html,

        videos=recorded_files["front"],

        audio=recorded_files["audio"],

        disk=disk,

        selected_date=selected_date,

        refresh_seconds=AUTO_REFRESH_SECONDS,

        auto_refresh=True
    )


# =========================================================
# 個別ダウンロード
# =========================================================

@app.route("/download/<category>/<filename>")
def download_file(category, filename):

    folders = {
        "front": FRONT_FOLDER,
        "audio": AUDIO_FOLDER
    }

    if category not in folders:
        abort(404)

    if Path(filename).name != filename:
        abort(404)

    if category == "front":

        if not filename.lower().endswith(".mp4"):
            abort(404)

    elif category == "audio":

        if not filename.lower().endswith(".wav"):
            abort(404)

    # 録画中ファイルはダウンロード禁止
    if camera.is_active_file(filename):
        abort(409, "File is currently being recorded.")

    return send_from_directory(
        str(folders[category]),
        filename,
        as_attachment=True
    )


# =========================================================
# ZIP一括ダウンロード
# =========================================================

@app.route("/download_zip/<selected_date>")
def download_zip(selected_date):

    try:

        datetime.date.fromisoformat(
            selected_date
        )

    except ValueError:

        abort(400)

    memory_file = camera.create_daily_zip(
        selected_date
    )

    if memory_file is None:

        return "No completed recording files found.", 404

    filename = (
        f"recording_{selected_date}.zip"
    )

    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename
    )


# =========================================================
# 個別削除
# =========================================================

@app.route(
    "/delete/<category>/<filename>",
    methods=["POST"]
)
def delete_file(category, filename):

    success = camera.delete_file(
        category,
        filename
    )

    if not success:

        abort(409, "File could not be deleted.")

    return redirect(
        url_for("files")
    )


# =========================================================
# 日付指定一括削除
# =========================================================

@app.route(
    "/delete_date/<selected_date>",
    methods=["POST"]
)
def delete_date(selected_date):

    try:

        datetime.date.fromisoformat(
            selected_date
        )

    except ValueError:

        abort(400)

    deleted_count = camera.delete_date_files(
        selected_date
    )

    print(
        f"Deleted {deleted_count} files for {selected_date}"
    )

    return redirect(
        url_for("files")
    )


# =========================================================
# ディスク情報API
# =========================================================

@app.route("/api/storage")
def storage_api():

    return jsonify(
        camera.get_disk_info()
    )


# =========================================================
# 終了処理
# =========================================================

import atexit

atexit.register(camera.stop)


# =========================================================
# 起動
# =========================================================

if __name__ == "__main__":

    try:

        print("")
        print("===================================")
        print(" Raspberry Pi Camera Recorder")
        print("===================================")

        print(
            f"Camera URL: http://<RaspberryPi-IP>:{WEB_PORT}/"
        )

        print(
            f"Files URL:  http://<RaspberryPi-IP>:{WEB_PORT}/files"
        )

        print("===================================")

        app.run(
            host=WEB_HOST,
            port=WEB_PORT,
            threaded=True,
            use_reloader=False
        )

    except KeyboardInterrupt:

        print("Keyboard interrupt received.")

    finally:

        camera.stop()