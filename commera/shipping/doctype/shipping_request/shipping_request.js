// Desk actions for a Shipping Request. Every button is gated on the state the document is actually in,
// so an operator cannot double-book a parcel or ask a provider for something it cannot do.
frappe.ui.form.on('Shipping Request', {
	refresh(frm) {
		if (frm.doc.__islocal || !frm.doc.provider) return;

		if (!frm.doc.awb) {
			const resuming = Boolean(frm.doc.order_ref);
			frm.add_custom_button(
				resuming ? __('Resume Booking') : __('Book Shipment'),
				() =>
					confirm_and_run(
						frm,
						resuming
							? __('Finish the booking already open at {0}?', [
									frm.doc.provider,
							  ])
							: __('Book this parcel with {0}? This buys a real label.', [
									frm.doc.provider,
							  ]),
						'book',
					),
			);
		}

		if (frm.doc.awb) {
			frm.add_custom_button(__('Sync Status'), () => run(frm, 'sync_status'));

			if (frm.doc.label_url) {
				frm.add_custom_button(__('Print Label'), () =>
					window.open(frm.doc.label_url, '_blank'),
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

			if (frm.doc.manifest_url) {
				frm.add_custom_button(__('Print Manifest'), () =>
					window.open(frm.doc.manifest_url, '_blank'),
				);
			}
		}

		// Cancellable statuses mirror CANCELLABLE_STATUSES on the server; the server is still the authority
		// and refuses anything later, this only keeps a dead button off the form.
		if (
			frm.doc.order_ref &&
			['Draft', 'Ready To Ship', 'Pickup Scheduled'].includes(frm.doc.status)
		) {
			frm.add_custom_button(__('Cancel With Carrier'), () =>
				confirm_and_run(
					frm,
					__('Cancel this shipment with {0}?', [frm.doc.provider]),
					'cancel_booking',
				),
			);
		}

		if (frm.doc.awb) {
			frm.dashboard.add_indicator(
				__('AWB {0}', [frm.doc.awb]),
				frm.doc.status === 'Delivered' ? 'green' : 'blue',
			);
		}
	},
});

function confirm_and_run(frm, message, method) {
	// Booking, pickup and cancellation all reach a carrier and cost money or send a van, so none of them
	// happen on a single stray click.
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
