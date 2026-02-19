#!/bin/zsh

# --- 設定（すべてexportで環境変数化）---

# Google Gemini APIキー（TRANSCRIBE_ENGINE=gemini または SUMMARIZE_ENGINE=gemini 使用時に必要）
# ※ セキュリティのため、ここにはキーを書かないでください。
# ※ ~/.zshrc に以下のように設定してください：
#    echo 'export GOOGLE_API_KEY="取得したキー"' >> ~/.zshrc

# --- TODO: Setting ---
# 文字起こしエンジン: "whisper"（ローカル・無料）または "gemini"（API）
# ⚠ 注意: gemini を選択すると音声データがGoogleのサーバーに送信されます。
#   録音内にパスワード・電話番号・口座番号などの個人情報が含まれる場合、情報漏洩のリスクがあります。
#   個人情報を含む音声にはWhisper（ローカル）の使用を推奨します。
export TRANSCRIBE_ENGINE="whisper"

# --- TODO: Setting ---
# 校正エンジン: "none"（スキップ）/ "claude"（Claude CLI・Pro Plan内無料）/ "gemini"（API）
export PROOFREAD_ENGINE="claude"

# --- TODO: Setting ---
# 要約エンジン: "gemini"（API）または "claude"（Claude CLI・Pro Plan内無料）
export SUMMARIZE_ENGINE="claude"

# --- TODO: Setting ---
# Whisperモデル名（TRANSCRIBE_ENGINE=whisper のときのみ使用）
export WHISPER_MODEL="mlx-community/whisper-large-v3-turbo"

# --- TODO: Setting ---
# マスク機能: "true" でLLMに送信する前に機密情報を[MASKED]に置換
# ※ TRANSCRIBE_ENGINE=whisper の場合のみ有効（geminiでは音声が直接送信されるため使用不可）
export ENABLE_MASKING="true"

# --- TODO: Setting ---
# 監視するボイスレコーダーのボリューム名
export RECORDER_NAME="NO NAME"

# --- TODO: Setting ---
# 音声ファイルが格納されているUSBデバイス内のサブディレクトリ名
export VOICE_FILES_SUBDIR="RECORD"

# --- TODO: Setting ---
# 音声ファイルを移動する先のローカルディレクトリ
export AUDIO_DEST_DIR="/Users/m1mac/Desktop/MyVoiceRecoser/audio"

# --- TODO: Setting ---
# Markdown要約ファイルを出力する先のローカルディレクトリ
export MARKDOWN_OUTPUT_DIR="/Users/m1mac/Desktop/MyVoiceRecoser/markdown_output"

# --- TODO: Setting ---
# 実行するPythonスクリプトのパス
export PYTHON_SCRIPT_PATH="./transcribe_summarize.py"

# --- TODO: Setting ---
# 要約時に使用するプロンプトファイルのパス
export SUMMARY_PROMPT_FILE_PATH="../prompt/summary_prompt.txt"

# --- TODO: Setting ---
# 処理済みファイルを記録するJSONLファイルのパス
export PROCESSED_LOG_FILE="../debug/processed_log.jsonl"

# --- TODO: Setting ---
# 処理対象の拡張子 (zsh配列形式で定義)
export TARGET_EXTENSIONS_ARRAY=(-iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a')

# --- TODO: Setting ---
# ステータス管理ファイル
export STATUS_FILE_PATH="/Users/m1mac/Desktop/MyVoiceRecoser/debug/processing_status.jsonl"

# --- TODO: Setting ---
# プロンプトテンプレートファイル
export PROMPT_TEMPLATE_PATH="../prompt/template.txt"

# --- ここまで設定 ---

# 設定値の確認 (デバッグ用)
echo "--- config.sh 設定値 (スクリプト基準での解決前) --- "
echo "TRANSCRIBE_ENGINE: ${TRANSCRIBE_ENGINE}"
echo "PROOFREAD_ENGINE: ${PROOFREAD_ENGINE}"
echo "SUMMARIZE_ENGINE: ${SUMMARIZE_ENGINE}"
echo "WHISPER_MODEL: ${WHISPER_MODEL}"
echo "ENABLE_MASKING: ${ENABLE_MASKING}"
echo "RECORDER_NAME: ${RECORDER_NAME}"
echo "AUDIO_DEST_DIR: ${AUDIO_DEST_DIR}"
echo "MARKDOWN_OUTPUT_DIR: ${MARKDOWN_OUTPUT_DIR}"
echo "PYTHON_SCRIPT_PATH: ${PYTHON_SCRIPT_PATH}"
echo "SUMMARY_PROMPT_FILE_PATH: ${SUMMARY_PROMPT_FILE_PATH}"
echo "PROCESSED_LOG_FILE: ${PROCESSED_LOG_FILE}"
echo "TARGET_EXTENSIONS_ARRAY (各要素):"
for element in "${TARGET_EXTENSIONS_ARRAY[@]}"; do
  echo "  - '$element'"
done
echo "-------------------------"

# 設定内容の確認用 (デバッグ時にコメントを外してください)
# echo "RECORDER_NAME: $RECORDER_NAME"
# echo "AUDIO_DEST_DIR: $AUDIO_DEST_DIR"
# echo "MARKDOWN_OUTPUT_DIR: $MARKDOWN_OUTPUT_DIR"
# echo "PYTHON_SCRIPT_PATH: $PYTHON_SCRIPT_PATH"
# echo "SEARCH_PATTERNS: ${SEARCH_PATTERNS[@]}"
# echo "STATUS_FILE_PATH: $STATUS_FILE_PATH"
# echo "PROMPT_TEMPLATE_PATH: $PROMPT_TEMPLATE_PATH" 