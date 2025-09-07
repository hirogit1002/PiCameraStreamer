import gphoto2 as gp
import cv2
import numpy as np

camera = gp.Camera()
camera.init()

# ライブビュー開始
camera.capture_preview()
while True:
    # プレビュー画像を取得
    camera_file = camera.capture_preview()
    file_data = camera_file.get_data_and_size()
    
    # OpenCV で処理できる形式に変換
    nparr = np.frombuffer(file_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is not None:
        cv2.imshow("LiveView", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
camera.exit()
