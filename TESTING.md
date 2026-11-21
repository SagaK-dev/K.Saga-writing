# 検証レポート / Testing

## 実行環境

- Python 3.13.5（検証環境）
- OpenCV 4.13.0 / fontTools 4.63.0 / ReportLab 4.4.9 / PyMuPDF 1.26.7
- 実際のWindows 11／物理スキャナーは使用していません。

## テストコマンド

```bash
python -m pip install -r backend/requirements.txt
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m pytest -q tests/test_pipeline.py
PYTHONPATH=backend python tests/smoke_backend.py
```

Windows PowerShellでは `PYTHONPATH` の代わりに `$env:PYTHONPATH='backend'` を設定してください。

## 含まれるテスト

- 常用漢字2,136字、JIS第1・第2水準6,355字、かな等の集合数
- PDFテンプレートの生成とQRペイロード
- 四隅マーカーの検出、回転180度の補正、射影変換
- 印刷用の薄青線を除いた赤インク抽出
- 複数ページ／別プロジェクトのQR拒否
- SVG輪郭、内部の穴、独立した小点
- TTFとOTFの生成・再読み込み・cmap検証・欠落文字
- 同じ文字の再スキャン版管理と再処理
- ZIP往復とディレクトリ脱出攻撃拒否
- FastAPIを使ったプロジェクト作成／PDF／画像アップロード／フォント出力
- 不正なファイル形式拒否

テスト用の筆跡はOpenCVで描いた合成赤インクです。テスト成功は本物の手書き筆跡や全Windows環境での動作を保証するものではありません。

## 残る受入テスト

1. Windows 11にPython 3.12でインストール／起動。
2. 0.7mm赤ボールペンで記入したA4用紙を、実際の300dpi/600dpiスキャナーで取り込む。
3. 赤が黒に近い、背景が黄ばんだ、紙がゆがんだ場合の抽出品質を確認する。
4. 常用漢字2,136字を実際に取り込み、欠落文字を補完する。
5. 生成したTTF/OTFをWindowsにインストールし、Wordで印刷結果を確認する。
6. React UIの `npm install && npm run build` を行い、ブラウザの操作を検証する。

## 検証結果

2026-11-20（日本時間）にバックエンド回帰テスト **13件すべて成功**。実際の `glyf` TTF と `CFF ` OTF を生成してfontToolsで再読み込みし、4字（あ・い・う・A）のUnicode割り当てを確認しました。APIの静的Web画面、CSS、JavaScript、APIヘルスチェックもHTTP 200を確認しています。

React/TypeScriptのソースはTypeScriptの構文トランスパイルで診断0件でしたが、npm依存パッケージをオフライン環境で入手できず、**React版の実ビルドと画面操作は未検証**です。代わりに標準Web画面を同梱し、JavaScript構文チェックと配信確認を実施しています。実際の筆跡スキャンではありません。
