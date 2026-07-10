import gphoto2 as gp
import cv2
import numpy as np
from datetime import datetime

# ----------------------------
# カメラ初期化
# ----------------------------
camera = gp.Camera()
camera.init()

# ライブビュー開始
camera.capture_preview()

# ----------------------------
# 動画設定
# ----------------------------
WIDTH = 1024
HEIGHT = 768
FPS = 30

filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4"

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
video = cv2.VideoWriter(
    filename,
    fourcc,
    FPS,
    (WIDTH, HEIGHT)
)

print(f"録画開始: {filename}")

while True:

    # プレビュー取得
    camera_file = camera.capture_preview()
    file_data = camera_file.get_data_and_size()

    nparr = np.frombuffer(file_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        continue

    frame = cv2.resize(frame, (WIDTH, HEIGHT))

    # ----------------------------
    # 現在日時
    # ----------------------------
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.8
    thickness = 2

    (tw, th), baseline = cv2.getTextSize(
        now,
        font,
        scale,
        thickness
    )

    x = (WIDTH - tw) // 2
    y = HEIGHT - 20

    # 黒背景
    cv2.rectangle(
        frame,
        (x - 10, y - th - 10),
        (x + tw + 10, y + baseline + 5),
        (0, 0, 0),
        -1
    )

    # 白文字
    cv2.putText(
        frame,
        now,
        (x, y),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA
    )

    # ----------------------------
    # REC表示
    # ----------------------------
    cv2.circle(frame, (25, 30), 8, (0, 0, 255), -1)

    cv2.putText(
        frame,
        "REC",
        (40, 36),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2
    )

    # 表示
    cv2.imshow("Canon LiveView", frame)

    # 録画
    video.write(frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break

video.release()
cv2.destroyAllWindows()
camera.exit()

print("録画終了")
print("保存先:", filename)