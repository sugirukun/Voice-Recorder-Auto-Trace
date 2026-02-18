import argparse
import datetime
import json
import os
import pathlib
import shutil
import re
import subprocess
import sys

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

# Constants
CHUNK_MAX_DURATION_MS = 20 * 60 * 1000  # 20 minutes in milliseconds
OVERLAP_MS = 1 * 60 * 1000  # 1 minute in milliseconds
MAX_FILENAME_LENGTH = 50  # Max length for the AI generated part of the filename


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

def mask_sensitive_info(text):
    """正規表現で機密情報を [MASKED] に置換する。"""
    masked = text

    # メールアドレス
    masked = re.sub(r'\S+@\S+\.\S+', '[MASKED]', masked)

    # クレジットカード番号（4桁×4）
    masked = re.sub(r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}', '[MASKED]', masked)

    # 電話番号（日本の一般的なパターン）
    masked = re.sub(r'0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}', '[MASKED]', masked)

    # セキュリティコード（キーワード＋3〜4桁数字）
    masked = re.sub(
        r'(セキュリティコード|セキュリティーコード|CVV|CVC)[はがの:：\s]*\d{3,4}',
        r'\1[MASKED]', masked
    )

    # 口座番号（キーワード＋数字列）
    masked = re.sub(
        r'(口座番号|口座)[はがの:：\s]*\d{4,}',
        r'\1[MASKED]', masked
    )

    # パスワード・暗証番号（キーワード後の文字列）
    masked = re.sub(
        r'(パスワード|暗証番号|PIN)[はがの:：\s]*\S+',
        r'\1[MASKED]', masked
    )

    # 住所（都道府県から始まるパターン）
    masked = re.sub(
        r'(北海道|東京都|(?:京都|大阪)府|.{2,3}県)\S{2,}',
        '[MASKED]', masked
    )

    # 名前パターン（「名前は〇〇」）
    masked = re.sub(
        r'(名前[はがの:：\s]*)\S+',
        r'\1[MASKED]', masked
    )

    return masked


# ---------------------------------------------------------------------------
# Claude CLI helper
# ---------------------------------------------------------------------------

def call_claude_cli(prompt_text):
    """claude CLI を呼び出してテキスト応答を返す。"""
    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        result = subprocess.run(
            ["claude", "-p", prompt_text],
            capture_output=True, text=True, timeout=300, env=env
        )
        if result.returncode != 0:
            print(f"Warning: claude CLI returned non-zero exit code: {result.returncode}")
            print(f"stderr: {result.stderr}")
        return result.stdout.strip()
    except FileNotFoundError:
        print("Error: 'claude' CLI not found. Install Claude Code or check PATH.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: claude CLI timed out (300s).")
        return ""


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------

def generate_filename_from_summary_gemini(model, summary_text):
    """Generates a filename suggestion using Gemini API."""
    print("Generating filename from summary (Gemini)...")
    prompt = (
        f"以下の要約内容の最も重要なトピックを反映した、具体的で短い日本語のファイル名を**一つだけ作成**してください。"
        f"ファイル名は、{MAX_FILENAME_LENGTH}文字以内の**一つの連続した文字列**とし、日本語、英数字、アンダースコア、ハイフンのみを使用してください。"
        f"拡張子は含めないでください。\n\n"
        f"例: AI戦略会議議事録\n\n"
        f"要約内容:\n{summary_text[:1000]}"
        f"\n\n作成ファイル名:"
    )
    try:
        response = model.generate_content(prompt)
        if response.candidates and response.candidates[0].content.parts:
            suggested_name = response.candidates[0].content.parts[0].text.strip()
            print(f"API suggested filename: {suggested_name}")
            return suggested_name
        else:
            print("Warning: Filename generation returned no suggestion.")
            return None
    except Exception as e:
        print(f"Error during filename generation: {e}")
        return None


