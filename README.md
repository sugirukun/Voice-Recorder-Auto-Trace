# AIボイスレコーダー化アプリ (AppLaud)

## 概要

AppLaudは、USBボイスレコーダーをMacに接続した際に、音声ファイルを自動的に取り込み、文字起こしと要約を行うアプリケーションです。生成されたテキストはMarkdownファイルとして保存され、日々の音声記録の管理と活用を効率化します。

## 主な機能

*   **自動ファイル取り込み:** 指定されたUSBボイスレコーダーの接続を検知し、音声ファイル（wav, mp3, m4a）を自動でローカルフォルダに移動します。
*   **AIによる文字起こしと要約:** Gemini APIを利用して、音声ファイルの文字起こしと要約を高精度で行います。
*   **Markdown形式での保存:** 要約結果をMarkdownファイルとして、整理された形式で保存します。ファイル名は録音日時（`YYYY-MM-DD-HH-MM-SS_タイトル.md`）と内容に基づき自動生成されます。
*   **長時間音声対応:** 20分を超える音声ファイルは自動的に分割処理され、APIの制限に対応しつつ、途切れることのない文字起こし結果を得られます。

## システム構成要素

*   **`file_mover.sh` (zshスクリプト):** USBデバイスの監視、音声ファイルの検出と移動、Pythonスクリプトの呼び出しを行います。全ての検出された音声ファイルを毎回必ず移動し、Pythonスクリプトを呼び出します。
*   **`transcribe_summarize.py` (Pythonスクリプト):** Gemini APIとの連携、音声ファイルの文字起こし、要約、Markdownファイル生成、処理記録を行います。
*   **`config.sh` (設定ファイル):** ボイスレコーダーの名称、各種フォルダパス、処理対象の拡張子などを設定します。
*   **`applaud_launcher.sh`:** launchdから呼ばれるラッパースクリプト。多重起動防止・ファイルコピー時の誤トリガー防止・処理完了後のTerminal自動クローズを担います。
*   **`launchd` (macOS):** USBデバイス接続をトリガーとして `applaud_launcher.sh` を経由し `file_mover.sh` を実行します。(ユーザーによる設定が必要です)

## セットアップ

1.  **リポジトリのクローン:**
    ```bash
    git clone https://github.com/your-username/AppLaud.git
    cd AppLaud
    ```
2.  **設定ファイルの編集:**
    *   `script/config.sh` を開き、お使いの環境に合わせて以下の項目を設定してください。
        *   `RECORDER_NAME`: 監視対象のボイスレコーダーのボリューム名 (Macでマウントされたときの名前)。
        *   `VOICE_FILES_SUBDIR`: 音声ファイルが格納されているUSBデバイス内のサブディレクトリ名。ルート直下に保存される機種（ZD46等）は空文字 `""` に設定。
        *   `AUDIO_DEST_DIR`: 音声ファイルの移動先ローカルフォルダ。
        *   `MARKDOWN_OUTPUT_DIR`: Markdown要約ファイルの出力先ローカルフォルダ。
        *   その他、必要に応じてパスを調整してください。
3.  **依存ライブラリのインストール (Python):**
    ```bash
    pip install google-generativeai pydub
    ```
    (Pythonの実行環境によっては `pip3` を使用してください。)
