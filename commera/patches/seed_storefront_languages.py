import frappe

# Every store before this patch served /en/ and /ar/, with English at the root redirect.
LANGUAGES = ("en", "ar")


def execute():
	settings = frappe.get_single("Commera Settings")
	if settings.storefront_languages:
		return

	settings.default_storefront_language = settings.default_storefront_language or LANGUAGES[0]
	for code in LANGUAGES:
		if frappe.db.exists("Language", code):
			settings.append("storefront_languages", {"language": code, "published": 1})

	# Skip validate: an unrelated setting, such as no payment method, must not block migrate.
	settings.flags.ignore_validate = True
	settings.save(ignore_permissions=True)
