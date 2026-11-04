"""GraphQL Admin API queries for 2026-10. Bulk queries allow five connections, two levels deep.
Each resource lists queries newest first; the next runs when Shopify says a field does not exist."""

SHOP_QUERY = """
{
	shop {
		name
		email
		contactEmail
		currencyCode
		myshopifyDomain
		primaryDomain { url host }
	}
}
"""

# limit: null asks for the exact count. The default stops counting at 10000.
COUNT_QUERIES = {
	"Products": "{ productsCount(limit: null) { count } }",
	"Collections": "{ collectionsCount(limit: null) { count } }",
	"Customers": "{ customersCount(limit: null) { count } }",
	"Pages": "{ pagesCount(limit: null) { count } }",
	"Redirects": "{ urlRedirectsCount(limit: null) { count } }",
	"Orders": "{ ordersCount(limit: null) { count } }",
	"Discounts": "{ discountNodesCount(limit: null) { count } }",
	"Gift cards": "{ giftCardsCount(limit: null) { count } }",
	"Blogs": "{ blogsCount(limit: null) { count } }",
}

PRODUCT_VARIANT_FIELDS = """
	id title sku price compareAtPrice inventoryQuantity inventoryPolicy position
	selectedOptions { name value }
	inventoryItem { tracked measurement { weight { unit value } } }
"""

# ProductVariant.barcode and image are deprecated in 2026-10, and their replacements would be a third
# bulk nesting level. The first query keeps them while they last; the second runs without them.
PRODUCT_VARIANT_DEPRECATED_FIELDS = " barcode image { url }"

PRODUCTS_QUERY = """
{
	products%(arguments)s {
		edges { node {
			id handle title descriptionHtml vendor productType tags status updatedAt
			seo { title description }
			options { name position optionValues { name } }
			media { edges { node {
				id mediaContentType alt
				... on MediaImage { image { url altText } }
			} } }
			variants { edges { node { VARIANT_FIELDS } } }
		} }
	}
}
"""

PRODUCT_QUERIES = [
	PRODUCTS_QUERY.replace("VARIANT_FIELDS", PRODUCT_VARIANT_FIELDS + PRODUCT_VARIANT_DEPRECATED_FIELDS),
	PRODUCTS_QUERY.replace("VARIANT_FIELDS", PRODUCT_VARIANT_FIELDS),
]

# Collection.ruleSet is deprecated in 2026-10. It is only read to tell smart collections apart.
COLLECTIONS_QUERY = """
{
	collections%(arguments)s {
		edges { node {
			id handle title descriptionHtml updatedAt
			RULE_SET
			image { url altText }
			seo { title description }
			products { edges { node { id } } }
		} }
	}
}
"""

COLLECTION_QUERIES = [
	COLLECTIONS_QUERY.replace("RULE_SET", "ruleSet { appliedDisjunctively }"),
	COLLECTIONS_QUERY.replace("RULE_SET", ""),
]

CUSTOMER_ADDRESS_FIELDS = """
	id address1 address2 city company countryCodeV2 firstName lastName phone province provinceCode zip
"""

# Customer.email, phone and addresses are deprecated in 2026-10. addressesV2 is a connection, so
# its addresses arrive as child lines of the customer.
CUSTOMER_QUERIES = [
	"""
{
	customers%(arguments)s {
		edges { node {
			id firstName lastName displayName note tags updatedAt
			defaultEmailAddress { emailAddress marketingState }
			defaultPhoneNumber { phoneNumber }
			defaultAddress { id }
			addressesV2 { edges { node { ADDRESS_FIELDS } } }
		} }
	}
}
""".replace("ADDRESS_FIELDS", CUSTOMER_ADDRESS_FIELDS),
	"""
{
	customers%(arguments)s {
		edges { node {
			id firstName lastName displayName note tags updatedAt email phone
			defaultAddress { id }
			addresses { ADDRESS_FIELDS }
		} }
	}
}
""".replace("ADDRESS_FIELDS", CUSTOMER_ADDRESS_FIELDS),
]

PAGE_QUERIES = [
	"""
{
	pages%(arguments)s {
		edges { node { id handle title body isPublished updatedAt } }
	}
}
"""
]

REDIRECT_QUERIES = [
	"""
{
	urlRedirects {
		edges { node { id path target } }
	}
}
"""
]


def build_query(template: str, changed_since_utc: str | None = None) -> str:
	"""Fill the connection arguments. Shopify's search syntax filters on updated_at."""
	arguments = f"(query: \"updated_at:>'{changed_since_utc}'\")" if changed_since_utc else ""
	return template.replace("%(arguments)s", arguments)
