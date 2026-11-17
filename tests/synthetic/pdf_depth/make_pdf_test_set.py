"""
Builds the synthetic PDF test set for ingestion. Synthetic data only.

  hidden_content_witness_statement.pdf   text-layer PDF seeded with every off-page item type
  scanned_letter_clear.pdf                2 image-only pages, clean 300 dpi scan
  scanned_letter_poor.pdf                 1 image-only page, degraded: OCR confidence in the warn band
  scanned_letter_unreadable.pdf           1 image-only page, heavily degraded: below the block threshold

Usage:  python make_pdf_test_set.py <output_dir>
Needs reportlab, pypdf, Pillow and a DejaVu or Liberation TTF font.
"""
import io
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject,
                           TextStringObject)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT.mkdir(parents=True, exist_ok=True)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/Library/Fonts/Times New Roman.ttf",
    "C:/Windows/Fonts/times.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("No TTF font found; edit FONT_CANDIDATES.")


# ------------------------------------------------------------------------------------------------
# 1. Text-layer PDF with off-page content
# ------------------------------------------------------------------------------------------------

def make_witness_statement(path: Path) -> None:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Times-Bold", 14)
    c.drawString(72, h - 72, "WITNESS STATEMENT")
    c.setFont("Times-Roman", 11)
    lines = [
        "Claim no. TF-2026-0417. In the County Court at Manchester.",
        "I am the claimant's sister and I make this statement from my own knowledge.",
        "On 12 September 2026 I attended the meeting at the depot with my brother.",
        "His National Insurance number is PX 44 19 02 C.",
        "I believe the facts stated in this witness statement are true.",
    ]
    y = h - 110
    for line in lines:
        c.drawString(72, y, line)
        y -= 18

    # AcroForm fields: a text field, a checkbox and a dropdown
    form = c.acroForm
    c.drawString(72, 520, "Claimant name:")
    form.textfield(name="ClaimantName", value="Marcus Thornfield", x=170, y=512, width=220, height=18, borderWidth=0)
    c.drawString(72, 490, "Statement of truth signed:")
    form.checkbox(name="TruthSigned", x=230, y=486, size=12, checked=True)
    c.drawString(72, 460, "Witness:")
    form.choice(name="WitnessName", value="Beatrix Lund", options=["Beatrix Lund", "Imogen Thornfield", "Dean Hollis"],
                x=170, y=452, width=220, height=18)
    c.showPage()

    c.setFont("Times-Roman", 11)
    c.drawString(72, h - 72, "Page 2. Exhibits are listed in the schedule.")
    c.showPage()
    c.save()

    reader = PdfReader(io.BytesIO(buf.getvalue()))
    writer = PdfWriter(clone_from=reader)

    def annot(page_idx: int, fields: dict) -> None:
        d = DictionaryObject({NameObject("/Type"): NameObject("/Annot")})
        for k, v in fields.items():
            d[NameObject(k)] = v
        ref = writer._add_object(d)
        page = writer.pages[page_idx]
        if "/Annots" not in page:
            page[NameObject("/Annots")] = ArrayObject()
        page["/Annots"].append(ref)

    rect = lambda a, b, c_, d_: ArrayObject([FloatObject(a), FloatObject(b), FloatObject(c_), FloatObject(d_)])

    # Sticky note (Text annotation) with an author
    annot(0, {"/Subtype": NameObject("/Text"), "/Rect": rect(400, 700, 420, 720),
              "/Contents": TextStringObject("Call Priya Castellane on 07700 900654 before filing."),
              "/T": TextStringObject("Dev Mehta")})
    # FreeText annotation: typed directly on the page by a reviewer
    annot(0, {"/Subtype": NameObject("/FreeText"), "/Rect": rect(300, 600, 560, 630),
              "/Contents": TextStringObject("Opponent director Yusuf Castellane, DOB 14/02/1971"),
              "/DA": TextStringObject("/Helv 9 Tf 0 g")})
    # Link annotation pointing at a mailto
    annot(0, {"/Subtype": NameObject("/Link"), "/Rect": rect(72, 400, 250, 414),
              "/A": DictionaryObject({NameObject("/S"): NameObject("/URI"),
                                      NameObject("/URI"): TextStringObject("mailto:imogen.thornfield@example.com")})})
    # Unapplied redaction mark over the NI number line: the text underneath is still in the file
    annot(0, {"/Subtype": NameObject("/Redact"), "/Rect": rect(72, h - 168, 330, h - 154),
              "/OverlayText": TextStringObject("REDACTED"),
              "/Contents": TextStringObject("Redact NI number")})
    # Highlight with a reviewer comment on page 2
    annot(1, {"/Subtype": NameObject("/Highlight"), "/Rect": rect(72, h - 80, 300, h - 64),
              "/Contents": TextStringObject("Exhibit HOB-3 is the bank statement for account 71002934."),
              "/T": TextStringObject("Harriet Okonkwo-Bell")})

    # Embedded file attachment
    writer.add_attachment("Thornfield_bank_statement.txt", b"Sort code 20-45-67 account 71002934\n")
    # Bookmark / outline item
    writer.add_outline_item("Statement of Yusuf Castellane (draft)", 0)
    # Document properties
    writer.add_metadata({"/Author": "Harriet Okonkwo-Bell", "/Subject": "Client Marcus Thornfield",
                         "/Title": "Witness statement TF-2026-0417", "/Keywords": "Castellane"})
    with open(path, "wb") as f:
        writer.write(f)


