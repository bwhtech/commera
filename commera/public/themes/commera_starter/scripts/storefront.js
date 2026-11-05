function product_url(product) {
	return `/${document.documentElement.lang}/products/${encodeURIComponent(
		product.handle,
	)}`;
}

async function save_change(state, change, action = true) {
	state.busy = action;
	state.error = '';
	try {
		await change();
	} catch (error) {
		state.error = error.message;
	} finally {
		state.busy = false;
	}
}

async function save_change_and_leave(state, change, action = true) {
	state.busy = action;
	state.error = '';
	try {
		await change();
	} catch (error) {
		state.error = error.message;
		state.busy = false;
	}
}

function typeahead() {
	return {
		query: '',
		results: null,

		async search() {
			const query = this.query.trim();
			if (!query) {
				this.results = null;
				return;
			}
			const results = await commera.search.get_typeahead(query);
			if (query === this.query.trim()) {
				this.results = results;
			}
		},

		product_url,

		money(product) {
			return commera.format.money(product.price, product.currency);
		},
	};
}

function form_state() {
	return {
		busy: false,
		error: '',
		saved: false,

		async submit(change, action) {
			this.saved = false;
			await save_change(this, change, action);
		},
	};
}

function product_form(product) {
	return {
		...product,
		size: product.size,
		qty: 1,
		image: 0,
		busy: false,
		error: '',
		missing_size: false,
		saved: product.in_wishlist,
		add_button_visible: true,

		init() {
			new IntersectionObserver(([entry]) => {
				this.add_button_visible = entry.isIntersecting;
			}).observe(this.$refs.add_button);
			const url = new URL(location.href);
			if (url.searchParams.has('save_to_wishlist')) {
				url.searchParams.delete('save_to_wishlist');
				history.replaceState(null, '', url);
				if (!product.is_guest && !this.saved) {
					this.toggle_wishlist();
				}
			}
		},

		get size_option() {
			return product.options.find(
				(option) => !option.values.some((value) => value.handle),
			);
		},

		get variant() {
			const selected = this.size_option
				? { [this.size_option.name]: this.size }
				: {};
			return commera.product.select_variant(product, selected);
		},

		get price() {
			return this.variant?.price ?? product.price;
		},

		get compare_at_price() {
			return this.variant?.compare_at_price;
		},

		get discount() {
			return Math.round((1 - this.price / this.compare_at_price) * 100);
		},

		money(amount) {
			return commera.format.money(amount, product.currency);
		},

		move_image(step, count) {
			this.image = (this.image + step + count) % count;
		},

		save(change, action) {
			return save_change(this, change, action);
		},

		async add_to_cart() {
			this.missing_size = !this.variant;
			if (this.missing_size) {
				return;
			}
			await this.save(async () => {
				await commera.cart.add_lines([
					{ item_code: this.variant.id, qty: this.qty },
				]);
				Alpine.store('cart').open = true;
			}, 'add_to_cart');
		},

		async toggle_wishlist() {
			if (product.is_guest) {
				const url = new URL(location.href);
				url.searchParams.set('save_to_wishlist', '1');
				this.$dispatch('open-auth', { redirect: url.pathname + url.search });
				return;
			}
			await this.save(async () => {
				await (this.saved
					? commera.wishlist.remove(product.id)
					: commera.wishlist.add(product.id));
				this.saved = !this.saved;
			}, 'wishlist');
		},
	};
}

function accordion(section_id) {
	return {
		open: 'description',

		select(event) {
			if (event.detail.section !== section_id) {
				return;
			}
			const block = [
				...this.$root.querySelectorAll('[data-commera-block]'),
			].find((element) => element.dataset.commeraBlock === event.detail.id);
			if (block) {
				this.open = block.dataset.accordionKey;
			}
		},
	};
}

function listing_filters() {
	return {
		open: '',

		toggle(name) {
			this.open = this.open === name ? '' : name;
		},

		apply() {
			const values = {};
			for (const [key, value] of new FormData(this.$el)) {
				if (value !== '') {
					values[key] = values[key] ? `${values[key]},${value}` : value;
				}
			}
			const query = new URLSearchParams(values).toString();
			globalThis.location.assign(
				query ? `${this.$el.action}?${query}` : this.$el.action,
			);
		},
	};
}

function order_summary() {
	return {
		code: '',
		busy: false,
		error: '',

		get cart() {
			return this.$store.cart.cart;
		},

		get discount_codes() {
			return this.summary?.discount_codes ?? this.cart?.discount_codes ?? [];
		},

		get discounts() {
			return this.summary?.discounts ?? this.cart?.discounts ?? [];
		},

		get subtotal() {
			return (this.cart?.discounts ?? []).reduce(
				(subtotal, discount) => subtotal + discount.amount,
				this.cart?.total ?? 0,
			);
		},

		money(amount) {
			return this.$store.cart.money(amount);
		},

		async apply_code() {
			const code = this.code.trim();
			await save_change(
				this,
				async () => {
					await commera.cart.apply_discount(code);
					this.code = '';
				},
				'apply',
			);
		},

		async remove_code(code) {
			await save_change(
				this,
				() => commera.cart.remove_discount(code),
				`remove:${code}`,
			);
		},
	};
}

