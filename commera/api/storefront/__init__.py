import frappe
from frappe.rate_limiter import rate_limit


def rate_limited_guest_api(method: str, *, limit: int, seconds: int, **options):
	"""A storefront endpoint guests may call with one HTTP `method`, rate limited per `rate_limit`."""

	def decorate(function):
		limited = rate_limit(limit=limit, seconds=seconds, **options)(function)
		return frappe.whitelist(allow_guest=True, methods=[method])(
			limited
		)  # nosemgrep: guest-whitelisted-method

	return decorate
