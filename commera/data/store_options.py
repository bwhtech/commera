# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

EVERY_STORE_OPTIONS = {
	"Color": [
		"Black",
		"White",
		"Grey",
		"Navy",
		"Blue",
		"Red",
		"Green",
		"Yellow",
		"Pink",
		"Purple",
		"Brown",
		"Beige",
	],
	"Size": ["XS", "S", "M", "L", "XL", "XXL"],
}

CATEGORY_OPTIONS = {
	"Fashion": {
		"Material": ["Cotton", "Linen", "Wool", "Silk", "Denim", "Leather", "Polyester", "Viscose"],
		"Fit": ["Slim", "Regular", "Relaxed", "Oversized"],
		"Sleeve": ["Short", "Long", "Sleeveless"],
	},
	"Beauty": {
		"Shade": ["Fair", "Light", "Medium", "Tan", "Deep"],
		"Finish": ["Matte", "Dewy", "Satin", "Gloss", "Shimmer"],
		"Scent": ["Floral", "Citrus", "Woody", "Fresh", "Oriental"],
		"Volume": ["30 ml", "50 ml", "100 ml", "200 ml"],
	},
	"Home": {
		"Material": ["Wood", "Metal", "Glass", "Ceramic", "Rattan", "Cotton", "Linen"],
		"Finish": ["Matte", "Gloss", "Natural"],
		"Bed size": ["Single", "Double", "Queen", "King"],
	},
	"Food": {
		"Weight": ["100 g", "250 g", "500 g", "1 kg"],
		"Flavour": ["Original", "Spicy", "Sweet", "Salted"],
		"Pack size": ["Single", "Pack of 3", "Pack of 6", "Pack of 12"],
	},
	"Electronics": {
		"Storage": ["64 GB", "128 GB", "256 GB", "512 GB"],
		"Memory": ["4 GB", "6 GB", "8 GB", "12 GB"],
		"Connectivity": ["Wired", "Wireless"],
	},
}

# ERPNext's setup wizard seeds these long sizes; each is hidden from pickers while no product uses it and
# the short size it duplicates exists.
SUPERSEDED_VALUES = {
	"Size": {
		"Extra Small": "XS",
		"Small": "S",
		"Medium": "M",
		"Large": "L",
		"Extra Large": "XL",
	},
}
