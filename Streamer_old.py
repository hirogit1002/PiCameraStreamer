import cv2  
import threading  
from flask import Flask, Response  
import datetime
import os

app = Flask(__name__)

class Camera:
    def __init__(self):
        self.cap = cv2.VideoCapture(2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.frame = None
        self.WIDTH = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.HEIGHT = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS))  # FPS
        self.fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        self.boFirst = True

        threading.Thread(target=self._update, daemon=True).start()

    def _update(self):
        while True:
            ret, f = self.cap.read()
            now = datetime.datetime.now()
            dateday_str = now.strftime("%Y-%m-%d")
            save_dir = "recorded/" + dateday_str + "/"
            if os.path.isdir(save_dir):
                pass
            else:
                os.makedirs(save_dir)
            datetime_str = now.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(f, datetime_str, (125, int(self.HEIGHT)-10), cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(f, datetime_str, (125, int(self.HEIGHT)-10), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2, cv2.LINE_AA)
            save_path = save_dir + datetime_str + ".mp4"

            if(self.boFirst ):
                video = cv2.VideoWriter(save_path, self.fourcc, self.fps, (int(self.WIDTH),int(self.HEIGHT)))
                self.boFirst  = False
            elif (now.second%15 == 0):
                video.release()
                video = cv2.VideoWriter(save_path, self.fourcc, self.fps, (int(self.WIDTH),int(self.HEIGHT)))
            video.write(f)


            if ret:
                self.frame = f

    def get_frame(self):
        if self.frame is None: return None
        _, j = cv2.imencode('.jpg', self.frame)
        return j.tobytes()

camera = Camera()

def generate_mjpeg():
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/stream')
def stream():
    return Response(generate_mjpeg(),
                    mimetype='multipart/x-mixed-replace; boundary=frame') 

if __name__ == "__main__":
	app.run(host='0.0.0.0', port=5000,threaded=True)
