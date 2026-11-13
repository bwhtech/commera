from commera.commera_ecommerce.doctype.commera_settings.commera_settings import validate_store_price_list
from commera.localization.market_setup import validate_price_list as validate_market_price_list


def validate(doc, method=None):
	validate_store_price_list(doc)
	validate_market_price_list(doc)
