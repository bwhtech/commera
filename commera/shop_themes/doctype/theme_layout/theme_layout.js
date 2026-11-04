frappe.ui.form.on('Theme Layout', {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.draft_layout) {
			return;
		}
		frm.add_custom_button(__('Publish'), async () => {
			if (frm.is_dirty()) {
				await frm.save();
			}
			await frm.call('publish');
			frm.reload_doc();
			frappe.show_alert({
				message: __('Layout published'),
				indicator: 'green',
			});
		});
	},
});
