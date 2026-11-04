frappe.ui.form.on('Shop Theme', {
	refresh(frm) {
		if (frm.is_new() || frm.doc.theme_settings) {
			return;
		}

		const settings_doctype = `${frm.doc.theme_name} Settings`;
		add_scaffold_button(frm, settings_doctype);
	},
});

async function add_scaffold_button(frm, settings_doctype) {
	const exists = await frappe.db.exists('DocType', settings_doctype);
	if (exists) {
		frm.dashboard.add_comment(
			__('DocType {0} already exists. Link it in the Theme Settings field.', [
				settings_doctype,
			]),
			'yellow',
			true,
		);
		return;
	}

	frm.add_custom_button(__('Scaffold Theme Settings'), () => {
		frappe.confirm(
			__('This will create a new DocType named {0}. Continue?', [
				settings_doctype,
			]),
			async () => {
				await frm.call('scaffold_theme_settings');
				frappe.show_alert({
					message: __('Creating {0}. This form refreshes when it is ready.', [
						settings_doctype,
					]),
					indicator: 'blue',
				});
			},
		);
	});
}
