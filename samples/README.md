# Synthetic sample files

Sample font binaries, scan images and printable PDFs are generated locally using synthetic red ink rather than anyone's handwriting.

```bash
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python tests/smoke_backend.py
```

This writes `sample-sheet.pdf`, `sample-scan-synthetic.png`, a TTF font, an OTF font, and `validation.json` into this folder.

Generated font binaries should **not** be committed to the public repository. User-generated fonts are restricted to personal use and redistribution is prohibited. The example `validation.json` here is reference test data, not proof of Windows 11 or real handwriting scan acceptance.
