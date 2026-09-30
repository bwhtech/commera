import frappe
from frappe.modules.utils import sync_customizations

BAND_FIELDS = ("from_value", "to_value", "shipping_amount", "free_shipping")
MERGE_SAVEPOINT = "move_service_shipping_rule"
NOT_MOVED_TITLE = "Delivery option Shipping Rule not moved"


def execute():
	"""Delivery options used to carry their own Shipping Rule; now the store rule's bands name the option."""
	if "bwh_shipping" not in frappe.get_installed_apps():
		return
	# Customizations sync after post_model_sync patches, so the band's shipping_service column may not exist yet.
	sync_customizations("bwh_shipping")
	move_service_shipping_rules_to_store_rule(get_legacy_service_rules())


def get_legacy_service_rules() -> dict[str, str]:
	"""The Shipping Rule each delivery option carried, from the column the doctype no longer declares."""
	if not frappe.db.has_column("Shipping Service", "shipping_rule"):
		return {}

	service = frappe.qb.DocType("Shipping Service")
	rows = (
		frappe.qb.from_(service)
		.select(service.name, service.shipping_rule)
		.where(service.shipping_rule.isnotnull() & (service.shipping_rule != ""))
		.orderby(service.creation)
		.run(as_dict=True)
	)
	return {row.name: row.shipping_rule for row in rows}


def move_service_shipping_rules_to_store_rule(legacy_rules: dict[str, str]):
	if not legacy_rules:
		return

	store_rule = frappe.db.get_single_value("Commera Settings", "shipping_rule")
	if not store_rule:
		# Setting one here would switch on the flat store-rule tax row for carts with no option chosen.
		frappe.log_error(
			title=NOT_MOVED_TITLE,
			message=f"No store Shipping Rule is set, so the delivery options' rules were not moved: "
			f"{format_service_rules(legacy_rules)}. Pick the store rule in Commera Settings and add "
			"each option's bands to it.",
		)
		return

	for shipping_rule, services in get_services_by_enabled_rule(legacy_rules).items():
		if shipping_rule == store_rule:
			stamp_store_rule_bands(store_rule, services)
		else:
			for service in services:
				merge_service_rule(store_rule, shipping_rule, service)


def get_services_by_enabled_rule(legacy_rules: dict[str, str]) -> dict[str, list[str]]:
	enabled_rules = set(
		frappe.get_all(
			"Shipping Rule",
			filters={"name": ["in", list(set(legacy_rules.values()))], "disabled": 0},
			pluck="name",
		)
	)
	services_by_rule = {}
	for service, shipping_rule in legacy_rules.items():
		if shipping_rule in enabled_rules:
			services_by_rule.setdefault(shipping_rule, []).append(service)
		else:
			log_not_moved(service, shipping_rule, "it is disabled or no longer exists")
	return services_by_rule


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
	if service_rule.calculate_based_on == "Fixed" or not service_rule.conditions:
		log_not_moved(service, shipping_rule, "it has no bands to merge into the store rule")
		return
	if (service_rule.calculate_based_on, service_rule.company) != (rule.calculate_based_on, rule.company):
		log_not_moved(
			service, shipping_rule, f"it is based on a different figure or company than {store_rule}"
		)
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
		log_not_moved(service, shipping_rule, f"its bands clash with those of {store_rule}")


def log_not_moved(service: str, shipping_rule: str, reason: str):
	frappe.log_error(
		title=NOT_MOVED_TITLE,
		message=f"Delivery option {service} used Shipping Rule {shipping_rule}, which was not moved onto the "
		f"store rule because {reason}. The option loses that pricing until its bands are added by hand.",
	)


def format_service_rules(legacy_rules: dict[str, str]) -> str:
	return ", ".join(f"{service} ({shipping_rule})" for service, shipping_rule in legacy_rules.items())
