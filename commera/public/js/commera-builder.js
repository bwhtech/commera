// Behaviours for Commera theme pages built in Frappe Builder, wired by data-commera-* attributes.
// The storefront SDK (window.commera) is already on the page.
(() => {
	const ADDED_LABEL_MS = 2000;
	let selected_variant_id = null;

	function set_message(text) {
		for (const element of document.querySelectorAll(
			'[data-commera-cart-message]',
		)) {
			element.textContent = text;
		}
	}

	function show_cart_count(cart) {
		const count = cart?.total_quantity ?? 0;
		for (const element of document.querySelectorAll(
			'[data-commera-cart-count]',
		)) {
			element.textContent = count;
			element.dataset.count = count;
		}
	}

	function select_size(button) {
		if (button.disabled || button.dataset.available === 'false') return;
		selected_variant_id = button.getAttribute('data-commera-size');
		for (const size of document.querySelectorAll('[data-commera-size]')) {
			size.setAttribute('aria-pressed', String(size === button));
		}
		set_message('');
	}

	// A chosen size wins; a product sold in one size binds its variant onto the button itself.
	function get_variant_id(button) {
		return (
			selected_variant_id ||
			button.getAttribute('data-commera-add-to-cart') ||
			button.getAttribute('data-commera-buy-now') ||
			null
		);
	}

	function has_sizes() {
		return Boolean(document.querySelector('[data-commera-size]'));
	}

	function get_quantity() {
		const input = document.querySelector('[data-commera-quantity]');
		return Math.max(Number(input?.value) || 1, 1);
	}

	async function add_to_cart(button, then_checkout) {
		const variant_id = get_variant_id(button);
		if (!variant_id) {
			set_message(
				has_sizes() ? 'Choose a size first.' : 'This product is not available.',
			);
			return;
		}
		button.disabled = true;
		try {
			const cart = await window.commera.cart.add_lines([
				{ item_code: variant_id, qty: get_quantity() },
			]);
			if (then_checkout) {
				await window.commera.cart.go_to_checkout();
				return;
			}
			show_added(button);
			// A theme's cart drawer opens on this.
			window.dispatchEvent(
				new CustomEvent('commera:cart-added', { detail: cart }),
			);
		} catch (error) {
			set_message(error?.message || 'Could not add this to your cart.');
		} finally {
			button.disabled = false;
		}
	}

	function show_added(button) {
		const label = button.textContent;
		button.textContent = 'Added to cart';
		set_message('Added to cart.');
		setTimeout(() => {
			button.textContent = label;
		}, ADDED_LABEL_MS);
	}

	document.addEventListener('click', (event) => {
		const target = event.target.closest(
			'[data-commera-size], [data-commera-add-to-cart], [data-commera-buy-now], [data-commera-checkout]',
		);
		if (!target) return;
		event.preventDefault();
		if (target.hasAttribute('data-commera-size')) select_size(target);
		else if (target.hasAttribute('data-commera-add-to-cart'))
			add_to_cart(target, false);
		else if (target.hasAttribute('data-commera-buy-now'))
			add_to_cart(target, true);
		else window.commera.cart.go_to_checkout();
	});

	window.addEventListener('commera:cart-updated', (event) =>
		show_cart_count(event.detail),
	);

	document.addEventListener('DOMContentLoaded', () => {
		for (const size of document.querySelectorAll('[data-commera-size]')) {
			size.setAttribute('aria-pressed', 'false');
		}
		window.commera?.cart
			.get()
			.then(show_cart_count)
			.catch(() => {});
	});
})();
