from dataclasses import dataclass, field

from frappe.utils import cstr

from commera.shopify.bulk import get_children

# Shopify gives a product without options one option "Title" with the single value "Default Title".
DEFAULT_OPTION_NAME = "Title"
DEFAULT_OPTION_VALUE = "Default Title"
SIZE_LABEL_SEPARATOR = " / "


@dataclass
class PageRow:
	"""One Shopify variant: the size label it gets in Commera, or None for a product without sizes."""

	size: str | None
	variant: dict


@dataclass
class ProductPlan:
	"""How one Shopify product lands in Commera's two axes: product pages and sizes."""

	page_option: str | None
	size_options: list[str]
	pages: dict[str, list[PageRow]] = field(default_factory=dict)

	@property
	def has_page_option(self) -> bool:
		return self.page_option is not None

	@property
	def joined_size_options(self) -> bool:
		return len(self.size_options) > 1

	def get_option_sizes(self, fallback_page_value: str) -> list[dict]:
		"""The option_sizes payload of catalog.create_product."""
		return [
			{
				"option": page_value if self.has_page_option else fallback_page_value,
				"sizes": [row.size for row in rows if row.size],
			}
			for page_value, rows in self.pages.items()
		]


def get_real_options(product: dict) -> list[dict]:
	options = sorted(product.get("options") or [], key=lambda option: option.get("position") or 0)
	return [option for option in options if not is_default_option(option)]


def is_default_option(option: dict) -> bool:
	values = [value.get("name") for value in option.get("optionValues") or []]
	return option.get("name") == DEFAULT_OPTION_NAME and values in ([DEFAULT_OPTION_VALUE], [])


def plan_product(product: dict, page_option_names: list[str]) -> ProductPlan:
	"""Pick the option that makes pages, and join every other option into the size label.

	`page_option_names` holds casefolded Shopify option names, for example ["color", "colour"].
	A product with no matching option gets one page, and all its options go to the size picker.
	"""
	option_names = [cstr(option["name"]) for option in get_real_options(product)]
	page_option = next((name for name in option_names if name.casefold() in page_option_names), None)
	plan = ProductPlan(page_option=page_option, size_options=[n for n in option_names if n != page_option])

	variants = sorted(
		get_children(product, "ProductVariant"), key=lambda variant: variant.get("position") or 0
	)
	for variant in variants:
		values = {
			cstr(option["name"]): cstr(option["value"]) for option in variant.get("selectedOptions") or []
		}
		page_value = values.get(page_option, "") if page_option else ""
		size_parts = [values[name] for name in plan.size_options if values.get(name)]
		size = SIZE_LABEL_SEPARATOR.join(size_parts) or None
		plan.pages.setdefault(page_value, []).append(PageRow(size=size, variant=variant))

	return plan
