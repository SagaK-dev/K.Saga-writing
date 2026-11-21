# Architecture

HandwriteFont is a local-first handwritten font builder. The backend does not use OCR to assign identity. Each sheet page is versioned and checksummed, and each cell is mapped to a known Unicode scalar.

```text
Print PDF + QR metadata + cell locations
        |
     Red ink on paper -> Scan (PDF/PNG/JPEG/TIFF)
        |
     Validate -> Registration marker centers -> Perspective warp
        |
     QR (known expected header position) -> Page/layout integrity
        |
     Fixed cell crop -> red-channel/HSV extraction
        |
     Isolated binary mask -> contours/hole hierarchy
        |
     SVG cubic Beziers + versioned PNG/metadata
        |
     1000 UPM metrics -> CFF cubic / TTF quadratic conversion
        |
     TTF & OTF -> FontTools reload/cmap verification -> JSON report
```

The backend modules are independently testable:

- `charsets.py`: scalar validation, common character sets, JIS X 0208 ku-ten decoding.
- `templates.py`: A4/A3 ReportLab renderer; QR payload bound to project UUID/page/character signature.
- `scanner.py`: OpenCV registration, QR decoder, ink segmentation, versioned glyph snapshots.
- `vector.py`: binary contours, hole parity, SVG Bezier fit.
- `fonts.py`: `FontBuilder` for real TrueType and CFF OpenType fonts, no binary renaming.
- `storage.py`: atomic JSON manifests, project UUID isolation, ZIP validation, append-only audit.
- `api.py`: local FastAPI JSON and binary endpoints.

The React/TypeScript frontend is optional; a static HTML frontend is included for dependency-free operation. The production FastAPI app serves `frontend/dist` when available, otherwise `frontend/fallback`.

## Metrics

Default unitsPerEm: 1000, ascent: 850, descent: -150. Full-width characters use 1000 advance units; proportional Latin uses 650. Shapes are fitted to an interior rectangle, without regularizing handwriting strokes. Manual x/y shifts can be applied in font units per glyph. Advanced optical spacing and vertical OpenType features are not implemented.

## Storage

Root: `%USERPROFILE%\.handwritefont` / `$HOME/.handwritefont`.

Each project has `project.json` (UTF-8) and subdirectories `scans/`, `glyphs/U+codepoint/vNNN/` and `exports/` with a per-project `audit.jsonl`.

## Safety and trust boundaries

- Server only binds to `127.0.0.1` in provided launchers.
- Image uploads have size/format/pixel limits. PDF rendering is capped at 80 pages per upload.
- Every project identifier must parse as UUID; path names derive from trusted code points.
- ZIP import blocks path traversal, symlinks, decompression expansion, forged glyph paths and invalid project IDs.
- SVG files are generated from numeric outline coordinates, not arbitrary uploaded markup.
- Fonts and scan images are not sent to cloud services.
- Font file generation is not sandboxed from native font/parser library bugs; only open trusted, local documents where possible.

## Known limitations

- No independent glyph optimizer, hinting or OpenType vertical metrics beyond the basic horizontal font data.
- Complex text shaping and variation-selector sequences are not supported by the Unicode-scalar mapping model.
- Perspective correction works for print geometry and photo scans but paper curvature may require flattening.
- Automated tests use synthetic strokes; real red ballpoint ink on several scanner models remains unverified.
- The React source was included but requires an npm build in an environment with npm dependencies available.