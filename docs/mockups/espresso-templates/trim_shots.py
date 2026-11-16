"""Trim the empty page background below the email content, keeping the bottom gutter."""

import sys
from pathlib import Path

from PIL import Image, ImageChops

BOTTOM_GUTTER = 64


def trim(path):
	image = Image.open(path).convert("RGB")
	width, height = image.size
	background = Image.new("RGB", (width, height), image.getpixel((width - 1, height - 1)))
	box = ImageChops.difference(image, background).getbbox()
	if not box:
		return
	bottom = min(height, box[3] + BOTTOM_GUTTER)
	image.crop((0, 0, width, bottom)).save(path, optimize=True)


for path in sys.argv[1:]:
	trim(Path(path))
