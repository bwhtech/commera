// Bulk-create Shipping Services from what a carrier account actually sells.

frappe.listview_settings['Shipping Service'] = {
	onload(list_view) {
		list_view.page.add_inner_button(__('Import from Carrier'), () =>
			open_carrier_import_dialog(list_view),
		);
	},
};

async function open_carrier_import_dialog(list_view) {
	// run_doc_method so the call checks read permission on AfterShip Shipping Settings.
	const choices = await frappe.xcall('run_doc_method', {
		dt: 'AfterShip Shipping Settings',
		method: 'get_service_choices',
	});

	const accounts = choices?.accounts || [];
	if (!accounts.length) {
		frappe.msgprint(
			__(
				'No carrier can ship from your pickup country. Check the shipper accounts on the key, and the Pickup Address in AfterShip Shipping Settings.',
			),
		);
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __('Import from Carrier'),
		size: 'large',
		fields: get_dialog_fields(accounts),
		primary_action_label: __('Add Selected'),
		async primary_action() {
			await save_selected_services(list_view, dialog, choices);
			dialog.hide();
		},
	});
	dialog.show();
}

function get_dialog_fields(accounts) {
	const fields = [
		{
			fieldtype: 'Currency',
			fieldname: 'default_rate',
			label: __('Default Rate'),
			description: __(
				"Backup Charge set on each imported service — what it costs when no band on the store's Shipping Rule covers the cart and the carrier gives no live quote. Leave it at 0 to price them yourself later.",
			),
		},
	];

	for (const [index, account] of accounts.entries()) {
		fields.push({ fieldtype: 'Section Break', label: account.description });
		fields.push({
			fieldtype: 'MultiCheck',
			fieldname: `services_${index}`,
			columns: 2,
			options: account.services.map((service) => ({
				label: service.service_name,
				value: service.service_code,
			})),
		});
	}
	return fields;
}

async function save_selected_services(list_view, dialog, choices) {
	const selections = get_selections(dialog, choices.accounts);
	if (!selections.length) {
		frappe.msgprint(__('Select at least one service to import.'));
		return;
	}

	const created = await frappe.xcall(
		'commera.shipping.doctype.shipping_service.shipping_service.create_shipping_services',
		{
			provider: choices.provider,
			selections: selections,
			default_rate: dialog.get_value('default_rate') || 0,
		},
	);

	list_view.refresh();
	frappe.show_alert({
		message: __('Created {0} service(s).', [created.length]),
		indicator: created.length ? 'green' : 'orange',
	});
}

function get_selections(dialog, accounts) {
	const selections = [];
	for (const [index, account] of accounts.entries()) {
		const selected = dialog.get_value(`services_${index}`) || [];
		for (const service_code of selected) {
			const service = account.services.find(
				(item) => item.service_code === service_code,
			);
			selections.push({
				service_code: service_code,
				service_name: service.service_name,
				carrier: account.carrier,
			});
		}
	}
	return selections;
}
