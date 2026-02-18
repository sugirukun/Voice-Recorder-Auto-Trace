#!/bin/zsh

# file_mover.sh
#
# USBデバイスがマウントされた際に呼び出され、音声ファイルを処理するスクリプト。
#
# 処理内容:
# 1. 設定ファイルを読み込む。
# 2. マウントされたUSBデバイスのパスを引数として受け取る。
# 3. デバイス内の音声ファイルを検索する。
# 4. ファイルを指定ディレクトリに移動する。
# 5. Pythonスクリプトを呼び出して文字起こしと要約を行う。

echo "引数: $@"

# --- 柔軟な引数パース（--configとマウントパスの順不同対応） ---
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONFIG_FILE="${SCRIPT_DIR}/config.sh"
MOUNTED_DEVICE_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            if [[ -n "$2" ]]; then
                CONFIG_FILE="$2"
                shift 2
            else
                echo "エラー: --config オプションの後にパスが必要です" >&2
                exit 1
            fi
            ;;
        *)
            if [[ -z "$MOUNTED_DEVICE_PATH" ]]; then
                MOUNTED_DEVICE_PATH="$1"
            fi
            shift
            ;;
    esac
done

if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
    echo "設定ファイルを読み込みました: $CONFIG_FILE"
else
    echo "エラー: 設定ファイルが見つかりません: $CONFIG_FILE" >&2
    exit 1
fi

if [ -z "$MOUNTED_DEVICE_PATH" ]; then
    echo "エラー: マウントされたUSBデバイスのパスが指定されていません。" >&2
    echo "使用法: $0 <マウントパス> [--config <設定ファイル>]" >&2
    exit 1
fi

echo "マウントパス: $MOUNTED_DEVICE_PATH"

# --- 検索対象パスの決定 ---
SEARCH_PATH="$MOUNTED_DEVICE_PATH"
if [ -n "$VOICE_FILES_SUBDIR" ]; then
    SEARCH_PATH="${MOUNTED_DEVICE_PATH}/${VOICE_FILES_SUBDIR}"
fi
echo "検索対象パス: $SEARCH_PATH"

# --- マウントポイントの準備待機 ---
echo "マウントポイント準備待機中: $SEARCH_PATH"
RETRY_COUNT=0
MAX_RETRIES=30 # 最大30秒待機
while [ ! -d "$SEARCH_PATH" ]; do
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "エラー: $SEARCH_PATH が $MAX_RETRIES 秒以内に利用可能になりませんでした。"
        exit 1
    fi
    sleep 1
    RETRY_COUNT=$((RETRY_COUNT + 1))
done
echo "$SEARCH_PATH 準備完了。"

# --- ディレクトリ作成 ---
mkdir -p "${AUDIO_DEST_DIR}"
echo "音声ファイル保存先ディレクトリを確認/作成しました: ${AUDIO_DEST_DIR}"
mkdir -p "${MARKDOWN_OUTPUT_DIR}"
echo "Markdown出力先ディレクトリを確認/作成しました: ${MARKDOWN_OUTPUT_DIR}"
LOG_FILE_DIR=$(dirname "${PROCESSED_LOG_FILE}")
if [ ! -d "$LOG_FILE_DIR" ]; then
    mkdir -p "$LOG_FILE_DIR"
    echo "ログファイル用ディレクトリを作成しました: $LOG_FILE_DIR"
fi
touch "${PROCESSED_LOG_FILE}"
echo "処理済み記録ファイルを確認/作成しました: ${PROCESSED_LOG_FILE}"

AUDIO_DONE_DIR="${AUDIO_DEST_DIR}/done"
mkdir -p "${AUDIO_DONE_DIR}"
echo "完了ファイル保存先ディレクトリを確認/作成しました: ${AUDIO_DONE_DIR}"

# --- 音声ファイルの検索 ---
echo "指定されたパスから音声ファイルを検索します: $SEARCH_PATH"
echo "検索拡張子 (配列): ${TARGET_EXTENSIONS_ARRAY[@]}"

echo "findコマンド実行前に5秒待機します..."
sleep 5

find_args=("$SEARCH_PATH")

echo "実行するfindコマンドのパス部分: $find_args[1]"
print -lr -- "実行するfindコマンドの述語部分 (TARGET_EXTENSIONS_ARRAY):" "${TARGET_EXTENSIONS_ARRAY[@]}"