def generate_filename_from_summary_claude(summary_text):
    """Generates a filename suggestion using Claude CLI."""
    print("Generating filename from summary (Claude)...")
    prompt = (
        f"以下の要約内容の最も重要なトピックを反映した、具体的で短い日本語のファイル名を**一つだけ作成**してください。"
        f"ファイル名は、{MAX_FILENAME_LENGTH}文字以内の**一つの連続した文字列**とし、日本語、英数字、アンダースコア、ハイフンのみを使用してください。"
        f"拡張子は含めないでください。ファイル名のみを出力し、他の説明は不要です。\n\n"
        f"例: AI戦略会議議事録\n\n"
        f"要約内容:\n{summary_text[:1000]}"
        f"\n\n作成ファイル名:"
    )
    suggested_name = call_claude_cli(prompt)
    if suggested_name:
        print(f"Claude suggested filename: {suggested_name}")
    return suggested_name or None


def generate_filename_from_summary(summary_text, engine, gemini_model=None):
    """要約エンジンと同じエンジンでファイル名を生成する。"""
    if engine == "claude":
        return generate_filename_from_summary_claude(summary_text)
    else:
        return generate_filename_from_summary_gemini(gemini_model, summary_text)


def sanitize_filename(filename_suggestion, max_length=MAX_FILENAME_LENGTH):
    """日本語（全角文字）も許容しつつ、ファイル名として不適切な記号のみ除去する。"""
    if not filename_suggestion:
        return "untitled_summary"

    text = filename_suggestion.strip()
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    text = re.sub(r"[\s]+", "_", text)
    text = re.sub(r"[_\-]{2,}", "_", text)
    text = text.strip("_- ")
    text = text[:max_length]
    if not text:
        return "untitled_summary"
    return text


# ---------------------------------------------------------------------------
# Transcription — Gemini
# ---------------------------------------------------------------------------

def transcribe_chunk_gemini(model, audio_chunk_path, transcription_output_path):
    """Uploads a single audio chunk, transcribes it via Gemini, and saves."""
    print(f"Uploading chunk: {audio_chunk_path}...")
    audio_file_part = genai.upload_file(path=audio_chunk_path)
    print(f"Completed upload: {audio_file_part.name}")

    print(f"Transcribing chunk {audio_file_part.name}...")
    response = model.generate_content(
        ["この音声ファイルを文字起こししてください。", audio_file_part]
    )
    print(f"Deleting uploaded chunk from API: {audio_file_part.name}")
    genai.delete_file(audio_file_part.name)

    transcription_text = ""
    if response.candidates and response.candidates[0].content.parts:
        transcription_text = response.candidates[0].content.parts[0].text
    else:
        print(f"Warning: Transcription for chunk {audio_chunk_path} returned no text.")

    try:
        with open(transcription_output_path, "w", encoding="utf-8") as f:
            f.write(transcription_text)
        print(f"Transcription for chunk saved to: {transcription_output_path}")
    except IOError as e:
        print(f"Error saving transcription for chunk: {e}")

    return transcription_text


