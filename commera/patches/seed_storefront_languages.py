from commera.localization.languages import seed_storefront_languages


def execute():
	# Every store before this patch served /en/ and /ar/, with English at the root redirect.
	seed_storefront_languages("en", ("en", "ar"))
