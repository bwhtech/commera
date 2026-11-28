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


def western_money(symbol):
	return lambda value: f"{symbol}{value:,.2f}"


def add_invoice_totals(doc):
	for row in doc["items"]:
		row["amount"] = round(row["qty"] * row["rate"], 2)
	doc["total"] = round(sum(row["amount"] for row in doc["items"]), 2)
	charges = sum(charge["amount"] for charge in doc["charges"])
	doc["net_total"] = round(doc["total"] - doc["discount_amount"] + charges, 2)
	for tax in doc["taxes"]:
		tax["amount"] = round(doc["net_total"] * tax["rate"] / 100, 2)
	doc["total_taxes"] = round(sum(tax["amount"] for tax in doc["taxes"]), 2)
	doc["grand_total"] = round(doc["net_total"] + doc["total_taxes"], 2)
	return doc


def exclusive_of_tax(amount, tax_rate):
	return round(amount * 100 / (100 + tax_rate), 2)


def build_invoice(sample, sample_pdf):
	order = sample["order"]
	invoice = sample["invoice"]
	tax_rate = order["tax_rate"]
	doc = {
		**copy_module.deepcopy(invoice),
		**sample_pdf["tax_invoice"],
		"order_name": order["name"],
		"transaction_date": order["transaction_date"],
		"payment_method": order["payment_method"],
		"payment_status": order["payment_status"],
		"billing": order["billing"],
		"shipping": order["shipping"],
		"customer_tax_id": order["customer_tax_id"],
		"coupon_code": order["coupon_code"],
		"discount_amount": exclusive_of_tax(order["discount_amount"], tax_rate),
		"charges": [
			{**charge, "amount": exclusive_of_tax(charge["amount"], tax_rate)} for charge in order["charges"]
		],
		"items": [
			{**row, "rate": exclusive_of_tax(row["rate"], tax_rate)}
			for row in copy_module.deepcopy(order["items"])
		],
	}
	return add_invoice_totals(doc)


def build_credit_note(sample, sample_pdf, invoice):
	returned = {row["item_code"]: row for row in sample["return"]["items"]}
	items = [
		{**row, "qty": returned[row["item_code"]]["qty"], "reason": returned[row["item_code"]]["reason"]}
		for row in copy_module.deepcopy(invoice["items"])
		if row["item_code"] in returned
	]
	returned_total = sum(row["qty"] * row["rate"] for row in items)
	discount_share = round(invoice["discount_amount"] * returned_total / invoice["total"], 2)
	doc = {
		**sample_pdf["credit_note"],
		"return_against": invoice["name"],
		"return_against_date": invoice["posting_date"],
		"order_name": invoice["order_name"],
		"return_name": sample["return"]["name"],
		"refund_method": sample["return"]["refund_method"],
		"refund_days": sample["return"]["refund_days"],
		"billing": invoice["billing"],
		"customer_tax_id": invoice["customer_tax_id"],
		"place_of_supply": invoice["place_of_supply"],
		"coupon_code": invoice["coupon_code"],
		"discount_amount": discount_share,
		"charges": [],
		"taxes": [{"description": tax["description"], "rate": tax["rate"]} for tax in invoice["taxes"]],
		"items": items,
	}
	return add_invoice_totals(doc)


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
	return SimpleNamespace(**fields)


def render(env, template, out_name, context):
	OUT.mkdir(parents=True, exist_ok=True)
	html_file = OUT / f"{out_name}.html"
	pdf_file = OUT / f"{out_name}.pdf"
	html_file.write_text(env.get_template(template).render(**context))
	subprocess.run(
		[
			CHROME,
			"--headless=new",
			"--disable-gpu",
			"--no-pdf-header-footer",
			"--allow-file-access-from-files",
			"--virtual-time-budget=8000",
			f"--print-to-pdf={pdf_file}",
			html_file.as_uri(),
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
	sample_pdf = json.loads((HERE / "kit" / "sample_pdf.json").read_text())
	tokens = json.loads((HERE / "kit" / "tokens.json").read_text())
	env = Environment(loader=FileSystemLoader(HERE), autoescape=True)
	doc = build_doc(sample)
	base = {"brand": sample["brand"], "tokens": tokens, "money": money, "steps": sample["steps"]}

	render(
		env,
		"pdfs/order-confirmation.html.j2",
		"order-confirmation",
		{
			**base,
			"doc": as_document(doc),
			"copy": sample["copy"]["order_confirmation_pdf"],
		},
	)

	minimal = {**doc, "customer_note": None, "gift_message": None, "billing": None, "customer_tax_id": None}
	render(
		env,
		"pdfs/order-confirmation.html.j2",
		"order-confirmation-minimal",
		{
			**base,
			"doc": as_document(minimal),
			"copy": sample["copy"]["order_confirmation_pdf"],
		},
	)

	invoice = build_invoice(sample, sample_pdf)
	assert invoice["grand_total"] == doc["grand_total"], (invoice["grand_total"], doc["grand_total"])
	render(
		env,
		"pdfs/tax-invoice.html.j2",
		"tax-invoice",
		{
			**base,
			"doc": as_document(invoice),
			"copy": sample_pdf["copy"]["tax_invoice"],
		},
	)

	inter_state = add_invoice_totals(
		{**copy_module.deepcopy(invoice), **copy_module.deepcopy(sample_pdf["tax_invoice_igst"])}
	)
	render(
		env,
		"pdfs/tax-invoice.html.j2",
		"tax-invoice-igst",
		{
			**base,
			"doc": as_document(inter_state),
			"copy": sample_pdf["copy"]["tax_invoice"],
		},
	)

	generic = add_invoice_totals(copy_module.deepcopy(sample_pdf["invoice_generic"]))
	render(
		env,
		"pdfs/tax-invoice.html.j2",
		"tax-invoice-generic",
		{
			**base,
			"brand": {**sample["brand"], **sample_pdf["brand_generic"]},
			"money": western_money(generic["currency_symbol"]),
			"doc": as_document(generic),
			"copy": sample_pdf["copy"]["tax_invoice"],
		},
	)

	credit_note = build_credit_note(sample, sample_pdf, invoice)
	assert credit_note["grand_total"] == sample["return"]["refund_amount"], credit_note["grand_total"]
	render(
		env,
		"pdfs/credit-note.html.j2",
		"credit-note",
		{
			**base,
			"doc": as_document(credit_note),
			"copy": sample_pdf["copy"]["credit_note"],
		},
	)

	packing_slip = {**doc, **sample_pdf["packing_slip"], "order_name": doc["name"]}
	render(
		env,
		"pdfs/packing-slip.html.j2",
		"packing-slip",
		{
			**base,
			"doc": as_document(packing_slip),
			"copy": sample_pdf["copy"]["packing_slip"],
		},
	)


if __name__ == "__main__":
	main()
