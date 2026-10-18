"""Draw made-up chat screenshots for the demo (ui/assets/*.png).

All text is fictional with placeholder numbers and links.
Usage: python -m scripts.make_sample_screenshots
"""

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("ui/assets")
W, PAD, BUBBLE_W = 720, 28, 560
FONT_PATHS = ["/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

SAMPLES = {
    "digital_arrest": ("Inspector R. Sharma (CBI)", "#075e54", "#ece5dd", [
        "CENTRAL BUREAU OF INVESTIGATION - NOTICE",
        "Your Aadhaar is linked to a money laundering case (FIR 4471/2026). "
        "A non-bailable arrest warrant has been issued.",
        "To clear your name, transfer your funds to the RBI safe verification account "
        "today. Funds will be returned after verification.",
        "Stay on this video call. Do NOT tell your family or bank. "
        "This is a confidential investigation.",
    ]),
    "job_task": ("HR - TaskPro Rewards", "#2a78d6", "#eef3fa", [
        "Congrats! Task 7 completed. Your earnings: Rs 1,20,000",
        "To withdraw, deposit Rs 40,000 as a merchant task fee. "
        "Amount is refunded with your earnings.",
        "Offer valid for 1 hour only. Many members are waiting for this slot!",
    ]),
    "kyc_update": ("SBI-KYCUPD", "#3b3b3b", "#f2f2f2", [
        "Dear Customer, your SBI KYC has EXPIRED. Your account will be BLOCKED today.",
        "To avoid freezing, move your balance to the verification account "
        "provided by our KYC desk: +91-98XXXXXX12",
        "Update now: bit.ly/xxxx-kyc",
    ]),
}


def font(size: int) -> ImageFont.ImageFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw(sender: str, header: str, bg: str, messages: list[str]) -> Image.Image:
    body, title = font(26), font(30)
    lines = [textwrap.wrap(m, width=36) for m in messages]
    height = 110 + sum(len(ls) * 36 + 48 for ls in lines) + PAD
    img = Image.new("RGB", (W, height), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 90], fill=header)
    d.text((PAD, 28), sender, font=title, fill="white")
    y = 110
    for ls in lines:
        h = len(ls) * 36 + 24
        d.rounded_rectangle([PAD, y, PAD + BUBBLE_W, y + h], radius=16, fill="white")
        for i, line in enumerate(ls):
            d.text((PAD + 18, y + 12 + i * 36), line, font=body, fill="#111111")
        y += h + 24
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (sender, header, bg, messages) in SAMPLES.items():
        path = OUT / f"{name}.png"
        draw(sender, header, bg, messages).save(path, optimize=True)
        print(f"{path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
