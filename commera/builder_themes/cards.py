from commera.sdk.format import image_url, money, product_url

CARD_IMAGE_WIDTH = 640


def get_cards(cards: list[dict]) -> list[dict]:
	return [get_card(card) for card in cards]


def get_card(card: dict) -> dict:
	compare_at = card["compare_at_price"]
	return {
		"title": card["title"],
		"url": product_url(card["handle"]),
		"image": image_url(card["image"], CARD_IMAGE_WIDTH) or "",
		"hover_image": image_url(card["hover_image"], CARD_IMAGE_WIDTH) or "",
		"vendor": card["vendor"] or "",
		"color": card["color"] or "",
		"price": money(card["price"], card["currency"]),
		"compare_at_price": money(compare_at, card["currency"]) if compare_at else "",
		"is_on_sale": bool(compare_at),
		"is_available": card["available"],
		"rating": card["rating"]["average"],
		"review_count": card["rating"]["count"],
	}
