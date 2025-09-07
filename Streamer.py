import cv2  
import threading  
from flask import Flask, Response  
import datetime
import os
import sounddevice as sd
import soundfile as sf
import wave
import numpy as np


app = Flask(__name__)

class Camera:
    def __init__(self):
        self.cap            = []
        self.cap            += [cv2.VideoCapture(2)] + [cv2.VideoCapture(4)]
        self.fourcc         = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        self.frame          = [None for c in self.cap]
        self.frame_front    = None
        self.frame_rear     = None
        self.WIDTH          = []
        self.HEIGHT         = []
        self.fps            = []
        self.save_folder    = []
        self.WIDTH          += [c.get(cv2.CAP_PROP_FRAME_WIDTH) for c in self.cap]
        self.HEIGHT         += [c.get(cv2.CAP_PROP_FRAME_HEIGHT) for c in self.cap]
        self.fps            += [float(c.get(cv2.CAP_PROP_FPS)) for c in self.cap]  # FPS
        self.boFirst        = True
        self.now            = datetime.datetime.now()
        self.save_folder    += ["front"] + ["rear"] 
        self.video          = []
        self.video          += [cv2.VideoWriter("video_front", self.fourcc, self.fps[i], (int(self.WIDTH[i]),int(self.HEIGHT[i]))) for i in range(len(self.cap))]

        self.audio_device_id    = 12 
        self.audio_info         = sd.query_devices(self.audio_device_id)
        self.samplerate         = int(self.audio_info["default_samplerate"]) 
        self.channels           = self.audio_info["max_input_channels"] 
        self.recording_flag     = True 
        self.audio_frames       = []
        self.AUDIO_FILE         = "output.wav" 

        self.record_time        = 15

        threading.Thread(target=self._update, daemon=True).start()
        threading.Thread(target=self.record_audio, daemon=True).start()

        print(sd.query_devices(self.audio_device_id))

    def record_audio(self):
        """マイク録音スレッド"""
        def callback(indata, frames, time_, status):
            self.audio_frames.append(indata.copy())

        with sd.InputStream(device=self.audio_device_id, samplerate=self.samplerate, channels=self.channels, callback=callback):
            while True:

                if(self.boFirst ):
                    wait = self.record_time - (self.now.second % self.record_time)
                    sd.sleep(int(wait * 1000))
                else:
                    sd.sleep(int(self.record_time * 1000))

                audio_data = np.concatenate(self.audio_frames, axis=0)

                # WAV に保存
                dateday_str = self.now.strftime("%Y-%m-%d")
                save_dir_pos = "recorded/" +"audio" + "/" 
                save_dir_date = save_dir_pos + dateday_str + "/"
                if os.path.isdir(save_dir_date):
                    pass
                elif os.path.isdir(save_dir_pos):
                    os.makedirs(save_dir_date)
                else:
                    os.makedirs(save_dir_pos)
                    os.makedirs(save_dir_date)
                datetime_str = self.now.strftime("%Y-%m-%d %H:%M:%S")
                save_path = save_dir_date + datetime_str + ".wav"
                sf.write(save_path, audio_data, self.samplerate)
                self.audio_frames       = []

    def _timeCtrl(self):
        self.now = datetime.datetime.now()

    def _videoCtrl(self, f, camera_num, save_folder):
        dateday_str = self.now.strftime("%Y-%m-%d")
        save_dir_pos = "recorded/" +save_folder + "/" 
        save_dir_date = save_dir_pos + dateday_str + "/"
        if os.path.isdir(save_dir_date):
            pass
        elif os.path.isdir(save_dir_pos):
            os.makedirs(save_dir_date)
        else:
            os.makedirs(save_dir_pos)
            os.makedirs(save_dir_date)
 
        datetime_str = self.now.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(f, datetime_str, (125, int(self.HEIGHT[camera_num])-10), cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(f, datetime_str, (125, int(self.HEIGHT[camera_num])-10), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2, cv2.LINE_AA)
        save_path = save_dir_date + datetime_str + ".mp4"

        if(self.boFirst ):
            self.video[camera_num]  = cv2.VideoWriter(save_path, self.fourcc, self.fps[camera_num]/len(self.cap), (int(self.WIDTH[camera_num]),int(self.HEIGHT[camera_num])))
            self.boFirst  = False
        elif (self.now.second%self.record_time == 0):
            self.video[camera_num] .release()
            self.video[camera_num]  = cv2.VideoWriter(save_path, self.fourcc, self.fps[camera_num]/len(self.cap), (int(self.WIDTH[camera_num]),int(self.HEIGHT[camera_num])))
        self.video [camera_num].write(f)
        return f

    def _update(self):
        while True:
            ret = []
            f   = []
            for c in self.cap:
                ret += [c.read()[0]]

                f += [c.read()[1]]

            for i in range(len(ret)):
                if ret[i]:
                    self._timeCtrl()
                    f[i] = self._videoCtrl(f[i], i, self.save_folder[i])
                    self.frame[i] = f[i]
            self.frame_front = self.frame[0] 
            self.frame_rear = self.frame[1] 

    def get_frame(self):
        if self.frame_front is None: return None
        _, j = cv2.imencode('.jpg', self.frame_front)
        return j.tobytes()

    def get_frame_rear(self):
        if self.frame_rear is None: return None
        _, j = cv2.imencode('.jpg', self.frame_rear)
        return j.tobytes()

camera = Camera()

def generate_mjpeg():
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def generate_mjpeg_rear():
    while True:
        frame_rear = camera.get_frame_rear()
        if frame_rear:
            yield (b'--frame_rear\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_rear + b'\r\n')


@app.route('/stream')
def stream():
    return Response(generate_mjpeg(),
                    mimetype='multipart/x-mixed-replace; boundary=frame') 


@app.route('/stream_rear')
def stream_rear():
    return Response(generate_mjpeg_rear(),
                    mimetype='multipart/x-mixed-replace; boundary=frame_rear') 

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000,threaded=True)