def transcribe_audio_gemini(model, audio_file_path, temp_chunk_dir_path):
    """Gemini API を使った文字起こし（チャンク分割対応）。"""
    print(f"Loading audio file: {audio_file_path}...")
    try:
        audio = AudioSegment.from_file(audio_file_path)
    except Exception as e:
        raise ValueError(
            f"Could not read audio file {audio_file_path}. Ensure ffmpeg is installed. Error: {e}"
        )

    duration_ms = len(audio)
    print(f"Audio duration: {duration_ms / 1000 / 60:.2f} minutes")

    short_transcription_cache = None
    if temp_chunk_dir_path is not None:
        short_transcription_cache = temp_chunk_dir_path / "full_transcription.txt"
    else:
        short_transcription_cache = pathlib.Path(audio_file_path).parent / (
            pathlib.Path(audio_file_path).stem + "_transcription.txt"
        )

    if duration_ms <= CHUNK_MAX_DURATION_MS:
        if short_transcription_cache.exists():
            print(f"Found cached transcription: {short_transcription_cache}")
            with open(short_transcription_cache, "r", encoding="utf-8") as f:
                return f.read()
        print("Audio is short enough, transcribing directly.")
        print(f"Uploading file: {audio_file_path}...")
        audio_file_full = genai.upload_file(path=audio_file_path)
        print(f"Completed upload: {audio_file_full.name}")

        print("Transcribing audio...")
        response = model.generate_content(
            ["この音声ファイルを文字起こししてください。", audio_file_full]
        )
        print(f"Deleting uploaded file from API: {audio_file_full.name}")
        genai.delete_file(audio_file_full.name)
        if response.candidates and response.candidates[0].content.parts:
            transcription = response.candidates[0].content.parts[0].text
            try:
                with open(short_transcription_cache, "w", encoding="utf-8") as f:
                    f.write(transcription)
                print(f"Transcription cached to: {short_transcription_cache}")
            except Exception as e:
                print(f"Warning: Failed to cache transcription: {e}")
            return transcription
        else:
            raise ValueError("Direct transcription failed or returned an empty response.")
    else:
        print(f"Audio is long, splitting into chunks with overlap into {temp_chunk_dir_path}...")
        temp_chunk_dir_path.mkdir(parents=True, exist_ok=True)

        all_transcriptions = []
        start_ms = 0
        chunk_id = 0
        while start_ms < duration_ms:
            end_ms = min(start_ms + CHUNK_MAX_DURATION_MS, duration_ms)
            chunk_id += 1

            chunk_audio_file_path = temp_chunk_dir_path / f"chunk_{chunk_id}.wav"
            chunk_transcription_file_path = temp_chunk_dir_path / f"chunk_{chunk_id}_transcription.txt"

            if not chunk_audio_file_path.exists():
                print(f"Exporting audio chunk {chunk_id}: {start_ms}ms to {end_ms}ms")
                current_chunk_segment = audio[start_ms:end_ms]
                current_chunk_segment.export(chunk_audio_file_path, format="wav")
            else:
                print(f"Audio chunk {chunk_audio_file_path} already exists.")

            if chunk_transcription_file_path.exists():
                print(f"Found existing transcription for chunk {chunk_id}")
                try:
                    with open(chunk_transcription_file_path, "r", encoding="utf-8") as f:
                        transcription_part = f.read()
                except IOError:
                    transcription_part = transcribe_chunk_gemini(
                        model, chunk_audio_file_path, chunk_transcription_file_path
                    )
            else:
                transcription_part = transcribe_chunk_gemini(
                    model, chunk_audio_file_path, chunk_transcription_file_path
                )

            all_transcriptions.append(transcription_part)

            if end_ms == duration_ms:
                break
            start_ms = max(0, end_ms - OVERLAP_MS)
            if start_ms >= duration_ms:
                break

        print(f"Processed {len(all_transcriptions)} chunks.")
        return "\n\n".join(filter(None, all_transcriptions))


# ---------------------------------------------------------------------------
# Transcription — Whisper (local)
# ---------------------------------------------------------------------------

def transcribe_audio_whisper(audio_file_path, whisper_model_name):
    """mlx-whisper を使ったローカル文字起こし。"""
    print(f"Transcribing with Whisper (model: {whisper_model_name})...")
    try:
        import mlx_whisper
    except ImportError:
        print("Error: mlx-whisper is not installed. Run: pip install mlx-whisper")
        sys.exit(1)

    result = mlx_whisper.transcribe(
        str(audio_file_path),
        path_or_hf_repo=whisper_model_name,
    )
    transcription = result.get("text", "")
    print(f"Whisper transcription complete ({len(transcription)} chars).")
    return transcription


# ---------------------------------------------------------------------------
# Proofreading
# ---------------------------------------------------------------------------

