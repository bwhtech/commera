"""Render each PDF template with the kit sample data, print it with Chrome, and rasterize every page to PNG.

Usage: PYTHONPATH=.pylib <python> render_pdf.py
"""

import copy as copy_module
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pymupdf
from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).parent
OUT = HERE / "out" / "pdfs"
CHROME = "/home/frappe/.agent-browser/browsers/chrome-157.0.8103.78/chrome"


def money(value):
	whole, fraction = f"{value:.2f}".split(".")
	head, tail = whole[:-3], whole[-3:]
	groups = []
	while len(head) > 2:
		groups.insert(0, head[-2:])
		head = head[:-2]
	if head:
		groups.insert(0, head)
	return f"₹{','.join([*groups, tail])}.{fraction}"


def build_doc(sample):
	doc = copy_module.deepcopy(sample["order"])
	static = (HERE / "static").as_uri()
	for row in doc["items"]:
		row["amount"] = row["qty"] * row["rate"]
		row["image"] = f"{static}/{row['image']}-thumb.jpg" if row["image"] else None
	doc["total"] = sum(row["amount"] for row in doc["items"])
	charges = sum(charge["amount"] for charge in doc["charges"])
	doc["grand_total"] = round(doc["total"] - doc["discount_amount"] + charges, 2)
	doc["tax_included"] = round(doc["grand_total"] * doc["tax_rate"] / (100 + doc["tax_rate"]), 2)
	return doc


def as_document(fields):
	# attribute access like a Frappe Document; a plain dict makes doc.items resolve to dict.items
	return SimpleNamespace(**fields)


def render(env, template, out_name, context):
	OUT.mkdir(parents=True, exist_ok=True)
	html_file = OUT / f"{out_name}.html"
	pdf_file = OUT / f"{out_name}.pdf"
	html_file.write_text(env.get_template(template).render(**context))
	subprocess.run(
		[
			CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
			"--virtual-time-budget=8000", f"--print-to-pdf={pdf_file}", html_file.as_uri(),
		],
		check=True,
		capture_output=True,
	)
	pdf = pymupdf.open(pdf_file)
	for page in pdf:
		page.get_pixmap(dpi=144).save(OUT / f"{out_name}-page{page.number + 1}.png")
	print(out_name, f"{pdf.page_count} page(s)")


def main():
	sample = json.loads((HERE / "kit" / "sample.json").read_text())
	tokens = json.loads((HERE / "kit" / "tokens.json").read_text())
	env = Environment(loader=FileSystemLoader(HERE), autoescape=True)
	doc = build_doc(sample)
	base = {"brand": sample["brand"], "tokens": tokens, "money": money, "steps": sample["steps"]}

	render(env, "pdfs/order-confirmation.html.j2", "order-confirmation", {
		**base, "doc": as_document(doc), "copy": sample["copy"]["order_confirmation_pdf"],
	})

	minimal = {**doc, "customer_note": None, "gift_message": None, "billing": None, "customer_tax_id": None}
	render(env, "pdfs/order-confirmation.html.j2", "order-confirmation-minimal", {
		**base, "doc": as_document(minimal), "copy": sample["copy"]["order_confirmation_pdf"],
	})


if __name__ == "__main__":
	main()
