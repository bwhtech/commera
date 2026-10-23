from commera.patches.drop_frozen_order_field_order import drop_shipped_setters

SHIPPED_LAYOUT_SETTERS = {
	"Item Group-main-field_order": "038a79562519da4c3df7a8e3921ae0c92e5e61cdcfece60c4cbf020081363ca9",
	"Warehouse-main-field_order": "e8383bbfbc9aa55ae2f4bc3bc5a01edc6a7bb87d9c61defc8575881e9c97b384",
	"Brand-main-field_order": "74540ff8ff75b505f5a93d21c825f6e067bc4fd527ea89ffd72d8d70544333ec",
	"Delivery Note Item-main-field_order": "fee5d0443313a385bd608a5138106f7e883e29c3834275eaee8f9c2e4f5aafbb",
}


def execute():
	drop_shipped_setters(SHIPPED_LAYOUT_SETTERS)