function blank_address(country) {
	return {
		first_name: '',
		last_name: '',
		address_line1: '',
		address_line2: '',
		city: '',
		state: '',
		pincode: '',
		country: country ?? '',
		phone: '',
	};
}

function address_form(address, country) {
	const form = blank_address(country);
	for (const key of Object.keys(form)) {
		form[key] = address[key] ?? form[key];
	}
	return form;
}

function checkout(config) {
	return {
		config,
		state: null,
		ready: false,
		sign_in_required: false,
		editing_address: true,
		email: config.email ?? '',
		delivery_method: 'ship',
		pickup_location: '',
		billing_same: true,
		choices: {
			shipping: config.saved_addresses[0] ?? 'new',
			billing: config.saved_addresses[0] ?? 'new',
		},
		forms: {
			shipping: blank_address(config.country),
			billing: blank_address(config.country),
		},
		shipping_options: [],
		shipping_reason: null,
		payment_methods: [],
		payment_method: '',
		summary_open: false,
		step: 'address',
		busy: false,
		error: '',

		async init() {
			globalThis.addEventListener('commera:cart-updated', () => this.refresh());
			try {
				this.state = await commera.checkout.get();
			} catch (error) {
				this.sign_in_required = error.status === 403;
				this.error = error.message;
			}
			if (this.state) {
				this.restore_state();
			}
			if (!this.editing_address) {
				await this.load_options();
			}
			this.ready = true;
		},

		restore_state() {
			const { state } = this;
			if (state.email && this.config.is_guest) {
				this.email = state.email;
			}
			if (state.is_store_pickup) {
				this.delivery_method = 'pickup';
				this.pickup_location = state.store;
			} else if (state.shipping_address) {
				this.restore_address('shipping', state.shipping_address);
				this.billing_same =
					state.billing_address?.name === state.shipping_address.name;
				if (!this.billing_same && state.billing_address) {
					this.restore_address('billing', state.billing_address);
				}
			}
			this.editing_address = !(state.is_store_pickup || state.shipping_address);
		},

		restore_address(kind, address) {
			if (this.config.saved_addresses.includes(address.name)) {
				this.choices[kind] = address.name;
				return;
			}
			this.choices[kind] = 'new';
			this.forms[kind] = address_form(address, this.config.country);
		},

		async refresh() {
			if (!this.state) {
				return;
			}
			await save_change(this, async () => {
				this.state = await commera.checkout.get();
				if (!this.editing_address) {
					await this.load_options();
				}
			});
		},

		async load_options() {
			const [shipping, payment_methods] = await Promise.all([
				this.state?.is_store_pickup
					? { options: [], reason: 'store_pickup' }
					: commera.checkout.list_shipping_options(),
				commera.checkout.list_payment_methods(),
			]);
			this.shipping_options = shipping.options;
			this.shipping_reason = shipping.reason;
			this.payment_methods = payment_methods;
			if (
				!payment_methods.some((method) => method.id === this.payment_method)
			) {
				this.payment_method = payment_methods[0]?.id ?? '';
			}
		},

		address_input(kind) {
			return this.choices[kind] === 'new'
				? { ...this.forms[kind] }
				: this.choices[kind];
		},

		async save_address() {
			this.step = 'address';
			const email = this.config.is_guest ? this.email.trim() : undefined;
			await save_change(
				this,
				async () => {
					this.state =
						this.delivery_method === 'pickup'
							? await commera.checkout.set_store_pickup({
									warehouse: this.pickup_location,
									email,
							  })
							: await commera.checkout.set_addresses({
									billing_address: this.address_input(
										this.billing_same ? 'shipping' : 'billing',
									),
									shipping_address: this.billing_same
										? undefined
										: this.address_input('shipping'),
									email,
							  });
					await this.load_options();
					this.editing_address = false;
				},
				'address',
			);
		},

		async choose_shipping_option(option_id) {
			this.step = 'shipping';
			await save_change(
				this,
				async () => {
					this.state = await commera.checkout.set_shipping_option(option_id);
					this.payment_methods = await commera.checkout.list_payment_methods();
				},
				`shipping:${option_id}`,
			);
		},

		async pay() {
			this.step = 'payment';
			this.busy = 'pay';
			this.error = '';
			try {
				const session = await commera.checkout.start_payment({
					payment_method: this.payment_method,
					expected_total: this.total,
				});
				globalThis.location.assign(session.redirect_url);
			} catch (error) {
				this.error = error.message;
				this.busy = false;
				if (error.exc_type === 'CheckoutPriceChangedError') {
					await this.refresh();
				}
			}
		},

		get is_cash_on_delivery() {
			return this.payment_methods.some(
				(method) =>
					method.id === this.payment_method && method.is_cash_on_delivery,
			);
		},

		get summary() {
			const summary = this.state?.summary;
			return this.is_cash_on_delivery ? summary?.cash_on_delivery : summary;
		},

		get total() {
			const total = this.summary?.total ?? this.$store.cart.cart?.total ?? 0;
			return this.shipping_pending
				? total - (this.summary?.shipping ?? 0)
				: total;
		},

		get shipping_amount() {
			return (this.summary?.shipping_discounts ?? []).reduce(
				(shipping, discount) => shipping + discount.amount,
				this.summary?.shipping ?? 0,
			);
		},

		get needs_shipping_option() {
			return (
				!this.state?.is_store_pickup &&
				this.shipping_options.length > 0 &&
				!this.state?.shipping_option
			);
		},

		get shipping_pending() {
			return this.editing_address || this.needs_shipping_option;
		},

		get address_recap() {
			if (this.state?.is_store_pickup) {
				return this.config.pickup_titles[this.state.store] ?? this.state.store;
			}
			const address = this.state?.shipping_address ?? {};
			return [
				address.address_line1,
				address.address_line2,
				address.city,
				address.state,
				address.pincode,
				address.country,
			]
				.filter(Boolean)
				.join(', ');
		},

		money(amount) {
			return this.$store.cart.money(amount);
		},
	};
}

