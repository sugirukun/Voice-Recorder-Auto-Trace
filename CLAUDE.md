# AppLaud (MyVoiceRecoser) - Claude Code設定

## プロジェクト概要
USBボイスレコーダーの音声を自動で文字起こし・校正・要約するmacOSアプリ。
Whisper（ローカル）/ Gemini API / Claude CLIを組み合わせて処理する。

## 技術スタック
- シェルスクリプト (zsh): `script/file_mover.sh`, `script/config.sh`
- Python: `script/transcribe_summarize.py`
- macOS launchd: USB接続トリガー
- AppleScript: エンジン選択ダイアログ

## 重要なファイル
- `script/config.sh` — 全設定を一元管理（APIキーはここに書かないこと）
- `script/file_mover.sh` — メイン処理スクリプト
- `script/transcribe_summarize.py` — 文字起こし・校正・要約処理
- `prompt/summary_prompt.txt` — 要約プロンプト
- `prompt/template.txt` — プロンプトテンプレート

## セキュリティルール

### git push前のセキュリティチェック（必須）
`git push` を実行する前に、必ず `~/.claude/skills/github-security/SKILL.md` のセキュリティチェックを実施すること。

具体的には以下を確認する：
1. **Secret漏洩チェック**: コミット対象にAPIキー・パスワード・トークンが含まれていないか `git diff --cached` で確認
2. **.gitignore確認**: `.env`, `*.pem`, `*.key` 等の機密ファイルパターンが除外されているか確認
3. **config.sh確認**: `GOOGLE_API_KEY` などのAPIキーが直接記載されていないか確認
4. **ログファイル確認**: `debug/` 配下のログファイルがコミット対象に含まれていないか確認

### APIキー管理
- APIキーは `~/.zshrc` に環境変数として設定する（config.shには書かない）
- `GOOGLE_API_KEY` が必要（Geminiエンジン使用時のみ）

## コーディング規約
- シェルスクリプトは `#!/bin/zsh` を使用
- 日本語コメント推奨
- config.shの設定項目には `# --- TODO: Setting ---` コメントを付ける
