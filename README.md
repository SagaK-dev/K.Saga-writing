# HandwriteFont 0.1.0

**K.Saga writing** — 赤い0.7mmボールペンで書いた手書き文字から、日本語フォントを制作するローカルアプリ。

- 専用PDF用紙の自動生成（A4 / A3、縦・横、任意の行列数）
- 印刷したマスとUnicodeの固定対応（OCRで文字を推測しない）
- QRコード照合・四隅マーカー・遠近補正・180度回転補正
- カラースキャン画像から赤い筆跡を抽出（HSV方式も搭載）
- グリフの輪郭抽出・Bezier曲線化・SVG保存
- TTF (`glyf`) / OTF (`CFF `) の生成と構造検証
- 過去バージョンを保持した再スキャン・再処理
- プロジェクトの保存・再開・ZIPバックアップ
- インターネットなしで動作（初回の依存ライブラリの導入時は通信が必要）

対応文字セット：ひらがな・カタカナ177文字、英数字・基本記号、常用漢字2,136字、JIS X 0208第1・第2水準6,355字、任意のUnicodeスカラー値。

**生成フォントの使用条件：個人利用のみ。二次配布禁止。** ソフトウェアのソースコードライセンスとは別です。各フォントの `name` テーブルにも使用条件を記録します。

## Windows 11で使う

1. [Python 3.12](https://www.python.org/downloads/) をインストールする（インストール時にPython Launcherを有効化）。
2. このフォルダーを展開する。
3. PowerShellで `powershell -ExecutionPolicy Bypass -File .\install-windows.ps1` を実行する。
4. `start-windows.bat` をダブルクリックする。
5. ブラウザーで `http://127.0.0.1:8765/` を開く。

Node.js 22をインストールするとReact/TypeScript/ViteのUIをビルドできます。**Node.jsがなくても、標準搭載の依存不要Web UIで機能を使用可能**です。

## 作業手順

1. 新しいプロジェクトを作成（初期設定：`K.Saga writing`、A4、6列×8行、常用漢字＋かな＋英数字）。
2. 「用紙PDFを保存」→プリンタの印刷倍率を100%にする。
3. 各マスの中央に指定文字を赤い0.7mmボールペンで記入する。QR・四隅の基準マーカーを隠さない。
4. スキャナーでカラー300–600dpiのPNG/JPEG/PDF/TIFFとして読み取る。
5. 「スキャン」でファイルを選んで取り込む。成功した文字は自動でSVG化される。
6. 「文字確認」で個別に赤色抽出の閾値、曲線、位置を調整できる。
7. 「フォント出力」でTTFとOTFを保存し、Windowsのフォント設定からインストールする。

フォントに収録していない文字は指定フォントで表示できません。Word側のフォールバックフォント等で代替されます。未収録字数は画面と検証JSONに明示します。

## ファイル構成

```text
backend/hwf/
  api.py        FastAPIサーバーとファイル入出力
  charsets.py   Unicode文字集合・JISマッピング
  templates.py  記入用紙PDF・QRコード・位置マーカー
  scanner.py    スキャン補正・文字画像切り出し・版管理
  vector.py     赤色抽出・輪郭抽出・SVG Bézier化
  fonts.py      TrueType / CFF OpenType生成
  storage.py    ローカル永続化・安全なZIP入出力・監査履歴
frontend/src/   React / TypeScript / Vite UI
frontend/fallback/  依存不要のオフラインHTML / JS UI
data/joyo_kanji.txt  常用漢字2136字集合
samples/        合成サンプルの生成・検証手順（バイナリはローカル生成）
tests/          pytest回帰テスト
```

データは既定で `%USERPROFILE%\.handwritefont` に保存されます。ZIPエクスポートで元画像、SVG、設定、監査ログ、生成フォントを保存できます。

## ソースコードからの起動（Pythonのみ）

```bash
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -r backend\requirements.txt
# Linux/macOS: .venv/bin/python -m pip install -r backend/requirements.txt
python -m uvicorn hwf.api:app --app-dir backend --host 127.0.0.1 --port 8765
```

React UIを有効にする場合は `cd frontend && npm install && npm run build` を行ってからサーバーを再起動します。ビルド済みの `frontend/dist` が存在すると、標準UIを自動的に置き換えます。開発時は `npm run dev` を使用できます。

## 出力の確認と制約

- TTFはTrueType二次曲線（Bezierの三次曲線を二次に変換）、OTFはCFF三次曲線。`fontTools`で再読込・cmap検証。
- 画像が薄い／背景が赤みを帯びる場合、抽出の確認・再処理が必要。
- このプロジェクトには**実物の手書きスキャンによる受入テスト結果は含まれていません**。`samples`のテスト用バイナリは `PYTHONPATH=backend python tests/smoke_backend.py` でローカル生成します。GitHubには個人用フォントバイナリを公開しません。
- 大量の漢字での長文組版品質、筆圧再現、Windowsへの現物インストールは今後の実機検証項目です。
- 複数コードポイントからなる異体字シーケンスや結合文字の字形組版には未対応。ユニコードスカラー単位で処理します。
- 通常の色付き文字フォントではなく、赤い筆跡から形状を抽出した**モノクロのアウトラインフォント**を生成します。

詳細は [INSTALL.md](INSTALL.md)、[ARCHITECTURE.md](ARCHITECTURE.md)、[TESTING.md](TESTING.md) を参照してください。