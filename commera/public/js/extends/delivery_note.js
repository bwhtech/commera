frappe.ui.form.on('Delivery Note', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__('Shipment'),
			() => {
				frappe.call({
					method: 'commera.shipping.fulfilment.create_shipment',
					args: { delivery_note: frm.doc.name },
					freeze: true,
					freeze_message: __('Drafting shipment...'),
					callback(response) {
						if (!response.message) return;
						frappe.set_route('Form', 'Shipment', response.message);
					},
				});
			},
			__('Create'),
		);
	},
});
