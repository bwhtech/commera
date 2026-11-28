"""Pad product photos to a seamless square (landscape) or 4:3 (portrait) canvas by extending their own backdrop.

Usage: python3 pad_images.py img-source img
"""

import subprocess
import sys
import tempfile
from pathlib import Path


def run(*args):
	subprocess.run(["magick", *map(str, args)], check=True)


def size(path):
	out = subprocess.run(
		["magick", "identify", "-format", "%w %h", str(path)], capture_output=True, text=True, check=True
	).stdout
	return map(int, out.split())


def pad(source, target, tmp):
	w, h = size(source)
	cw, ch = (max(w, h), max(w, h)) if w >= h else (round(h * 4 / 3), h)
	dx, dy = (cw - w) // 2, (ch - h) // 2
	feather = round(min(w, h) * 0.06)
	run(
		source,
		"-set",
		"option:distort:viewport",
		f"{cw}x{ch}-{dx}-{dy}",
		"-virtual-pixel",
		"Edge",
		"-distort",
		"SRT",
		"0",
		"+repage",
		"-blur",
		"0x18",
		tmp / "bg.png",
	)
	run(
		"-size",
		f"{w}x{h}",
		"xc:black",
		"-fill",
		"white",
		"-draw",
		f"rectangle {feather},{feather} {w - feather},{h - feather}",
		"-blur",
		f"0x{feather // 2}",
		tmp / "mask.png",
	)
	run(source, tmp / "mask.png", "-alpha", "off", "-compose", "CopyOpacity", "-composite", tmp / "fg.png")
	run(
		tmp / "bg.png",
		tmp / "fg.png",
		"-geometry",
		f"+{dx}+{dy}",
		"-compose",
		"over",
		"-composite",
		"-quality",
		"80",
		"-strip",
		target,
	)


if __name__ == "__main__":
	source_dir, target_dir = Path(sys.argv[1]), Path(sys.argv[2])
	target_dir.mkdir(parents=True, exist_ok=True)
	for source in sorted(source_dir.glob("*.jpg")):
		if sys.argv[3:] and source.stem not in sys.argv[3:]:
			continue
		pad(source, target_dir / source.name, Path(tempfile.mkdtemp()))
		print(source.name, *size(target_dir / source.name))