# ------------------------------------------------------------------------------------------------
# 2. Image-only PDFs (scans)
# ------------------------------------------------------------------------------------------------

LETTER_P1 = [
    "Kingsley & Barr LLP",
    "14 King Street, Manchester M2 6AG",
    "",
    "Our ref: KB/2026/0912",
    "Your ref: TF-2026-0417",
    "",
    "Dear Sirs,",
    "",
    "Re: Marcus Thornfield v Castellane Holdings Ltd",
    "",
    "We act for Castellane Holdings Ltd. Your client,",
    "Mr Thornfield, of 7 Larkspur Close, Altrincham",
    "WA14 2QL, has raised a claim for unpaid wages.",
    "His National Insurance number is PX 44 19 02 C.",
]
LETTER_P2 = [
    "Our client disputes the claim in full. Payment of",
    "the sum of 31,400 pounds is not admitted.",
    "",
    "Please direct all correspondence to Dean Hollis",
    "on 0161 496 0844 or dean.hollis@example.com.",
    "",
    "Yours faithfully,",
    "",
    "Kingsley & Barr LLP",
]


def _render_page(lines, dpi: int = 300) -> Image.Image:
    w, h = int(8.27 * dpi), int(11.69 * dpi)
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    font = _font(int(dpi * 0.16))     # about 11.5 pt
    y = int(dpi * 1.0)
    for line in lines:
        draw.text((int(dpi * 1.0), y), line, font=font, fill=0)
        y += int(dpi * 0.26)
    return img


def _degrade(img: Image.Image, div: int, blur: float, rot: float, noise: float, seed: int = 7) -> Image.Image:
    """Downscale (lower dpi), blur, skew and speckle a clean page to imitate a poor scan."""
    rnd = random.Random(seed)
    w, h = img.size
    small = img.resize((w // div, h // div), Image.BILINEAR).filter(ImageFilter.GaussianBlur(blur))
    small = small.rotate(rot, fillcolor=255, expand=False)
    px = small.load()
    sw, sh = small.size
    for _ in range(int(sw * sh * noise)):
        x, y = rnd.randrange(sw), rnd.randrange(sh)
        px[x, y] = 0 if rnd.random() < 0.5 else 255
    return small


def _images_to_pdf(images, path: Path, dpi: int) -> None:
    rgb = [im.convert("RGB") for im in images]
    rgb[0].save(path, "PDF", resolution=dpi, save_all=True, append_images=rgb[1:])


def make_scans(out: Path) -> None:
    clean1, clean2 = _render_page(LETTER_P1), _render_page(LETTER_P2)
    # 2 clean pages: OCR confidence about 0.94, READY_WITH_WARNINGS
    _images_to_pdf([clean1, clean2], out / "scanned_letter_clear.pdf", 300)
    # 150 dpi, light blur and speckle: confidence about 0.63, inside the warn band (0.60-0.80)
    _images_to_pdf([_degrade(clean1, 2, 0.6, 0.8, 0.004)], out / "scanned_letter_poor.pdf", 150)
    # heavier speckle: confidence about 0.45, below the 0.60 minimum, BLOCKED
    _images_to_pdf([_degrade(clean1, 2, 0.8, 1.0, 0.02)], out / "scanned_letter_unreadable.pdf", 150)


if __name__ == "__main__":
    make_witness_statement(OUT / "hidden_content_witness_statement.pdf")
    make_scans(OUT)
    for p in sorted(OUT.glob("*.pdf")):
        print("wrote", p, p.stat().st_size, "bytes")
