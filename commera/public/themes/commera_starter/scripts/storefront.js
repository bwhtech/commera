function product_url(product) {
	return `/${document.documentElement.lang}/products/${encodeURIComponent(
		product.handle,
	)}`;
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

		async save(change) {
			this.busy = true;
			this.error = '';
			try {
				await change();
			} catch (error) {
				this.error = error.message;
			} finally {
				this.busy = false;
			}
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

		async save(change) {
			this.busy = true;
			this.error = '';
			try {
				await change();
			} catch (error) {
				this.error = error.message;
			} finally {
				this.busy = false;
			}
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

	Alpine.data('search_modal', () => ({
		...typeahead(),
		open: false,

		show() {
			this.open = true;
			this.$nextTick(() => this.$refs.search_input.focus());
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
