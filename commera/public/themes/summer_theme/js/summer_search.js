/* Typeahead state for the search canvas. Loaded synchronously from the canvas markup: Alpine's
   core is deferred, so a deferred script here would miss alpine:init. */
document.addEventListener('alpine:init', () => {
	Alpine.data('summer_search', (settings) => ({
		search_term: '',
		matched_term: '',
		products: [],
		categories: [],
		corrected_query: null,
		/* 'idle', 'loading', 'ready' (products holds the answer for matched_term) or 'failed'. */
		status: 'idle',
		debounce_timer: null,
		/* Each keystroke fires its own request and the server answers out of order often enough
		   to matter; only the newest id may paint. */
		latest_request: 0,

		get has_enough_characters() {
			return this.search_term.trim().length >= 2;
		},

		handle_input() {
			clearTimeout(this.debounce_timer);
			if (!this.has_enough_characters) {
				this.reset();
				return;
			}
			this.status = 'loading';
			this.debounce_timer = setTimeout(() => this.get_products(), 275);
		},

		reset() {
			clearTimeout(this.debounce_timer);
			this.latest_request += 1;
			this.products = [];
			this.categories = [];
			this.corrected_query = null;
			this.matched_term = '';
			this.status = 'idle';
		},

		async get_products() {
			const term = this.search_term.trim();
			this.latest_request += 1;
			const request_id = this.latest_request;
			let response;
			try {
				response = await frappe_call(
					'/api/v2/method/commera.api.search.typeahead',
					{ q: term },
				);
			} catch (error) {
				/* The results on screen belong to an older term, so they go rather than pass for this one's. */
				if (request_id !== this.latest_request) return;
				this.products = [];
				this.categories = [];
				this.corrected_query = null;
				this.matched_term = term;
				this.status = 'failed';
				return;
			}
			if (request_id !== this.latest_request) {
				return;
			}
			this.products = response.data.products;
			this.categories = response.data.categories;
			this.corrected_query = response.data.corrected_query;
			this.matched_term = term;
			this.status = 'ready';
		},

		get_product_url(product) {
			return `${settings.products_url}/${product.route}`;
		},

		/* The server titles each card in the page's language: frappe_call sends it. */
		get_product_name(product) {
			return product.title || product.item_name;
		},
	}));
});
