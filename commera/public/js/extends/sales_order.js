frappe.ui.form.on('Sales Order', {
	async refresh(frm) {
		// Remove existing button to avoid duplication
		frm.clear_custom_buttons();
		if (frm.doc.docstatus === 0) {
			return;
		}

		const response = await get_refund_status(frm.doc.name);

		const r = response;
		if (!r || !r.can_refund) {
			return;
		}

		frm.add_custom_button(__('Refund'), () => {
			const d = new frappe.ui.Dialog({
				title: 'Refund Options',
				fields: [
					{
						fieldname: 'original_amount',
						label: !r.only_charges
							? 'Refund Original Amount'
							: 'Refund Charges',
						fieldtype: 'Check',
						default: 1,
						read_only: 1,
					},
					...(!r.only_charges && frm.doc.total_taxes_and_charges
						? [
								{
									fieldname: 'refund_charges',
									label: 'Refund Charges',
									fieldtype: 'Check',
									default: 1,
									change: () => {
										const checked = d.get_value('refund_charges');
										const new_amount = checked
											? r.refundable_amount
											: frm.doc.net_total - r.amount_refunded;

										d.set_value('refund_amount', new_amount);
									},
								},
						  ]
						: []),
					{
						fieldname: 'refund_amount',
						label: 'Refund Amount',
						fieldtype: 'Currency',
						default: r.refundable_amount ? r.refundable_amount : frm.doc.total,
						reqd: 1,
						change: () => {
							const value = d.get_value('refund_amount');
							const max = r.only_charges
								? r.refundable_amount
								: r.refundable_amount
								  ? r.refundable_amount + frm.doc.total_taxes_and_charges
								  : frm.doc.grand_total;
							if (value <= 0) {
								frappe.msgprint(
									__('Min refund amount should be greater than 0'),
								);
								if (!r.only_charges) {
									d.set_value('refund_charges', 0);
								}
								d.set_value('refund_amount', max);
							}
							if (value > max) {
								frappe.msgprint(__('Max refund amount is {0}', [max]));
								if (!r.only_charges) {
									d.set_value('refund_charges', 1);
								}

								d.set_value('refund_amount', max);
							}
						},
					},
				],
				primary_action_label: 'Proceed with Refund',
				primary_action(values) {
					const amount = values.refund_amount;
					const max = r.refundable_amount || frm.doc.grand_total;

					if (amount < 0 || amount > max) {
						frappe.msgprint(
							__('Refund amount must be between 0 and {0}.', [max]),
						);
						return;
					}

					d.hide();
					confirm_and_process_refund(frm, amount);
				},
			});

			d.show();
		});
	},
});

async function get_refund_status(order_id) {
	try {
		const res = await frappe.call({
			method: 'commera.api.orders.get_sales_order_refund_status',
			args: { order_id },
		});
		return res.message;
	} catch (err) {
		return;
	}
}

async function confirm_and_process_refund(frm, amount) {
	frappe.confirm('Are you sure you want to refund?', async () => {
		const response = await frappe.call({
			method: 'commera.api.orders.create_refund_payment_entry',
			args: {
				order_id: frm.doc.name,
				amount: amount,
			},
		});

		if (response.message) {
			frappe.msgprint(
				__(
					"Refund Payment Entry <a href='/app/payment-entry/{0}'>{1}</a> created",
					[response.message, response.message],
				),
			);
			frm.reload_doc();
		}
	});
}
