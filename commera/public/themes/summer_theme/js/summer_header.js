/* Header chrome state (drawer, mega-menu, search canvas, cart drawer). Its own file, not summer.js:
   summer.js is deferred to the end of the layout, by which point alpine:init has already fired. */
document.addEventListener('alpine:init', () => {
	Alpine.data('summer_header', () => ({
		menu_open: false,
		search_open: false,
		cart_open: false,
		cart_tab: 'cart',
		open_branches: [],
		cart_detail_loaded: false,
		bottom_bar_active: false,
		// The drawer's Checkout: 'idle', 'saving' while the cart's last edit lands, 'leaving' once checkout loads.
		checkout_status: 'idle',

		init() {
			window.addEventListener('pageshow', (event) => {
				if (event.persisted) this.checkout_status = 'idle';
			});
			/* Below 768px style.css parks .extra-nav off the bottom edge and slides it up on .active,
			   which upstream stamps from a jQuery scroll handler. A sentinel reads the same moment. */
			const observer = new IntersectionObserver((entries) => {
				this.bottom_bar_active = !entries[0].isIntersecting;
			});
			observer.observe(this.$refs.header_sentinel);
		},

		is_branch_open(branch_key) {
			return this.open_branches.includes(branch_key);
		},

		toggle_branch(branch_key) {
			this.open_branches = this.is_branch_open(branch_key)
				? this.open_branches.filter((key) => key !== branch_key)
				: [...this.open_branches, branch_key];
		},

		async open_cart() {
			this.search_open = false;
			this.menu_open = false;
			this.cart_open = true;
			/* Stock and price are only stamped onto the persisted cart by an API read, and increment()
			   refuses to go past stock_qty, so the stepper is dead on a page that never loaded it. */
			if (!this.cart_detail_loaded && Alpine.store('cart').items.length) {
				this.cart_detail_loaded = true;
				await Alpine.store('cart').fetch_detail_for_cart();
			}
		},

		open_search() {
			this.cart_open = false;
			this.menu_open = false;
			this.search_open = true;
		},

		open_mobile_menu() {
			this.search_open = false;
			this.cart_open = false;
			this.menu_open = true;
		},

		close_overlays() {
			this.menu_open = false;
			this.search_open = false;
			this.cart_open = false;
		},

		/* Checkout builds from the server cart, so an edit still waiting on the debounce must land first. */
		async go_to_checkout(url) {
			if (this.checkout_status !== 'idle') return;
			this.checkout_status = 'saving';
			if (!(await Alpine.store('cart').flush_sync())) {
				this.checkout_status = 'idle';
				return;
			}
			this.checkout_status = 'leaving';
			window.location.href = url;
		},
	}));
});
