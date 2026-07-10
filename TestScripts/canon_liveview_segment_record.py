import os
import time
from datetime import datetime
import cv2
import numpy as np
import gphoto2 as gp

WIDTH=1024
HEIGHT=768
FPS=30
SEGMENT_SECONDS=15
SAVE_DIR="Movie"
os.makedirs(SAVE_DIR, exist_ok=True)

camera=gp.Camera()
camera.init()
camera.capture_preview()

def current_segment_start(ts=None):
    if ts is None: ts=time.time()
    return int(ts//SEGMENT_SECONDS)*SEGMENT_SECONDS

def writer_for(segstart):
    dt=datetime.fromtimestamp(segstart)
    name=dt.strftime("%Y%m%d_%H%M%S")+".mp4"
    path=os.path.join(SAVE_DIR,name)
    fourcc=cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(path,fourcc,FPS,(WIDTH,HEIGHT)), segstart

seg=current_segment_start()
video,seg=writer_for(seg)

try:
    while True:
        cf=camera.capture_preview()
        data=cf.get_data_and_size()
        frame=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        if frame is None:
            continue
        frame=cv2.resize(frame,(WIDTH,HEIGHT))
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        font=cv2.FONT_HERSHEY_SIMPLEX
        (tw,th),bl=cv2.getTextSize(now,font,0.8,2)
        x=(WIDTH-tw)//2
        y=HEIGHT-20
        cv2.rectangle(frame,(x-10,y-th-10),(x+tw+10,y+bl+5),(0,0,0),-1)
        cv2.putText(frame,now,(x,y),font,0.8,(255,255,255),2,cv2.LINE_AA)
        cv2.circle(frame,(25,30),8,(0,0,255),-1)
        cv2.putText(frame,"REC",(40,36),font,0.8,(0,0,255),2)
        newseg=current_segment_start()
        if newseg!=seg:
            video.release()
            video,seg=writer_for(newseg)
        video.write(frame)
        cv2.imshow("Canon LiveView",frame)
        if cv2.waitKey(1)&0xFF==ord("q"):
            break
finally:
    video.release()
    cv2.destroyAllWindows()
    camera.exit()