function order_confirmation() {
	return {
		status: 'checking',
		order: null,
		details: null,

		async init() {
			const params = new URLSearchParams(globalThis.location.search);
			const reference_id =
				params.get('reference_id') ??
				params.get('payment_id') ??
				params.get('session_id');
			if (!reference_id) {
				this.status = 'failed';
				return;
			}
			let result;
			try {
				result = await commera.checkout.complete(reference_id);
			} catch {
				this.status = 'failed';
				return;
			}
			const [cart, details] = await Promise.all([
				commera.cart.get().catch(() => null),
				result.order ? this.get_details(result.order) : null,
			]);
			if (cart) {
				Alpine.store('cart').cart = cart;
			}
			this.order = result.order;
			this.details = details;
			this.status =
				{ Paid: 'paid', Pending: 'pending' }[result.status] ?? 'failed';
		},

		get_details(order) {
			const key = new URL(
				order.link,
				globalThis.location.origin,
			).searchParams.get('key');
			return commera.account
				.get_order(order.name, key ?? undefined)
				.catch(() => null);
		},

		money(amount) {
			return commera.format.money(amount, this.order?.currency);
		},
	};
}

document.addEventListener('alpine:init', () => {
	Alpine.store('cart', {
		cart: null,
		open: false,
		busy: false,
		error: '',

		get count() {
			return this.cart?.total_quantity ?? 0;
		},

		async init() {
			globalThis.addEventListener('commera:cart-updated', (event) => {
				this.cart = event.detail;
			});
			this.cart = await commera.cart.get();
		},

		save(change, action) {
			return save_change(this, change, action);
		},

		async set_quantity(line, qty) {
			await this.save(
				() => commera.cart.update_lines([{ line_id: line.line_id, qty }]),
				`quantity:${line.line_id}`,
			);
		},

		async remove(line) {
			await this.save(
				() => commera.cart.remove_lines([line.line_id]),
				`remove:${line.line_id}`,
			);
		},

		async checkout() {
			await save_change_and_leave(
				this,
				() => commera.cart.go_to_checkout(),
				'checkout',
			);
		},

		money(amount) {
			return commera.format.money(amount, this.cart?.currency);
		},

		product_url,
	});

	Alpine.data('typeahead', typeahead);
	Alpine.data('product_form', product_form);
	Alpine.data('listing_filters', listing_filters);
	Alpine.data('accordion', accordion);
	Alpine.data('order_summary', order_summary);
	Alpine.data('checkout', checkout);
	Alpine.data('order_confirmation', order_confirmation);

	Alpine.data('search_modal', () => ({
		...typeahead(),
		open: false,

		show() {
			this.open = true;
			this.$nextTick(() => this.$refs.search_input.focus());
		},
	}));

	Alpine.data('wishlist', (count) => ({
		...form_state(),
		count,
		removed: [],

		async remove(product) {
			await this.submit(async () => {
				const wishlist = await commera.wishlist.remove(product);
				this.removed.push(product);
				this.count = wishlist.count;
			}, `remove:${product}`);
		},
	}));

	Alpine.data('profile_form', (profile) => ({
		...form_state(),
		profile,

		async save() {
			await this.submit(async () => {
				this.profile = await commera.account.update_profile(this.profile);
				this.saved = true;
			});
		},
	}));

	Alpine.data('address_book', (addresses) => ({
		...form_state(),
		addresses,
		form: null,

		edit(address = {}) {
			this.error = '';
			this.form = { ...address };
		},

		close() {
			this.error = '';
			this.form = null;
		},

		async save() {
			await this.submit(async () => {
				await commera.account.save_address(this.form);
				this.addresses = await commera.account.list_addresses();
				this.form = null;
			});
		},

		async remove(address) {
			await this.submit(async () => {
				await commera.account.delete_address(address.name);
				this.addresses = this.addresses.filter(
					(entry) => entry.name !== address.name,
				);
			}, `remove:${address.name}`);
		},
	}));

	Alpine.data('auth_form', ({ mode, redirect }) => ({
		...form_state(),
		mode,
		redirect,
		step: 'details',
		first_name: '',
		last_name: '',
		email: '',
		code: '',
		resent: false,

		switch_mode(next_mode) {
			this.mode = next_mode;
			this.step = 'details';
			this.code = '';
			this.error = '';
		},

		async request_code() {
			if (this.mode === 'login') {
				await commera.auth.send_login_code(this.email);
			} else {
				await commera.auth.send_signup_code({
					email: this.email,
					first_name: this.first_name,
					last_name: this.last_name,
				});
			}
		},

		async send_code() {
			await this.submit(async () => {
				await this.request_code();
				this.resent = false;
				this.code = '';
				this.step = 'code';
			}, 'send');
		},

		async resend_code() {
			await this.submit(async () => {
				await this.request_code();
				this.resent = true;
			}, 'resend');
		},

		async verify() {
			this.resent = false;
			await save_change_and_leave(
				this,
				async () => {
					if (this.mode === 'login') {
						await commera.auth.log_in({ email: this.email, code: this.code });
					} else {
						await commera.auth.sign_up({
							email: this.email,
							first_name: this.first_name,
							last_name: this.last_name,
							code: this.code,
						});
					}
					if (this.redirect) {
						location.assign(this.redirect);
					} else {
						location.reload();
					}
				},
				'verify',
			);
		},
	}));

	Alpine.data('log_out_button', () => ({
		busy: false,
		error: '',

		async log_out() {
			await save_change_and_leave(this, async () => {
				await commera.auth.log_out();
				location.assign(`/${document.documentElement.lang}`);
			});
		},
	}));

	Alpine.data('order_detail', ({ name, key, is_owner, is_cancelled }) => ({
		...form_state(),
		tracking: {},
		returns: {},
		invoice_url: null,
		confirm_cancel: false,
		show_return: false,
		selected: [],
		reasons: {},
		item_codes: [],

		async init() {
			this.item_codes = [...this.$el.querySelectorAll('[data-item]')].map(
				(element) => element.dataset.item,
			);
			this.tracking = await commera.orders.get_tracking(name, key);
			if (is_owner && !is_cancelled) {
				[this.returns, this.invoice_url] = await Promise.all([
					commera.orders.get_return_options(name),
					commera.orders.get_invoice_url(name),
				]);
			}
		},

		get returnable_codes() {
			const locked = [
				...(this.returns.returned_items ?? []),
				...(this.returns.pending_items ?? []),
			];
			return this.item_codes.filter((item_code) => !locked.includes(item_code));
		},

		async cancel() {
			await this.submit(async () => {
				await commera.orders.cancel(name);
				location.reload();
			});
		},

		async request_return() {
			await this.submit(async () => {
				this.returns = await commera.orders.request_return(
					name,
					this.selected.map((item_code) => ({
						item_code,
						reason: this.reasons[item_code],
					})),
				);
				this.selected = [];
				this.show_return = false;
			});
		},
	}));

	Alpine.data('track_order', () => ({
		...form_state(),
		order_number: '',
		email: '',
		message: '',

		async send() {
			await this.submit(async () => {
				this.message = await commera.orders.send_order_link({
					order_number: this.order_number,
					email: this.email,
				});
			});
		},
	}));

	Alpine.data('hero', (slide_count) => ({
		slide: 0,
		selected: false,

		init() {
			this.$el.addEventListener('commera:block:select', (event) => {
				const slides = [...this.$el.querySelectorAll('[data-commera-block]')];
				const index = slides.indexOf(event.target);
				if (index === -1) return;
				this.slide = index;
				this.selected = true;
			});
			this.$el.addEventListener('commera:block:deselect', () => {
				this.selected = false;
			});
			if (
				slide_count < 2 ||
				matchMedia('(prefers-reduced-motion: reduce)').matches
			) {
				return;
			}
			setInterval(() => {
				if (!this.selected) this.slide = (this.slide + 1) % slide_count;
			}, 5000);
		},
	}));
});
