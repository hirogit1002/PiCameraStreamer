# Camera Streaming & Recording with Flask and OpenCV

USBカメラとUSBマイクから映像・音声を取得し、1分ごとに自動で録画・保存しながら、Flaskを使ってリアルタイム配信するシステムです。録画ファイルはブラウザから一覧表示・ダウンロード・削除できます。

Raspberry PiなどのLinux環境でのドライブレコーダーや監視カメラシステムを想定しています。

# 主な機能 / Features

- USBカメラ（Front）から映像を取得
  - 初期設定: `/dev/video1`
- 映像をMP4形式（mp4v）で録画し、映像に日時（タイムスタンプ）を表示
- USB音声デバイス（`IW 2000`）から音声を録音し、WAV形式（16bit PCM, 48kHz, モノラル）で保存
- 録画・録音ファイルを60秒ごとに自動分割（映像と音声は同じ区間・同じ名前で保存）
- 動画フォルダの容量上限（初期設定 2.5GB）を超えると、古い動画から自動削除
- FlaskによるMJPEGリアルタイムストリーミング
- ブラウザからライブ映像を確認可能
- 録画ファイル管理ページ
  - 動画・音声ファイルの一覧表示（録画中のファイルは除外）
  - 個別ダウンロード / 個別削除
  - 日付検索
  - 日付指定のZIP一括ダウンロード
  - 日付指定の一括削除
  - ディスク使用量の表示（30秒ごとに自動更新）
- カメラ・音声デバイスが切断されても自動で再接続
- 終了時に録画・録音を安全に停止して保存

# 動作環境 / Requirements

- Python 3.8+
- Linux / Raspberry Pi OS
- USBカメラ 1台
- USB音声入力デバイス（デバイス名に `IW 2000` を含むもの）
- 必要なライブラリ
  - OpenCV
  - Flask
  - sounddevice
  - soundfile
  - NumPy

# インストール / Installation

## 1. リポジトリを取得

```bash
git clone https://github.com/yourusername/dual-camera-stream.git
cd dual-camera-stream
```

※ `yourusername` は実際のGitHubユーザー名に変更してください。

## 2. 必要なパッケージをインストール

sounddevice / soundfile はシステムライブラリに依存するため、先にインストールします（Raspberry Pi OS / Debian系）。

```bash
sudo apt install libportaudio2 libsndfile1
```

次にPythonライブラリをインストールします。

```bash
pip install flask opencv-python sounddevice soundfile numpy
```

# デバイスの確認 / Device Setup

## カメラ

USBカメラが認識されているか確認します。

```bash
ls /dev/video*
```

初期設定では以下のデバイスを使用します。

| デバイス | 設定値 |
|---|---|
| Frontカメラ | `/dev/video1` |

カメラのデバイス番号は環境によって異なります。使用するカメラに合わせて、プログラム内の `CAMERA_ID` を変更してください。

## 音声デバイス

認識されている音声入力デバイスを確認します。

```bash
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

プログラムは、入力チャンネルを持ち、名前に `IW 2000` を含むデバイスを自動的に探して使用します。別のデバイスを使う場合は、`find_audio_device()` 内の `"IW 2000"` を使用するデバイス名に変更してください。

デバイスが見つからない場合、プログラムは起動時にエラーで終了します。

# 設定 / Configuration

`Streamer.py` 先頭の設定項目を変更することで動作を調整できます。

| 設定項目 | 初期値 | 説明 |
|---|---|---|
| `CAMERA_ID` | `/dev/video1` | カメラのデバイス |
| `RECORD_INTERVAL_SECONDS` | `60` | ファイル分割間隔（秒） |
| `MAX_FOLDER_SIZE_GB` | `2.5` | 動画フォルダの最大容量（GB） |
| `CAMERA_RETRY_SECONDS` | `3` | カメラ再接続の待機時間（秒） |
| `CAMERA_FAILURE_LIMIT` | `10` | 再接続を行う連続フレーム取得失敗回数 |
| `AUDIO_RETRY_SECONDS` | `3` | 音声デバイス再接続の待機時間（秒） |
| `AUDIO_SAMPLE_RATE` | `48000` | 音声サンプリングレート（Hz） |
| `AUDIO_CHANNELS` | `1` | 音声チャンネル数 |
| `WEB_HOST` | `0.0.0.0` | Webサーバーのホスト |
| `WEB_PORT` | `5000` | Webサーバーのポート |
| `AUTO_REFRESH_SECONDS` | `30` | ファイル一覧の自動更新間隔（秒） |

# 保存フォルダ / Recording Directory

録画ファイルは以下の構成で保存されます。

```text
recorded/
├── front/
│   ├── 20261101_120000.mp4
│   ├── 20261101_120100.mp4
│   └── ...
└── audio/
    ├── 20261101_120000.wav
    ├── 20261101_120100.wav
    └── ...
