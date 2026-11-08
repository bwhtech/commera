"""Publish all demo items to the website, if products do not show after install_demo_data."""

import frappe

from commera.commera_ecommerce.doctype.bulk_publish_variants.bulk_publish_variants import save_publish_state


def publish_all_demo_items():
	"""Publish all demo product items to website"""

	print("Publishing demo items to website...")

	warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
	if not warehouse:
		print("❌ No warehouse found")
		return

	items = frappe.get_all(
		"Item",
		filters={"has_variants": 0, "is_stock_item": 1},
		fields=["name", "item_name", "item_group", "brand", "description"],
	)

	created = 0
	published = 0

	for item in items:
		wi_name = frappe.db.get_value("Website Item", {"item_code": item.name}, "name")

		if not wi_name:
			wi = frappe.get_doc(
				{
					"doctype": "Website Item",
					"item_code": item.name,
					"item_name": item.item_name,
					"web_item_name": item.item_name,
					"item_group": item.item_group,
					"brand": item.brand or "",
					"description": item.description or "",
					"website_warehouse": warehouse,
					"published": 1,
					"website_item_groups": [{"item_group": item.item_group}] if item.item_group else [],
				}
			)
			wi.insert(ignore_permissions=True)
			created += 1
		else:
			frappe.db.set_value("Website Item", wi_name, {"published": 1, "website_warehouse": warehouse})

			wi = frappe.get_doc("Website Item", wi_name)
			if not wi.website_item_groups and item.item_group:
				wi.append("website_item_groups", {"item_group": item.item_group})
				wi.save(ignore_permissions=True)

			published += 1

	# Fix Style Attribute Variant routes (remove language prefix)
	savs = frappe.get_all("Style Attribute Variant", fields=["name", "route"])
	sav_fixed = 0

	for sav in savs:
		if sav.route:
			clean_route = sav.route.replace("en/products/", "").replace("ar/products/", "")
			if clean_route != sav.route:
				frappe.db.set_value("Style Attribute Variant", sav.name, "route", clean_route)
				sav_fixed += 1

	# Publish all SAVs that have sizes
	to_publish = [
		sav.name
		for sav in frappe.get_all("Style Attribute Variant", filters={"is_published": 0}, fields=["name"])
		if frappe.db.exists("Color Size Item", {"parent": sav.name})
	]
	# Through the bulk publisher, which also updates the search index and announces product_updated.
	save_publish_state(1, to_publish)
	sav_published = len(to_publish)

	# Fix Website Item routes (should be simple slug without prefix)
	website_items = frappe.get_all("Website Item", fields=["name", "item_code", "route"])
	routed = 0

	for wi in website_items:
		item_code = wi.item_code.lower().replace("_", "-").replace(" ", "-")

		if wi.route:
			clean_route = wi.route.replace("en/products/", "").replace("ar/products/", "")
			if clean_route != item_code:
				frappe.db.set_value("Website Item", wi.name, "route", item_code)
				routed += 1
		else:
			frappe.db.set_value("Website Item", wi.name, "route", item_code)
			routed += 1
	# nosemgrep: frappe-manual-commit  # job only, a crash keeps the items already published
	frappe.db.commit()
	frappe.clear_cache()

	print("\n✅ Complete!")
	print(f"   Created: {created} Website Items")
	print(f"   Published: {published} existing items")
	print(f"   Fixed SAV routes: {sav_fixed}")
	print(f"   Published SAVs: {sav_published}")
	print(f"   Fixed Website Item routes: {routed}")
	print("\nVisit: https://your-site.com/en/products")
	print("\nNote: Routes should be clean slugs (e.g., 'tshirt-classic-black')")
	print("      The /en/products/ prefix is added by hooks.py routing")


if __name__ == "__main__":
	publish_all_demo_items()