def proofread_text(text, engine, gemini_model=None):
    """文字起こし結果を校正する。engine が 'none' ならそのまま返す。"""
    if engine == "none":
        return text

    prompt = (
        "以下の文字起こしテキストを校正してください。\n"
        "- 誤字脱字を修正\n"
        "- 句読点を適切に追加\n"
        "- 明らかな聞き間違いを文脈から修正\n"
        "- 内容自体は変更しないこと\n"
        "- 校正後のテキストのみを出力してください\n\n"
        f"テキスト:\n{text}"
    )

    if engine == "claude":
        print("Proofreading with Claude CLI...")
        return call_claude_cli(prompt)
    elif engine == "gemini":
        print("Proofreading with Gemini API...")
        response = gemini_model.generate_content(prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        else:
            print("Warning: Proofreading returned empty response, using original text.")
            return text
    else:
        print(f"Warning: Unknown proofread engine '{engine}', skipping.")
        return text


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

def summarize_text(text, prompt_template, engine, gemini_model=None):
    """文字起こし結果を要約する。"""
    prompt = prompt_template.replace("{{TRANSCRIPTION}}", text)

    if engine == "claude":
        print("Summarizing with Claude CLI...")
        return call_claude_cli(prompt)
    elif engine == "gemini":
        print("Summarizing with Gemini API...")
        response = gemini_model.generate_content(prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        else:
            raise ValueError("Summarization failed or returned an empty response.")
    else:
        raise ValueError(f"Unknown summarize engine: {engine}")


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_markdown(transcription, proofread, summary, output_dir, generated_filename_base, file_date):
    """YYYYMMDD_タイトル.md 形式でMarkdownを保存する。既存ファイルがあれば連番を付与。"""
    date_prefix = file_date.strftime("%Y%m%d")
    base_name = f"{date_prefix}_{generated_filename_base}"
    markdown_filename = f"{base_name}.md"
    output_path = pathlib.Path(output_dir) / markdown_filename
    count = 1
    while output_path.exists():
        markdown_filename = f"{base_name}_{count}.md"
        output_path = pathlib.Path(output_dir) / markdown_filename
        count += 1
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content_parts = []
    content_parts.append(f"## 要約\n\n{summary}")
    if proofread and proofread != transcription:
        content_parts.append(f"## 校正済みテキスト\n\n{proofread}")
    content_parts.append(f"## 文字起こし\n\n{transcription}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(content_parts) + "\n")
    print(f"Markdown saved to: {output_path}")
    return markdown_filename


def log_processed_file(
    log_file_path, source_audio, output_markdown, status, error_message=None
):
    """Logs the processing information to a JSONL file."""
    log_entry = {
        "source_audio": source_audio,
        "output_markdown": output_markdown,
        "processed_at": datetime.datetime.now().isoformat(),
        "status": status,
    }
    if error_message:
        log_entry["error_message"] = error_message

    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(f"Logged to: {log_file_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Transcribe and summarize audio files in a directory."
    )
    parser.add_argument(
        "--audio_processing_dir", required=True,
        help="Directory containing audio files to process.",
    )
    parser.add_argument(
        "--markdown_output_dir", required=True,
        help="Directory to save the Markdown summary.",
    )
    parser.add_argument(
        "--summary_prompt_file_path", required=True,
        help="Path to the summary prompt template file.",
    )
    parser.add_argument(
        "--processed_log_file_path", required=True,
        help="Path to the JSONL log file.",
    )
    args = parser.parse_args()

    # --- Read engine configuration from environment variables ---
    transcribe_engine = os.getenv("TRANSCRIBE_ENGINE", "whisper").lower()
    proofread_engine = os.getenv("PROOFREAD_ENGINE", "none").lower()
    summarize_engine = os.getenv("SUMMARIZE_ENGINE", "claude").lower()
    whisper_model = os.getenv("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
    enable_masking = os.getenv("ENABLE_MASKING", "true").lower() == "true"

    print(f"Configuration:")
    print(f"  Transcribe engine: {transcribe_engine}")
    print(f"  Proofread engine:  {proofread_engine}")
    print(f"  Summarize engine:  {summarize_engine}")
    print(f"  Whisper model:     {whisper_model}")
    print(f"  Masking enabled:   {enable_masking}")

    # --- Gemini warning ---
    if transcribe_engine in ("gemini", "both"):
        print("\n⚠ 注意: 文字起こしにGemini APIを使用します。音声データがGoogleのサーバーに送信されます。")
        print("  録音内にパスワード・電話番号・口座番号などの個人情報が含まれる場合、情報漏洩のリスクがあります。")
        print("  個人情報を含む音声にはWhisper（ローカル）の使用を推奨します。\n")

    # --- Masking only works with whisper ---
    if enable_masking and transcribe_engine not in ("whisper", "both"):
        print("⚠ マスク機能はWhisper（ローカル）での文字起こし時のみ有効です。Gemini選択時は無効化されます。")
        enable_masking = False

    # --- Setup Gemini if needed ---
    needs_gemini = (
        transcribe_engine in ("gemini", "both")
        or proofread_engine == "gemini"
        or summarize_engine == "gemini"
    )
    gemini_model = None
    if needs_gemini:
        if genai is None:
            print("Error: google-generativeai is not installed. Run: pip install google-generativeai")
            return
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("Error: GOOGLE_API_KEY environment variable not set (required for Gemini engine).")
            log_processed_file(
                args.processed_log_file_path,
                pathlib.Path(args.audio_processing_dir).name,
                None, "failure", "GOOGLE_API_KEY not set",
            )
            return
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")

    processing_dir = pathlib.Path(args.audio_processing_dir)
    markdown_output_dir = pathlib.Path(args.markdown_output_dir)
    summary_prompt_file_path = pathlib.Path(args.summary_prompt_file_path)
    processed_log_file_path = pathlib.Path(args.processed_log_file_path)

    done_dir = processing_dir / "done"
    done_dir.mkdir(parents=True, exist_ok=True)

    audio_extensions = [".wav", ".mp3", ".m4a"]
    audio_files_to_process = [
        f for f in processing_dir.iterdir()
        if f.is_file() and f.suffix.lower() in audio_extensions
    ]

    if not audio_files_to_process:
        print(f"No audio files found in {processing_dir} with extensions {audio_extensions}")
        return

    print(f"Found {len(audio_files_to_process)} audio files to process in {processing_dir}")

    for audio_file_path in audio_files_to_process:
        original_audio_path = audio_file_path
        original_audio_filename = original_audio_path.name
        original_audio_filename_stem = original_audio_path.stem
        output_markdown_filename = None
        print(f"\n--- Processing file: {original_audio_filename} ---")

        temp_base_dir = pathlib.Path(".").resolve() / ".tmp_chunks"
        temp_chunk_processing_dir = temp_base_dir / f"{original_audio_filename_stem}_chunks"

        cleanup_temp_dir_on_success = False

        try:
            # --- Step 1: Transcription ---
            transcription = None
            try:
                if transcribe_engine == "whisper":
                    transcription = transcribe_audio_whisper(original_audio_path, whisper_model)
                elif transcribe_engine == "gemini":
                    if AudioSegment is None:
                        raise ValueError("pydub is required for Gemini transcription. Run: pip install pydub")
                    # Check duration for chunking
                    audio_for_duration_check = AudioSegment.from_file(original_audio_path)
                    if len(audio_for_duration_check) > CHUNK_MAX_DURATION_MS:
                        temp_chunk_processing_dir.mkdir(parents=True, exist_ok=True)
                        cleanup_temp_dir_on_success = True
                        print(f"Using temporary directory for chunks: {temp_chunk_processing_dir}")

                    transcription = transcribe_audio_gemini(
                        gemini_model, original_audio_path,
                        temp_chunk_processing_dir if cleanup_temp_dir_on_success else None,
                    )
                elif transcribe_engine == "both":
                    # Whisper + Gemini 両方で文字起こしし、結果を統合
                    print("  [both] Whisperで文字起こし中...")
                    whisper_transcription = transcribe_audio_whisper(original_audio_path, whisper_model)
                    print("  [both] Geminiで文字起こし中...")
                    if AudioSegment is None:
                        raise ValueError("pydub is required for Gemini transcription. Run: pip install pydub")
                    audio_for_duration_check = AudioSegment.from_file(original_audio_path)
                    if len(audio_for_duration_check) > CHUNK_MAX_DURATION_MS:
                        temp_chunk_processing_dir.mkdir(parents=True, exist_ok=True)
                        cleanup_temp_dir_on_success = True
                    gemini_transcription = transcribe_audio_gemini(
                        gemini_model, original_audio_path,
                        temp_chunk_processing_dir if cleanup_temp_dir_on_success else None,
                    )
                    transcription = (
                        "## Whisper（ローカル）の文字起こし結果\n\n"
                        + whisper_transcription
                        + "\n\n---\n\n"
                        + "## Gemini APIの文字起こし結果\n\n"
                        + gemini_transcription
                    )
                    print("  [both] 両方の文字起こし完了。結果を統合しました。")
                else:
                    raise ValueError(f"Unknown transcribe engine: {transcribe_engine}")
            except Exception as e:
                print(f"Error during transcription for {original_audio_filename}: {e}")
                log_processed_file(
                    processed_log_file_path, original_audio_filename,
                    None, "transcribe_failure", str(e),
                )
                continue

            # --- Save transcription to file ---
            transcription_save_path = done_dir / f"{original_audio_filename_stem}_transcription.txt"
            try:
                with open(transcription_save_path, "w", encoding="utf-8") as f:
                    f.write(transcription)
                print(f"Transcription saved to: {transcription_save_path}")
            except IOError as e:
                print(f"Warning: Failed to save transcription: {e}")

            # --- Step 2: Masking ---
            text_for_llm = transcription
            if enable_masking:
                print("Applying masking to sensitive information...")
                text_for_llm = mask_sensitive_info(transcription)
                masked_count = text_for_llm.count("[MASKED]")
                if masked_count > 0:
                    print(f"  Masked {masked_count} sensitive item(s).")
                else:
                    print("  No sensitive information detected.")

            # --- Step 3: Proofreading (optional) ---
            proofread_result = text_for_llm
            try:
                proofread_result = proofread_text(text_for_llm, proofread_engine, gemini_model)
            except Exception as e:
                print(f"Warning: Proofreading failed ({e}), using unproofread text.")

            # --- Step 4: Summarization ---
            try:
                with open(summary_prompt_file_path, "r", encoding="utf-8") as f:
                    prompt_template = f.read()

                summary = summarize_text(
                    proofread_result, prompt_template, summarize_engine, gemini_model
                )

                # --- Step 5: Filename generation (same engine as summarize) ---
                suggested_filename_base = generate_filename_from_summary(
                    summary, summarize_engine, gemini_model
                )
                sanitized_filename_base = sanitize_filename(suggested_filename_base)

                file_creation_timestamp = original_audio_path.stat().st_ctime
                file_creation_date = datetime.datetime.fromtimestamp(file_creation_timestamp)

                output_markdown_filename = save_markdown(
                    transcription, proofread_result, summary,
                    markdown_output_dir, sanitized_filename_base, file_creation_date,
                )
                log_processed_file(
                    processed_log_file_path, original_audio_filename,
                    output_markdown_filename, "summary_success",
                )
                print(f"Processing successful for {original_audio_filename}.")

                # Move processed file to done directory
                try:
                    shutil.move(
                        str(original_audio_path),
                        str(done_dir / original_audio_filename),
                    )
                    print(f"Moved {original_audio_filename} to {done_dir}")
                except Exception as e:
                    print(f"Error moving {original_audio_filename} to {done_dir}: {e}")
                    log_processed_file(
                        processed_log_file_path, original_audio_filename,
                        output_markdown_filename, "move_to_done_failure",
                        f"Failed to move to {done_dir}: {str(e)}",
                    )

                # Clean up temp chunk dir if used
                if cleanup_temp_dir_on_success and temp_chunk_processing_dir.exists():
                    try:
                        shutil.rmtree(temp_chunk_processing_dir)
                        print(f"Removed temporary chunk directory: {temp_chunk_processing_dir}")
                    except Exception as e:
                        print(f"Warning: Failed to remove temp directory: {e}")

            except Exception as e:
                print(f"Error summarizing {original_audio_filename}: {e}")
                log_processed_file(
                    processed_log_file_path, original_audio_filename,
                    output_markdown_filename, "summary_failure", str(e),
                )
                continue

        except Exception as e:
            print(f"Unhandled error processing {original_audio_filename}: {e}")
            log_processed_file(
                processed_log_file_path, original_audio_filename,
                output_markdown_filename, "failure", str(e),
            )
            continue

    print("\nAll files processed.")


if __name__ == "__main__":
    main()