4.  **APIキーの設定（Geminiエンジン使用時のみ必要）:**
    *   [Google AI Studio](https://aistudio.google.com/apikey) でAPIキーを取得してください。
    *   取得したAPIキーを `~/.zshrc` に設定します（GitHubにキーが漏れないよう、config.shには書かないでください）：
        ```bash
        echo 'export GOOGLE_API_KEY="取得したキー"' >> ~/.zshrc
        source ~/.zshrc
        ```
    *   APIキーを削除・再発行した場合は、古いキーを `.zshrc` から削除してから新しいキーを設定してください：
        ```bash
        sed -i '' '/GOOGLE_API_KEY/d' ~/.zshrc
        echo 'export GOOGLE_API_KEY="新しいキー"' >> ~/.zshrc
        source ~/.zshrc
        ```
    *   **注意:** Geminiの無料枠にはリクエスト数・トークン数の制限があります。使用状況は [Google AI Studio Rate Limit](https://aistudio.google.com/rate-limit) で確認できます。
5.  **`launchd` エージェントの設定 (macOSユーザー向け):**
    *   USBデバイス接続時に `file_mover.sh` を自動実行するために、`launchd` のエージェントを設定する必要があります。
    *   本リポジトリの `script/com.example.applaud.filemover.plist` は、このための設定ファイルテンプレートです。
    *   **重要: 設定はすべて `script/config.sh` で一元管理してください。APIキーやパスは `.plist` には直接書かず、`config.sh` にまとめて記述します。**
    *   launchdは直接 `file_mover.sh` を呼ばず、`~/.local/bin/applaud_launcher.sh` を経由します。このラッパーが多重起動防止・誤トリガー防止を担います。
    *   **手順:**
        1.  ラッパースクリプトを配置します。
            ```bash
            mkdir -p ~/.local/bin
            cp script/applaud_launcher.sh ~/.local/bin/  # 内容を環境に合わせて編集
            chmod +x ~/.local/bin/applaud_launcher.sh
            ```
        2.  テンプレートファイルを `~/Library/LaunchAgents/` ディレクトリにコピーします。
            ```bash
            cp script/com.example.applaud.filemover.plist ~/Library/LaunchAgents/
            ```
        3.  コピーした `~/Library/LaunchAgents/com.example.applaud.filemover.plist` をテキストエディタで開き、以下を修正します。
            *   `ProgramArguments`: `applaud_launcher.sh` への絶対パス。
            *   `WatchPaths`: `/Volumes/YOUR_RECORDER_NAME`（ボイスレコーダーのボリューム名）。
            *   ログパス (`StandardOutPath`, `StandardErrorPath`) は必要に応じて変更（デフォルトは `/tmp/` 以下）。
        4.  編集後、`launchd` エージェントを読み込みます。
            ```bash
            launchctl load ~/Library/LaunchAgents/com.example.applaud.filemover.plist
            ```
        5.  これで、指定したUSBデバイスがマウントされると自動的に処理が開始されます。
    *   **動作確認とログ:**
        *   ログは `.plist` ファイル内で指定したパス（デフォルトでは `/tmp/com.example.applaud.filemover.stdout.log` および `stderr.log`）に出力されます。問題が発生した場合はこれらのログファイルを確認してください。
        *   Console.app (`アプリケーション > ユーティリティ > コンソール`) でも `launchd` やスクリプトからのログを確認できる場合があります。
        *   **tailコマンドによるリアルタイム監視例:**
            ```bash
            tail -f /tmp/com.example.applaud.filemover.stdout.log
            tail -f /tmp/com.example.applaud.filemover.stderr.log
            ```
        *   ログファイルの内容をリアルタイムで確認したい場合に便利です。
    *   **アンロード (停止):**
        *   `launchd` エージェントの動作を停止（アンロード）するには、以下のコマンドを実行します。
            ```bash
            launchctl unload ~/Library/LaunchAgents/com.example.applaud.filemover.plist
            ```
        *   アンロード後、再度有効にするには `launchctl load` を実行します。`.plist` ファイルを修正した場合は、アンロードしてからロードし直すことで変更が反映されます。
6.  **動作確認 (任意):**
    *   サンプル音声ファイルを `audio/` ディレクトリに直接置き、以下のコマンドで手動実行できます。
        ```bash
        cd script && python3 transcribe_summarize.py \
          --audio_processing_dir ../audio \
          --markdown_output_dir ../markdown_output \
          --summary_prompt_file_path ../prompt/summary_prompt.txt \
          --processed_log_file_path ../debug/processed_log.jsonl
        ```

## 使い方

1.  上記セットアップを完了します。
2.  設定したボイスレコーダーをMacにUSB接続します。
3.  自動的に処理が開始され、`config.sh` で指定した `MARKDOWN_OUTPUT_DIR` に要約Markdownファイルが生成されます。
4.  処理済みの音声ファイルは `AUDIO_DEST_DIR` に移動されます。
5.  処理のログは `PROCESSED_LOG_FILE` (デフォルト: `debug/processed_log.jsonl`) に記録されます。

## 注意事項

*   本アプリケーションはmacOSでの使用を前提としています。特に `launchd` を利用した自動実行部分はmacOS特有の機能です。
*   APIキーの取り扱いには十分注意してください。環境変数など、安全な方法で管理してください。
*   長時間音声の処理には時間がかかる場合があります。

## オリジナルリポジトリとの違い

本リポジトリは [nyanko3141592/AppLaud](https://github.com/nyanko3141592/AppLaud) のフォークです。以下のカスタマイズを加えています。

### オリジナルの機能

- 文字起こし: Gemini APIのみ
- 要約: Gemini APIのみ
- 校正: なし
- エンジン選択: config.shで固定
- マスク機能: なし
- Markdown出力: 要約のみ
- launchd: スクリプトを直接実行
- Gemini使用時の警告: なし
- 多重起動防止: なし

### このフォークで追加・変更した機能

- 文字起こし: Whisper（ローカル）/ Gemini API / 両方から選択可能
- 要約: Claude CLI / Gemini API から選択可能
- 校正: Claude CLI または Gemini APIによる校正ステップを追加
- エンジン選択: USB接続時にAppleScriptダイアログで都度選択可能（5つの構成プリセット）
- マスク機能: Whisper使用時、LLM送信前に機密情報を[MASKED]に置換
- Markdown出力: 文字起こし・校正済みテキスト・要約の3セクション構成
- launchd: `applaud_launcher.sh` 経由でTerminal.app実行（macOS TCC権限対応）
- Gemini使用時の警告: セキュリティ警告ダイアログを表示（音声の外部送信に関する注意）
- 多重起動防止: ロックファイル＋`/Volumes/`のmtime判定でファイルコピー時の誤トリガーを防止
- 処理完了後にTerminalウィンドウを自動クローズ
- Markdownファイル名: 録音日時（`YYYY-MM-DD-HH-MM-SS`）をファイル名から直接パース

### エンジン選択ダイアログ

USB接続時に以下の5つの構成から選択できます：

1. **おすすめ（追加コストなし）** — Whisper + マスク + Claude校正 + Claude要約（※Claude Proサブスク必要）
2. **全部Gemini** — Gemini文字起こし + Gemini校正 + Gemini要約
3. **Gemini+Claude** — Gemini文字起こし + Claude校正 + Gemini要約
4. **両方で文字起こし** — Whisper & Gemini両方 + Claude校正 + Claude要約
5. **カスタム** — config.shの設定値をそのまま使用

## 今後の改善点 (TODO)

*   Windows/Linuxへの対応。
*   より詳細なエラーハンドリングと通知機能。
*   Web UIによる設定や操作インターフェース。
*   `launchd.plist` の設定を簡略化する補助スクリプトや、より詳細なインストラクションの提供。

詳細は `document/project.md` を参照してください。
