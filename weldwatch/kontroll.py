"""Kontroll-PDF: Zeichnung mit markierten Funden (grün = erkannt, orange = prüfen, grau = ignoriert)."""
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

def _font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

def render_overlay(pdf_path, items, exclude_rect, scale=2.0, page_index=0):
    pdf = pdfium.PdfDocument(pdf_path)
    img = pdf[page_index].render(scale=scale).to_pil().convert("RGB")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fnt = _font(int(9 * scale))
    if exclude_rect:
        x0, y0, x1, y1 = [v * scale for v in exclude_rect]
        d.rectangle([x0, y0, x1, y1], fill=(120, 120, 120, 70), outline=(90, 90, 90, 255), width=3)
        d.text((x0 + 6, y0 + 4), "ignoriert (allgemeine Angaben)", fill=(60, 60, 60, 255), font=fnt)
    for it in items:
        x0, y0, x1, y1 = [v * scale for v in it["box"]]
        col = tuple(it["farbe"]) if it.get("farbe") else ((0, 170, 0) if it["ok"] else (255, 140, 0))
        d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], outline=col + (255,), width=max(2, int(1.5 * scale)))
        label = str(it["nr"])
        tw = d.textlength(label, font=fnt)
        d.rectangle([x0 - 4, y0 - 4 - 12 * scale, x0 - 4 + tw + 6, y0 - 4], fill=col + (255,))
        d.text((x0 - 1, y0 - 4 - 11.5 * scale), label, fill=(255, 255, 255, 255), font=fnt)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

def save_pdf(img, out_path, dpi=150):
    img.save(out_path, "PDF", resolution=dpi)
