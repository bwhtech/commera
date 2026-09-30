import frappe
from frappe.modules.utils import sync_customizations

BAND_FIELDS = ("from_value", "to_value", "shipping_amount", "free_shipping")
MERGE_SAVEPOINT = "move_service_shipping_rule"


def execute():
	"""Delivery options used to carry their own Shipping Rule; now the store rule's bands name the option."""
	if "bwh_shipping" not in frappe.get_installed_apps():
		return
	# Customizations sync after post_model_sync patches, so the band's shipping_service column may not exist yet.
	sync_customizations("bwh_shipping")
	if not frappe.db.has_column("Shipping Service", "shipping_rule"):
		return
	move_service_shipping_rules_to_store_rule()


def move_service_shipping_rules_to_store_rule():
	services_by_rule = get_services_by_rule()
	if not services_by_rule:
		return

	store_rule = get_store_rule(services_by_rule)
	if not store_rule:
		return

	for shipping_rule, services in services_by_rule.items():
		if shipping_rule == store_rule:
			stamp_store_rule_bands(store_rule, services)
		else:
			for service in services:
				merge_service_rule(store_rule, shipping_rule, service)


def get_services_by_rule() -> dict[str, list[str]]:
	service = frappe.qb.DocType("Shipping Service")
	rows = (
		frappe.qb.from_(service)
		.select(service.name, service.shipping_rule)
		.where(service.shipping_rule.isnotnull() & (service.shipping_rule != ""))
		.orderby(service.creation)
		.run(as_dict=True)
	)
	services_by_rule = {}
	for row in rows:
		services_by_rule.setdefault(row.shipping_rule, []).append(row.name)
	return services_by_rule


def get_store_rule(services_by_rule: dict[str, list[str]]) -> str | None:
	store_rule = frappe.db.get_single_value("Commera Settings", "shipping_rule")
	if store_rule:
		return store_rule

	if len(services_by_rule) > 1:
		frappe.log_error(
			title="Delivery option Shipping Rules not moved",
			message=f"No store Shipping Rule is set and the delivery options use different rules: "
			f"{services_by_rule}. Pick the store rule in Commera Settings and name each band's option.",
		)
		return None

	store_rule = next(iter(services_by_rule))
	frappe.db.set_single_value("Commera Settings", "shipping_rule", store_rule)
	return store_rule


def stamp_store_rule_bands(store_rule: str, services: list[str]):
	if len(services) > 1:
		frappe.log_error(
			title="Store Shipping Rule bands not assigned",
			message=f"Delivery options {', '.join(services)} all used the store Shipping Rule {store_rule}, "
			"so its bands cannot say which option they price. Name the option on each band.",
		)
		return

	rule = frappe.get_doc("Shipping Rule", store_rule)
	unassigned_bands = [band for band in rule.conditions if not band.shipping_service]
	if not unassigned_bands:
		return
	for band in unassigned_bands:
		band.shipping_service = services[0]
	rule.save(ignore_permissions=True)


def merge_service_rule(store_rule: str, shipping_rule: str, service: str):
	rule = frappe.get_doc("Shipping Rule", store_rule)
	if any(band.shipping_service == service for band in rule.conditions):
		return

	service_rule = frappe.get_doc("Shipping Rule", shipping_rule)
	if (service_rule.calculate_based_on, service_rule.company) != (rule.calculate_based_on, rule.company):
		log_merge_refused(service, shipping_rule, store_rule, "it is based on a different figure or company")
		return

	for band in service_rule.conditions:
		rule.append(
			"conditions", {**{field: band.get(field) for field in BAND_FIELDS}, "shipping_service": service}
		)

	frappe.db.savepoint(MERGE_SAVEPOINT)
	try:
		rule.save(ignore_permissions=True)
	except frappe.ValidationError:
		frappe.db.rollback(save_point=MERGE_SAVEPOINT)
		frappe.clear_last_message()
		log_merge_refused(service, shipping_rule, store_rule, "its bands clash with the store rule's")


def log_merge_refused(service: str, shipping_rule: str, store_rule: str, reason: str):
	frappe.log_error(
		title="Delivery option Shipping Rule not moved",
		message=f"Delivery option {service} used Shipping Rule {shipping_rule}, which could not be merged into "
		f"the store rule {store_rule} because {reason}. Add its bands to the store rule by hand.",
	)
