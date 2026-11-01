function product_url(product) {
	return `/${document.documentElement.lang}/products/${encodeURIComponent(
		product.handle,
	)}`;
}

async function save_change(state, change) {
	state.busy = true;
	state.error = '';
	try {
		await change();
	} catch (error) {
		state.error = error.message;
	} finally {
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

		async submit(change) {
			this.saved = false;
			await save_change(this, change);
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

		save(change) {
			return save_change(this, change);
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
			});
		},

		async toggle_wishlist() {
			if (product.is_guest) {
				globalThis.location.assign(
					`/login?redirect-to=${encodeURIComponent(location.pathname)}`,
				);
				return;
			}
			await this.save(async () => {
				await (this.saved
					? commera.wishlist.remove(product.id)
					: commera.wishlist.add(product.id));
				this.saved = !this.saved;
			});
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
			await save_change(this, async () => {
				await commera.cart.apply_discount(code);
				this.code = '';
			});
		},

		async remove_code(code) {
			await save_change(this, () => commera.cart.remove_discount(code));
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

		save(change) {
			return save_change(this, change);
		},

		async set_quantity(line, qty) {
			await this.save(() =>
				commera.cart.update_lines([{ line_id: line.line_id, qty }]),
			);
		},

		async remove(line) {
			await this.save(() => commera.cart.remove_lines([line.line_id]));
		},

		async checkout() {
			await this.save(() => commera.cart.go_to_checkout());
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
			});
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

		init() {
			if (
				slide_count < 2 ||
				matchMedia('(prefers-reduced-motion: reduce)').matches
			) {
				return;
			}
			setInterval(() => {
				this.slide = (this.slide + 1) % slide_count;
			}, 5000);
		},
	}));
});