```

- `front/`：カメラの録画ファイル（MP4）
- `audio/`：音声の録音ファイル（WAV）
- 録画・録音ファイルは60秒ごとに分割されます。
- ファイル名には録画区間の開始日時（`YYYYMMDD_HHMMSS`）が付与されます。
- カメラ再接続などで同じ区間内にファイルが複数できる場合、`_part001` のような連番が付きます。
- 容量制限による自動削除の対象は動画（`front/`）のみです。音声ファイルは自動削除されないため、ストレージの空き容量に注意してください。

# 起動方法 / Usage

Pythonプログラムを実行します。

```bash
python3 Streamer.py
```

Flaskサーバーが起動したら、ブラウザから以下のURLにアクセスします。

| ページ | URL |
|---|---|
| ライブ映像 | `http://<RaspberryPi-IP>:5000/` |
| 録画ファイル管理 | `http://<RaspberryPi-IP>:5000/files` |

`<RaspberryPi-IP>` はRaspberry PiのIPアドレスに置き換えてください。

例：

```text
http://192.168.1.100:5000/
```

# Webインターフェース / Web Interface

## ルート一覧

| パス | メソッド | 説明 |
|---|---|---|
| `/` | GET | ライブ映像ページ |
| `/stream` | GET | MJPEGストリーム |
| `/files` | GET | 録画ファイル一覧（`?date=YYYY-MM-DD` で日付検索） |
| `/download/<category>/<filename>` | GET | 個別ダウンロード（`category` は `front` または `audio`） |
| `/download_zip/<YYYY-MM-DD>` | GET | 指定日の動画・音声をZIPで一括ダウンロード |
| `/delete/<category>/<filename>` | POST | 個別削除 |
| `/delete_date/<YYYY-MM-DD>` | POST | 指定日のファイルを一括削除 |
| `/api/storage` | GET | ディスク使用量をJSONで返す |

## 録画ファイル管理ページ

- ディスクの合計・使用量・空き容量・使用率を表示します。
- 日付で検索すると、その日のファイルだけを表示します。
- 日付検索中は「ZIP一括ダウンロード」と「その日のファイルを全削除」が利用できます。
- 録画中・保存中のファイルは一覧に表示されず、ダウンロードや削除もできません。

# 注意事項 / Notes

- カメラのデバイス番号は接続環境によって変わる場合があります。
- 音声デバイス名（`IW 2000`）が一致しない場合、起動できません。
- 録画を長時間続ける場合は、特に音声ファイルが自動削除されない点に注意し、ストレージの空き容量を定期的に確認してください。
- カメラの解像度やフレームレートによってCPU負荷が変わります。
- 認証機能はありません。ブラウザからアクセスする場合、Raspberry Piとアクセス端末が同じネットワークに接続されている必要があります。インターネットに公開しないでください。
- ZIPダウンロード時は、一時ファイルが `recorded/` 直下に作成され、ダウンロード完了後に削除されます。

# License

This project is available under the MIT License.
