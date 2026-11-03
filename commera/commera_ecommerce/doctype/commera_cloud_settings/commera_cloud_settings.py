from frappe.model.document import Document


class CommeraCloudSettings(Document):
	"""This site's link to Commera Cloud. Written only by the link job in `commera.cloud.link`."""

	@property
	def site_key_value(self) -> str | None:
		return self.get_password("site_key", raise_exception=False)
