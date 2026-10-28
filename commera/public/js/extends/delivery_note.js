// Start a shipment from a submitted Delivery Note. The button only appears once the note is submitted:
// booking a carrier against a draft would commit a real consignment for goods nobody has agreed to send.
frappe.ui.form.on('Delivery Note', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__('Shipment'),
			() => {
				frappe.call({
					method: 'commera.shipping.fulfilment.create_shipping_request',
					args: { delivery_note: frm.doc.name },
					freeze: true,
					freeze_message: __('Drafting shipment...'),
					callback(response) {
						if (!response.message) return;
						frappe.set_route('Form', 'Shipping Request', response.message);
					},
				});
			},
			__('Create'),
		);
	},
});
