import sys
from pathlib import Path

from PIL import Image

raw_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
# (centre x, centre y, square side) as fractions of the photo width, picked per photo to frame the garment
framing = {
	"p1": (0.5, 0.36, 0.78),
	"p2": (0.51, 0.52, 0.6),
	"p5": (0.5, 0.5, 0.82),
	"p7": (0.55, 0.42, 0.95),
}

for name, (centre_x, centre_y, side_fraction) in framing.items():
	image = Image.open(raw_dir / f"{name}.jpg").convert("RGB")
	width, height = image.size
	side = int(width * side_fraction)
	left = min(max(int(width * centre_x - side / 2), 0), width - side)
	top = min(max(int(height * centre_y - side / 2), 0), height - side)
	square = image.crop((left, top, left + side, top + side)).resize((800, 800), Image.LANCZOS)
	square.save(out_dir / f"{name}.jpg", quality=84, optimize=True, progressive=True)
	square.save(out_dir / f"{name}.webp", quality=82)
	thumb_width = int(800 * 52 / 64)
	thumb_left = (800 - thumb_width) // 2
	thumb = square.crop((thumb_left, 0, thumb_left + thumb_width, 800)).resize((104, 128), Image.LANCZOS)
	thumb.save(out_dir / f"{name}-thumb.jpg", quality=86, optimize=True)
	card_height = int(800 * 240 / 272)
	card_top = int((800 - card_height) * 0.25)
	card = square.crop((0, card_top, 800, card_top + card_height)).resize((544, 480), Image.LANCZOS)
	card.save(out_dir / f"{name}-card.jpg", quality=84, optimize=True, progressive=True)
