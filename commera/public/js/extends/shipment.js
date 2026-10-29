// Carrier actions on a Shipment. Every button is gated on the state the document is actually in, so an
// operator cannot double-book a parcel or ask a carrier for something it cannot do.
frappe.ui.form.on('Shipment', {
	refresh(frm) {
		const provider = frm.doc.custom_shipping_provider;
		if (frm.doc.__islocal || !provider || frm.doc.docstatus === 2) return;

		if (!frm.doc.awb_number) {
			const resuming = Boolean(frm.doc.custom_order_ref);
			frm.add_custom_button(
				resuming ? __('Resume Booking') : __('Buy Label'),
				() =>
					confirm_and_run(
						frm,
						resuming
							? __('Finish the booking already open at {0}?', [provider])
							: __('Book this parcel with {0}? This buys a real label.', [
									provider,
							  ]),
						'book',
					),
			);
		}

		if (frm.doc.awb_number) {
			frm.add_custom_button(__('Sync Status'), () => run(frm, 'sync_status'));

			if (frm.doc.custom_label_url) {
				frm.add_custom_button(__('Print Label'), () =>
					window.open(frm.doc.custom_label_url, '_blank'),
				);
			}

			frm.add_custom_button(__('Schedule Pickup'), () =>
				confirm_and_run(
					frm,
					__('Ask the carrier to collect this parcel? A courier will be sent.'),
					'schedule_pickup',
				),
			);

			frm.add_custom_button(__('Generate Manifest'), () =>
				run(frm, 'generate_manifest'),
			);

			if (frm.doc.custom_manifest_url) {
				frm.add_custom_button(__('Print Manifest'), () =>
					window.open(frm.doc.custom_manifest_url, '_blank'),
				);
			}
		}

		// Mirrors CANCELLABLE_STATUSES on the server, which still refuses anything later.
		if (
			frm.doc.custom_order_ref &&
			['Draft', 'Ready To Ship', 'Pickup Scheduled'].includes(
				frm.doc.custom_shipment_status,
			)
		) {
			frm.add_custom_button(__('Cancel With Carrier'), () =>
				confirm_and_run(
					frm,
					__('Cancel this shipment with {0}?', [provider]),
					'cancel_booking',
				),
			);
		}
	},
});

function confirm_and_run(frm, message, method) {
	// Booking, pickup and cancellation reach a carrier and cost money or send a van.
	frappe.confirm(message, () => run(frm, method));
}

function run(frm, method) {
	frm
		.call({
			doc: frm.doc,
			method,
			freeze: true,
			freeze_message: __('Talking to the carrier...'),
		})
		.then(() => frm.reload_doc());
}