AUDIO_FILES=()
find_stderr_output=""
find_output_stdout=$(find "$find_args[1]" -type f \
    \( "${TARGET_EXTENSIONS_ARRAY[@]}" \) \
    -not -name '._*' \
    -print0 2> >(find_stderr_output=$(cat); echo "$find_stderr_output" >&2) )
find_exit_code=$?

echo "Find command exit code: $find_exit_code"

if [ $find_exit_code -ne 0 ]; then
    echo "エラー: findコマンドの実行に失敗しました。終了コード: $find_exit_code。パス: $find_args[1]" >&2
    if [ -n "$find_stderr_output" ] && [[ "$find_stderr_output" != *"Permission denied"* ]] && [[ "$find_stderr_output" != *"Operation not permitted"* ]]; then
        echo "Find command stderr: $find_stderr_output" >&2
    fi
    if [ ! -d "$find_args[1]" ]; then
        echo "エラー: 検索対象ディレクトリが存在しません: $find_args[1]" >&2
    fi
    exit 1
fi

if [ -n "$find_output_stdout" ]; then
  while IFS= read -r -d $'\0' file; do
      if [ -n "$file" ]; then
          AUDIO_FILES+=("$file")
      fi
  done <<< "$find_output_stdout"
else
  echo "findコマンドの標準出力は空でした（対象ファイルなし、またはエラー）。"
fi

echo "検出された音声ファイル (AUDIO_FILES配列):"
for f in "${AUDIO_FILES[@]}"; do echo "  - $f"; done

echo "検出された音声ファイル数: ${#AUDIO_FILES[@]}"

# --- ファイルごとの処理ループ ---
echo "\n処理を開始します..."

for audio_file_full_path in "${AUDIO_FILES[@]}"; do
    audio_file_name=$(basename "$audio_file_full_path")
    echo "\n--------------------------------------------------"
    echo "処理対象ファイル: $audio_file_full_path ($audio_file_name)"

    # --- ファイルの移動 ---
    destination_path="${AUDIO_DEST_DIR}/${audio_file_name}"
    echo "ファイルを移動します: $audio_file_full_path -> $destination_path"
    mv -f "$audio_file_full_path" "$destination_path"
    if [ $? -ne 0 ]; then
        echo "エラー: ファイルの移動に失敗しました: $audio_file_full_path" >&2
        # 移動失敗時もPythonスクリプトは呼び出されるため、ここではexitしない
    else
        echo "ファイルの移動に成功しました。"
    fi
done # 個別ファイル移動ループの終了

# --- エンジン選択ダイアログ (AppleScript) ---
echo "エンジン選択ダイアログを表示します..."

ENGINE_CHOICE=$(osascript <<'APPLESCRIPT'
set choiceList to {"おすすめ（追加コストなし ※Claude Proサブスク必要）— Whisper + マスク + Claude校正 + Claude要約", "全部Gemini — Gemini文字起こし + Gemini校正 + Gemini要約（⚠音声は外部送信）", "Gemini+Claude — Gemini文字起こし + Claude校正 + Gemini要約（⚠音声は外部送信）", "両方で文字起こし — Whisper&Gemini + Claude校正 + Claude要約（⚠音声は外部送信）", "カスタム — config.sh の設定をそのまま使用"}
set userChoice to choose from list choiceList ¬
    with title "MyVoiceRecoser - エンジン選択" ¬
    with prompt "文字起こし・要約の構成を選択してください：" ¬
    default items {item 1 of choiceList}
if userChoice is false then
    return "cancelled"
end if
return item 1 of userChoice
APPLESCRIPT
)

osascript_exit_code=$?
echo "ダイアログ選択結果: ${ENGINE_CHOICE} (終了コード: ${osascript_exit_code})"

if [ $osascript_exit_code -ne 0 ] || [ "$ENGINE_CHOICE" = "cancelled" ]; then
    echo "ダイアログがキャンセルされました。処理を中止します。"
    exit 0
fi

