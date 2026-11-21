# Third-party notices and data provenance

The project uses these third-party Python and web libraries (versions pinned in `backend/requirements.txt` and `frontend/package.json`). This document is for attribution, not a replacement for the upstream license files.

| Component | Purpose | License (check official upstream notices before redistributing binaries) |
| --- | --- | --- |
| FastAPI / Starlette | Local API | MIT / BSD-style |
| Pydantic | Data validation | MIT |
| NumPy | Arrays | BSD-3-Clause |
| OpenCV | Registration and masks | Apache-2.0 |
| Pillow | Image processing | HPND-style |
| ReportLab | Printable PDFs | BSD-style |
| qrcode | Sheet QR | BSD-3-Clause |
| fontTools | TTF / CFF font generation | MIT with bundled notices |
| PyMuPDF | PDF rasterization | AGPL-3.0 or commercial license |
| React / ReactDOM | Optional interface | MIT |
| Vite / TypeScript | Optional UI build | MIT / Apache-2.0 |

**Important:** PyMuPDF is distributed under **AGPL-3.0 or a commercial license**. If you plan to distribute the packaged application (not just generate personal fonts), comply with AGPL-3.0 obligations or obtain the appropriate commercial license. Since the user explicitly restricts the generated fonts to personal use, that restriction is distinct from the software's own dependencies and licenses.

## Joyo dataset

`data/joyo_kanji.txt` is the 2,136-character first-column sequence derived from `hiroshi-manabe/Joyo-Kanji-List/joyo.tsv` (GitHub blob `6866de1edafe36fa7473e5a6580c5443e2b793e0`). The repository describes substitutions for some variant glyph forms, including 叱, 剥, 填 and 頬. The list is used as a factual enumeration of Unicode characters. See [repository](https://github.com/hiroshi-manabe/Joyo-Kanji-List) and [Japanese Agency for Cultural Affairs](https://www.bunka.go.jp/kokugo_nihongo/sisaku/joho/joho/kijun/naikaku/pdf/joyokanjiihyo_20101130.pdf).

This archive contains no third-party font files. ReportLab's built-in CJK registration refers to the PDF viewer's Japanese font capabilities; it does not bundle a proprietary font binary.