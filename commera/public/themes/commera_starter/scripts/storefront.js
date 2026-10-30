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