# Gemini使用時の警告ダイアログ（共通関数）
show_gemini_warning() {
    local confirm_result
    confirm_result=$(osascript <<'APPLESCRIPT'
display dialog "⚠ 注意: Gemini APIを使用すると、音声データがGoogleのサーバーに送信されます。

録音内にパスワード・電話番号・口座番号などの個人情報が含まれる場合、情報漏洩のリスクがあります。

続行しますか？" ¬
    with title "Gemini API - セキュリティ警告" ¬
    buttons {"キャンセル", "続行"} ¬
    default button "キャンセル" ¬
    with icon caution
APPLESCRIPT
)
    local confirm_exit=$?
    if [ $confirm_exit -ne 0 ] || [ "$confirm_result" = "キャンセル" ]; then
        echo "Gemini API の使用がキャンセルされました。処理を中止します。"
        exit 0
    fi
    echo "Gemini API の使用が確認されました。"
}

case "$ENGINE_CHOICE" in
    おすすめ*)
        echo "構成: おすすめ（追加コストなし）を選択"
        export TRANSCRIBE_ENGINE="whisper"
        export ENABLE_MASKING="true"
        export PROOFREAD_ENGINE="claude"
        export SUMMARIZE_ENGINE="claude"
        ;;
    全部Gemini*)
        echo "構成: 全部Gemini を選択 — 警告ダイアログを表示します"
        show_gemini_warning
        export TRANSCRIBE_ENGINE="gemini"
        export ENABLE_MASKING="false"
        export PROOFREAD_ENGINE="gemini"
        export SUMMARIZE_ENGINE="gemini"
        ;;
    Gemini+Claude*)
        echo "構成: Gemini+Claude を選択 — 警告ダイアログを表示します"
        show_gemini_warning
        export TRANSCRIBE_ENGINE="gemini"
        export ENABLE_MASKING="false"
        export PROOFREAD_ENGINE="claude"
        export SUMMARIZE_ENGINE="gemini"
        ;;
    両方で文字起こし*)
        echo "構成: 両方で文字起こし を選択 — 警告ダイアログを表示します"
        show_gemini_warning
        export TRANSCRIBE_ENGINE="both"
        export ENABLE_MASKING="true"
        export PROOFREAD_ENGINE="claude"
        export SUMMARIZE_ENGINE="claude"
        ;;
    カスタム*)
        echo "構成: カスタム（config.sh の設定値をそのまま使用）"
        ;;
esac

echo "--- 適用されるエンジン設定 ---"
echo "TRANSCRIBE_ENGINE: ${TRANSCRIBE_ENGINE}"
echo "PROOFREAD_ENGINE: ${PROOFREAD_ENGINE}"
echo "SUMMARIZE_ENGINE: ${SUMMARIZE_ENGINE}"
echo "ENABLE_MASKING: ${ENABLE_MASKING}"
echo "-----------------------------"

# --- Pythonスクリプトの呼び出し (AUDIO_DEST_DIR を対象とする) ---
# 個別ファイルごとではなく、一度だけ呼び出すように変更
# AUDIO_FILES 配列の要素数に関わらず、常にPythonスクリプトを呼び出す
abs_python_script_path="$(cd "${SCRIPT_DIR}" && realpath "${PYTHON_SCRIPT_PATH}")"
abs_summary_prompt_file_path="$(cd "${SCRIPT_DIR}" && realpath "${SUMMARY_PROMPT_FILE_PATH}")"
abs_processed_log_file_path="$(cd "${SCRIPT_DIR}" && realpath "${PROCESSED_LOG_FILE}")"
abs_markdown_output_dir="$(cd "${SCRIPT_DIR}" && realpath "${MARKDOWN_OUTPUT_DIR}")"
abs_audio_dest_dir_for_python="$(cd "${SCRIPT_DIR}" && realpath "${AUDIO_DEST_DIR}")"

echo "Pythonスクリプトを呼び出します: $abs_python_script_path (対象ディレクトリ: $abs_audio_dest_dir_for_python)"
python3 "$abs_python_script_path" \
    --audio_processing_dir "$abs_audio_dest_dir_for_python" \
    --markdown_output_dir "$abs_markdown_output_dir" \
    --summary_prompt_file_path "$abs_summary_prompt_file_path" \
    --processed_log_file_path "$abs_processed_log_file_path"

python_exit_code=$?
if [ $python_exit_code -eq 0 ]; then
    echo "Pythonスクリプトの実行に成功しました。"
else
    echo "エラー: Pythonスクリプトの実行に失敗しました。(終了コード: $python_exit_code)" >&2
fi

echo "\n全ての処理が完了しました。"
exit 0 