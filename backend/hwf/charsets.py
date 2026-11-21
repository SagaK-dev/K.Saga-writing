"""Defined sets. Character identity is never inferred from ink shapes."""
from __future__ import annotations
from pathlib import Path
import unicodedata

DATA_DIR = Path(__file__).resolve().parents[2] / 'data'


def unique_scalars(text: str) -> list[int]:
    found = set()
    result = []
    for char in text:
        cp = ord(char)
        if 0xD800 <= cp <= 0xDFFF:
            raise ValueError(f'Unicode surrogate U+{cp:04X} cannot be assigned')
        if cp in found or char in '\r\n\t':
            continue
        if unicodedata.category(char) in {'Cf', 'Cc', 'Cs', 'Cn'}:
            raise ValueError(f'U+{cp:04X} is not a visible, assigned character')
        if unicodedata.combining(char):
            raise ValueError(f'U+{cp:04X} is a combining mark; sequence shaping is not supported')
        found.add(cp)
        result.append(cp)
    return result


def jis0208_kanji() -> list[int]:
    """JIS X 0208 ku 16–84 = first and second level kanji, in kuten order."""
    out = []
    for ku in range(16, 85):
        for ten in range(1, 95):
            try:
                encoded = bytes([0x1b,0x24,0x42, ku+0x20, ten+0x20,0x1b,0x28,0x42])
                cp = ord(encoded.decode('iso2022_jp'))
                out.append(cp)
            except (UnicodeDecodeError, ValueError):
                continue
    return list(dict.fromkeys(out))


def get_charset(name: str, custom: str = '') -> list[int]:
    kana = ''.join(chr(c) for c in range(0x3041, 0x3097)) + ''.join(chr(c) for c in range(0x30A1, 0x30FB)) + 'ーヷヸヹヺ'
    ascii_letters = ''.join(chr(c) for c in range(0x21, 0x7F))
    choices = {
        'kana': kana,
        'latin': ascii_letters,
        'symbols': '。、・「」『』（）［］｛｝？！ー〜…：；＋－×÷＝％＃＆＠＊／＼｜＿￥　',
    }
    if name == 'joyo':
        choices['joyo'] = (DATA_DIR / 'joyo_kanji.txt').read_text(encoding='utf-8').strip()
    if name == 'all':
        choices['all'] = kana + ascii_letters + choices['symbols'] + (DATA_DIR / 'joyo_kanji.txt').read_text(encoding='utf-8').strip()
    if name == 'jis':
        return jis0208_kanji()
    if name == 'custom':
        if not custom:
            raise ValueError('Custom charset is empty')
        return unique_scalars(custom)
    if name not in choices:
        raise ValueError('Unknown character set')
    cps = unique_scalars(choices[name])
    # U+3000 needs a font blank, not hand-drawn artwork.
    return cps
