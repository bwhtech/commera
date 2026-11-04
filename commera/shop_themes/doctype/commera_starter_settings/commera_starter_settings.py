# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CommeraStarterSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		brand_color: DF.Color | None
		brand_text_color: DF.Color | None
		color_scheme: DF.Literal["System", "Light", "Dark"]
		corners: DF.Literal["Square", "Subtle", "Default", "Rounded"]
		facebook_url: DF.Data | None
		font: DF.Data | None
		heading_font: DF.Data | None
		instagram_url: DF.Data | None
		logo: DF.AttachImage | None
		pinterest_url: DF.Data | None
		x_url: DF.Data | None
		youtube_url: DF.Data | None
	# end: auto-generated types

	pass
