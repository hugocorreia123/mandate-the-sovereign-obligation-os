"""Mandate — Phase 10: turn the corpus into scanned documents.

Why: every number in this project so far was measured on CLEAN TEXT.
That is the largest caveat in the README, and it silently broke Phase
8: the cloud tier made 1 error in 440 fields, so there was nothing to
calibrate a confidence signal against. Real documents arrive as
scans — skewed, speckled, JPEG-crushed, photocopied. Errors appear.
Errors are what make evaluation possible.

This module renders each corpus document to an image and degrades it
DETERMINISTICALLY (seeded), so the benchmark is reproducible forever
and the gold labels come free — we already know what every document
says.

Honest scope: this is *simulated* scanning. It reproduces the
mechanical artifacts (skew, sensor noise, compression, blur, uneven
lighting) but not the full ugliness of a real fax of a photocopy of a
stamped filing. Phase 10b adds a handful of genuine public filings as
a qualitative check. Stated rather than glossed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# a serif face reads like a filing; mono reads like a dot-matrix court
# printout — both are realistic, so we vary them
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _font(rng, size: int):
    for path in ([p for p in FONT_CANDIDATES if Path(p).exists()]
                 or []):
        pass
    avail = [p for p in FONT_CANDIDATES if Path(p).exists()]
    if not avail:
        return ImageFont.load_default()
    return ImageFont.truetype(rng.choice(avail), size)


@dataclass
class ScanProfile:
    """How badly the document was scanned."""
    name: str
    skew_deg: float          # rotation off-axis
    noise: int               # sensor speckle amplitude
    blur: float              # optical/defocus
    jpeg_quality: int        # compression damage
    contrast: float          # over/under-exposure
    dpi_scale: float         # resolution loss

    @staticmethod
    def clean() -> "ScanProfile":
        return ScanProfile("clean", 0.0, 0, 0.0, 95, 1.0, 1.0)

    @staticmethod
    def office() -> "ScanProfile":
        """A decent office scanner. The realistic best case."""
        return ScanProfile("office", 0.4, 8, 0.3, 85, 1.02, 0.9)

    @staticmethod
    def photocopy() -> "ScanProfile":
        """A photocopy of a print — the common case in a law firm.
        Calibrated to sit just before the cliff: OCR still reads it."""
        return ScanProfile("photocopy", 1.2, 30, 1.1, 38, 1.2, 0.55)

    @staticmethod
    def fax() -> "ScanProfile":
        """A fax of a photocopy. Calibrated to the discriminating band
        found empirically: tesseract still reads ~84% of the text but
        starts LOSING FACTS (amounts, dates). One notch worse and the
        page collapses to noise, which measures nothing — the useful
        band is narrow and was found by sweeping, not guessed."""
        return ScanProfile("fax", 2.0, 40, 1.4, 30, 1.3, 0.45)

PROFILES = {p.name: p for p in (ScanProfile.clean(),
                                ScanProfile.office(),
                                ScanProfile.photocopy(),
                                ScanProfile.fax())}


def render(text: str, rng: random.Random, width: int = 1240,
           margin: int = 90) -> Image.Image:
    """Lay the document out on an A4-ish page (1240px ~ 150dpi)."""
    size = rng.choice([19, 20, 21])
    font = _font(rng, size)
    lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for word in para.split():
            trial = (cur + " " + word).strip()
            if font.getlength(trial) > width - 2 * margin:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    lh = int(size * 1.6)
    height = max(1754, margin * 2 + lh * len(lines))
    img = Image.new("L", (width, height), 255)
    d = ImageDraw.Draw(img)
    y = margin
    for ln in lines:
        d.text((margin, y), ln, font=font, fill=18)
        y += lh
    return img


def degrade(img: Image.Image, p: ScanProfile,
            rng: random.Random) -> Image.Image:
    """Apply the mechanical artifacts of a real scan, in order."""
    import io

    if p.dpi_scale < 1.0:                     # resolution loss first
        w, h = img.size
        small = img.resize((int(w * p.dpi_scale), int(h * p.dpi_scale)),
                           Image.BILINEAR)
        img = small.resize((w, h), Image.BILINEAR)

    if p.skew_deg:                            # paper never lies flat
        img = img.rotate(rng.uniform(-p.skew_deg, p.skew_deg),
                         resample=Image.BICUBIC, fillcolor=255)

    if p.blur:
        img = img.filter(ImageFilter.GaussianBlur(p.blur))

    if p.contrast != 1.0:                     # lamp too hot/cold
        img = ImageEnhance.Contrast(img).enhance(p.contrast)

    if p.noise:                               # sensor speckle
        px = img.load()
        w, h = img.size
        for _ in range((w * h) // 90):
            x, y = rng.randrange(w), rng.randrange(h)
            v = px[x, y] + rng.randint(-p.noise * 3, p.noise * 3)
            px[x, y] = max(0, min(255, v))

    if p.jpeg_quality < 95:                   # compression damage
        buf = io.BytesIO()
        img.convert("L").save(buf, "JPEG", quality=p.jpeg_quality)
        buf.seek(0)
        img = Image.open(buf).convert("L")
    return img


def scan_corpus(corpus_dir: str | Path, out_dir: str | Path,
                profile: str = "photocopy", seed: int = 42) -> list[Path]:
    """Render + degrade every corpus document. Deterministic."""
    corpus_dir, out_dir = Path(corpus_dir), Path(out_dir)
    out = out_dir / profile
    out.mkdir(parents=True, exist_ok=True)
    p = PROFILES[profile]
    made = []
    for txt in sorted((corpus_dir / "docs").glob("*.txt")):
        rng = random.Random(f"{seed}:{profile}:{txt.stem}")
        img = degrade(render(txt.read_text(), rng), p, rng)
        dest = out / f"{txt.stem}.png"
        img.save(dest)
        made.append(dest)
    return made


if __name__ == "__main__":
    import sys
    prof = sys.argv[1] if len(sys.argv) > 1 else "photocopy"
    made = scan_corpus("data/corpus", "data/scans", prof)
    print(f"{len(made)} pages -> data/scans/{prof}/  "
          f"({PROFILES[prof]})")
