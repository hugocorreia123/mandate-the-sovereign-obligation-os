"""Mandate — Phase 10: perception. Reading a page, not a string.

Everything before this phase consumed clean text. Real obligations
arrive as scans. This module adds the perception tier that turns a
page into text, with the same ladder discipline as everything else:

  ocr_page()  — classical OCR (tesseract). No AI, no network, works
                on a laptop with the lights off. The Tier-2 of
                perception.
  vlm_page()  — a vision-language model via Ollama (local) reads the
                page as a human would. The Tier-1 of perception:
                slower, heavier, better on damaged pages.

Both return plain text, so the entire existing extraction stack runs
on top of either without knowing which produced it.

LANGUAGE PACKS ARE NOT OPTIONAL. Reading Portuguese with the English
model silently strips diacritics (Juízo -> Juizo, CITAÇÃO -> CITACAO)
and costs real accuracy. `ocr_page` selects the pack from the
document's language and REFUSES to quietly fall back — a wrong pack
is a wrong measurement.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

LANG_PACK = {"pt": "por", "en": "eng"}


class OCRUnavailable(RuntimeError):
    """tesseract, or the required language pack, is missing."""


def available_langs() -> set[str]:
    if not shutil.which("tesseract"):
        return set()
    out = subprocess.run(["tesseract", "--list-langs"],
                         capture_output=True, text=True)
    return {l.strip() for l in out.stdout.splitlines()[1:] if l.strip()}


def ocr_page(image_path: str | Path, lang: str = "pt",
             psm: int = 6, strict: bool = True) -> str:
    """OCR one page with the CORRECT language pack.

    strict=True (default) raises when the pack is missing rather than
    silently reading Portuguese with the English model — that
    substitution costs diacritics and produces a measurement of the
    wrong thing.
    """
    pack = LANG_PACK.get(lang, "eng")
    have = available_langs()
    if not have:
        raise OCRUnavailable(
            "tesseract not found — install it (macOS: brew install "
            "tesseract tesseract-lang)")
    if pack not in have:
        msg = (f"tesseract language pack '{pack}' is missing "
               f"(have: {sorted(have)}). Install it — macOS: "
               f"brew install tesseract-lang. Reading '{lang}' with "
               f"another pack silently strips diacritics and measures "
               f"the wrong thing.")
        if strict:
            raise OCRUnavailable(msg)
        pack = "eng"
    r = subprocess.run(
        ["tesseract", str(image_path), "-", "-l", pack,
         "--psm", str(psm)],
        capture_output=True, text=True)
    return r.stdout


VLM_PROMPT = (
    "Transcribe this scanned legal document EXACTLY as it appears. "
    "Output only the text of the document — no commentary, no "
    "summary, no markdown. Preserve line breaks, numbers, dates, "
    "currency amounts and accented characters exactly as printed. "
    "If a character is illegible, transcribe your best reading rather "
    "than omitting it."
)


def vlm_page(image_path: str | Path,
             model: str = "qwen2.5vl:7b",
             host: str = "http://localhost:11434") -> str:
    """Read a page with a local vision-language model (Ollama).

    Sovereign by construction: the page never leaves the machine.
    """
    import base64
    import json
    import urllib.request

    img = base64.b64encode(Path(image_path).read_bytes()).decode()
    body = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": VLM_PROMPT,
                      "images": [img]}],
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as f:
        return json.load(f)["message"]["content"]


PERCEPTION = {"ocr": ocr_page, "vlm": vlm_page}
