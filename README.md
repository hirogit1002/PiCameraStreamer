# Camera Streaming & Recording with Flask and OpenCV

USBカメラ1台から映像を取得し、録画しながらFlaskを使ってリアルタイム配信するシステムです。

Raspberry PiなどのLinux環境でのドライブレコーダーや監視カメラシステムを想定しています。

# 主な機能 / Features

- USBカメラ1台から映像を取得
  - Camera: `/dev/video2`
- 映像をMP4形式で録画
- 映像に日時（タイムスタンプ）を表示
- 録画ファイルを15秒ごとに自動分割
- FlaskによるMJPEGリアルタイムストリーミング
- ブラウザからライブ映像を確認可能

# 動作環境 / Requirements

- Python 3.8+
- Linux / Raspberry Pi OS
- USBカメラ 1台
- OpenCV
- Flask

# インストール / Installation

## 1. リポジトリを取得

```bash
git clone https://github.com/yourusername/dual-camera-stream.git
cd dual-camera-stream
```

※ `yourusername` は実際のGitHubユーザー名に変更してください。

## 2. 必要なライブラリをインストール

```bash
pip install flask opencv-python
```

# カメラの確認 / Camera Setup

USBカメラが認識されているか確認します。

```bash
ls /dev/video*
```

初期設定では以下のデバイスを使用します。

| カメラ | デバイス |
|---|---|
| Camera | `/dev/video2` |

カメラのデバイス番号は環境によって異なります。使用するカメラに合わせて、Pythonプログラム内のデバイス番号を変更してください。

# 保存フォルダ / Recording Directory

録画ファイルは以下の構成で保存されます。

```text
recorded/
└── front/
    ├── 20261101_120000.mp4
    ├── 20261101_120015.mp4
    └── ...
```

- `front/`：カメラの録画ファイル
- 録画ファイルは15秒ごとに分割されます。
- ファイル名には録画開始日時が付与されます。

# 起動方法 / Usage

Pythonプログラムを実行します。

```bash
python3 camera_server.py
```

Flaskサーバーが起動したら、ブラウザから以下のURLにアクセスします。

**ライブ映像：**

```text
http://<RaspberryPi-IP>:5000/front
```

`<RaspberryPi-IP>` はRaspberry PiのIPアドレスに置き換えてください。

例：

```text
http://192.168.1.100:5000/front
```

# 注意事項 / Notes

- カメラのデバイス番号は接続環境によって変わる場合があります。
- 録画を長時間続ける場合は、ストレージの空き容量を定期的に確認してください。
- カメラの解像度やフレームレートによってCPU負荷が変わります。
- ブラウザからアクセスする場合、Raspberry Piとアクセス端末が同じネットワークに接続されている必要があります。

# License

This project is available under the MIT License.