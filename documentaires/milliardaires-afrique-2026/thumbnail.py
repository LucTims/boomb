#!/usr/bin/env python3
"""Miniature 1280x720 du documentaire. Usage : python3 thumbnail.py <dossier_de_travail>"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import DARK, GOLD, WHITE, chip, flag, gradient_overlay, text_img  # noqa: E402

work = sys.argv[1]
bg = Image.open(os.path.join(work, "bg", "industry_1.png")).convert("RGB").resize((1920, 1080), Image.LANCZOS)
fr = bg.convert("RGBA")
fr.alpha_composite(gradient_overlay())
fr.alpha_composite(Image.new("RGBA", fr.size, DARK + (40,)))

fr.alpha_composite(chip("TOP 10 · AFRIQUE 2026", 48, fg=DARK, bg=GOLD + (255,)), (100, 110))
y = 230
for line in ("L'HOMME LE PLUS", "RICHE D'AFRIQUE"):
    im = text_img(line, 128, WHITE)
    fr.alpha_composite(im, (90, y))
    y += 140
fr.alpha_composite(text_img("51,7 MILLIARDS $", 170, GOLD), (84, y + 20))
fr.alpha_composite(flag("NG", 150, 100), (104, y + 245))
fr.alpha_composite(text_img("Et les 9 autres ?", 64, WHITE), (290, y + 250))
d = ImageDraw.Draw(fr)
d.rectangle([0, 1064, 1920, 1080], fill=GOLD + (255,))

out = os.path.join(work, "miniature_boombooks_riches_afrique_2026.jpg")
fr.convert("RGB").resize((1280, 720), Image.LANCZOS).save(out, quality=92)
print(out)
