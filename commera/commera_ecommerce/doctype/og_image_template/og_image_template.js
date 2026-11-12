// Copyright (c) 2026, company@bwhstudios.com and contributors
// For license information, please see license.txt

frappe.ui.form.on('OG Image Template', {
	refresh(frm) {
		// Preview needs a real docname to attach the generated image to.
		if (frm.is_new()) return;

		frm.add_custom_button(__('Generate Preview'), async () => {
			// Chromium takes a few seconds to render the card; freeze for feedback.
			frappe.dom.freeze(__('Generating preview…'));
			try {
				await frm.call('generate_preview');
				// Reload so the freshly-set preview_image renders in the form.
				await frm.reload_doc();
				frappe.show_alert({
					message: __('Preview generated'),
					indicator: 'green',
				});
			} finally {
				frappe.dom.unfreeze();
			}
		});
	},
});
