# Dual Camera Streaming & Recording with Flask and OpenCV

This project captures video from **two USB cameras** (e.g., front and rear),  
records them to disk, and serves live video streams via a **Flask MJPEG server**.  

It is designed for use cases such as dashcams, surveillance, or any dual-camera recording system.

---

## ✨ Features

- Capture from two cameras (`/dev/video2` and `/dev/video4` by default)  
- Record video as `.mp4` files, organized by date and camera type (`front` / `rear`)  
- Timestamp overlay on each frame  
- Auto-segmentation of recordings every **15 seconds**  
- Live MJPEG streaming via Flask web server  
- Separate endpoints for front and rear camera feeds  

---

## 📦 Requirements

- Python 3.8+
- OpenCV (cv2)
- Flask

Install dependencies:

```bash
pip install flask opencv-python
```

# Dual Camera Streaming & Recording with Flask + OpenCV

このプロジェクトは、複数のUSBカメラ（例: 前方・後方）から映像を取得し、  
Flaskを用いてMJPEGストリーミング配信を行いながら録画を保存するシステムです。

---

## 📌 機能

- 前方カメラ（例: `/dev/video2`）、後方カメラ（例: `/dev/video4`）から映像を取得  
- OpenCVを使用して録画（mp4形式、日時入り）  
- Flaskを利用したリアルタイムMJPEGストリーミング配信  
- 保存先は `recorded/front/` および `recorded/rear/` フォルダに日付ごとに自動作成  
- 録画ファイルは 15 秒ごとに自動分割  

---

## 🚀 セットアップ

### 1. 必要環境

- Python 3.8+
- USBカメラ 2台
- Flask
- OpenCV (cv2)

### 2. インストール

```bash
git clone https://github.com/yourusername/dual-camera-stream.git
cd dual-camera-stream

# 必要ライブラリをインストール
pip install -r requirements.txt
```