class ModalSurface {
	constructor(element, focusSelector) {
		this.element = element;
		this.focusSelector = focusSelector;
		this.onKeydown = this.onKeydown.bind(this);
	}

	open() {
		if (ModalSurface.active === this) return;
		ModalSurface.active?.close();
		this.opener = document.activeElement;
		this.disabled = [];
		this.element.inert = false;
		this.element.classList.add('open');
		this.element.setAttribute('aria-hidden', 'false');
		for (
			let node = this.element;
			node.parentElement && node !== document.body;
			node = node.parentElement
		) {
			for (const sibling of [...node.parentElement.children].filter(
				(sibling) =>
					sibling !== node &&
					!sibling.inert &&
					!/SCRIPT|STYLE/.test(sibling.tagName),
			)) {
				sibling.inert = true;
				this.disabled.push(sibling);
			}
		}
		document.documentElement.classList.add('is-locked');
		document.addEventListener('keydown', this.onKeydown);
		ModalSurface.active = this;
		this.element.querySelector(this.focusSelector)?.focus();
	}

	close() {
		if (!this.element.classList.contains('open')) return;
		for (const element of this.disabled ?? []) {
			element.inert = false;
		}
		this.disabled = [];
		this.element.classList.remove('open');
		this.element.setAttribute('aria-hidden', 'true');
		this.element.inert = true;
		document.documentElement.classList.remove('is-locked');
		document.removeEventListener('keydown', this.onKeydown);
		if (ModalSurface.active === this) ModalSurface.active = null;
		if (this.opener?.isConnected && !this.opener.closest('[inert]'))
			this.opener.focus({ preventScroll: true });
		this.onClose?.();
	}

	onKeydown(event) {
		if (event.key === 'Escape') {
			event.preventDefault();
			this.close();
		}
		if (event.key !== 'Tab') return;
		const controls = [
			...this.element.querySelectorAll(
				'a[href],button,input,select,textarea,[tabindex="0"]',
			),
		].filter(
			(element) =>
				!element.disabled &&
				!element.closest('[inert]') &&
				element.getClientRects().length,
		);
		const target = event.shiftKey ? controls.at(-1) : controls[0];
		if (
			(event.shiftKey && document.activeElement === controls[0]) ||
			(!event.shiftKey && document.activeElement === controls.at(-1))
		) {
			event.preventDefault();
			target?.focus();
		}
	}
}

class StorePreview {
	constructor() {
		this.products = window.CATALOG.products;
		this.cart = this.readCart();
		this.setupMenu();
		this.setupRadios();
		this.setupInfo();
		this.setupNewsletter();
		document
			.querySelector('.announce .close')
			?.addEventListener('click', () => {
				document.querySelector('.announce').hidden = true;
			});
		this.updateCount();
	}

	notify(message) {
		clearTimeout(this.statusTimer);
		document.querySelector('[data-status]').textContent = message;
		this.statusTimer = setTimeout(() => {
			document.querySelector('[data-status]').textContent = '';
		}, 3500);
	}

	add(slug, quantity, size) {
		const existing = this.cart.find(
			(line) => line.slug === slug && line.size === size,
		);
		if (existing) existing.quantity += quantity;
		else this.cart.push({ slug, quantity, size });
		this.saveCart();
		this.notify(
			`${quantity === 1 ? 'Piece' : `${quantity} pieces`} added to your cart.`,
		);
	}

	saveCart() {
		try {
			localStorage.setItem('email-preview-cart-v2', JSON.stringify(this.cart));
		} catch {}
		this.updateCount();
	}

	updateCount() {
		const count = this.cart.reduce((sum, line) => sum + line.quantity, 0);
		for (const element of document.querySelectorAll('[data-cart-count]')) {
			element.textContent = count;
		}
		for (const element of document.querySelectorAll('[data-cart-link]')) {
			element.setAttribute('aria-label', `Cart, ${count} items`);
		}
	}

	setupMenu() {
		const menu = new ModalSurface(
			document.getElementById('menu'),
			'button[data-close]',
		);
		const opener = document.querySelector('[data-open=menu]');
		opener.addEventListener('click', () => {
			menu.open();
			opener.setAttribute('aria-expanded', 'true');
		});
		menu.onClose = () => opener.setAttribute('aria-expanded', 'false');
		for (const button of menu.element.querySelectorAll('[data-close]'))
			button.addEventListener('click', () => menu.close());
		this.menu = menu;
	}

	setupRadios() {
		const select = (group, option) => {
			if (
				!option ||
				option.disabled ||
				option.getAttribute('aria-disabled') === 'true'
			)
				return;
			for (const item of group.querySelectorAll('[role="radio"]')) {
				item.setAttribute('aria-checked', String(item === option));
				item.tabIndex = item === option ? 0 : -1;
			}
			const label = document.getElementById(group.dataset.label);
			if (label) label.textContent = option.dataset.value;
			group.dispatchEvent(
				new CustomEvent('optionchange', { detail: option, bubbles: true }),
			);
		};
		document.addEventListener('click', (event) => {
			const option = event.target.closest('[role="radio"]');
			if (option) select(option.closest('[role="radiogroup"]'), option);
		});
		document.addEventListener('keydown', (event) => {
			const group = event.target.closest('[role="radiogroup"]');
			if (
				!group ||
				![
					'ArrowRight',
					'ArrowLeft',
					'ArrowDown',
					'ArrowUp',
					'Home',
					'End',
				].includes(event.key)
			)
				return;
			event.preventDefault();
			const options = [...group.querySelectorAll('[role="radio"]')].filter(
				(option) => !option.disabled,
			);
			const direction = ['ArrowRight', 'ArrowDown'].includes(event.key)
				? 1
				: -1;
			const index =
				event.key === 'Home'
					? 0
					: event.key === 'End'
					  ? options.length - 1
					  : (options.indexOf(event.target) + direction + options.length) %
						  options.length;
			select(group, options[index]);
			options[index]?.focus();
		});
	}

	setupInfo() {
		const dialog = document.getElementById('info-dialog');
		const copy = {
			Shipping:
				'Orders are packed in paper and dispatched from Lisbon within two working days. This preview shows free tracked shipping on orders over $80; delivery terms need confirmation before launch.',
			Returns:
				'This preview offers returns within 30 days. The final return address and policy will be available when the shop opens.',
			'Care guide':
				'Wash gently by hand, then dry thoroughly. Avoid abrasive cleaners, sudden temperature changes and heating empty cookware. Check each piece’s condition before use.',
			Contact:
				'The workshop’s contact details will be available when the shop opens.',
			About:
				'Émail collects vintage enamelware from European kitchens. Original colour, everyday usefulness and the marks of a previous life guide the collection.',
			Checkout:
				'You’re exploring a storefront preview. Checkout is not connected, and no payment will be taken. Your cart is saved in this browser.',
			'Track an order':
				'Order tracking will be available when the shop opens. No orders are placed through this preview.',
			Wholesale: 'Trade enquiries will be available when the shop opens.',
			Instagram:
				'The studio’s social account has not been connected to this preview.',
			Reviews:
				'The reviews shown here are sample content for the storefront design.',
			'Size guide':
				'Capacity is the volume a vessel holds. For a casserole, 1.5 L suits a small side, 2.5 L a meal for two, and 3.5 L a larger dish. These size choices demonstrate the theme; confirm each vintage piece’s measurements before launch.',
		};
		document.addEventListener('click', (event) => {
			const button = event.target.closest('[data-info]');
			if (button) this.showInfo(button.dataset.info, copy[button.dataset.info]);
		});
		dialog
			.querySelector('[data-close-info]')
			.addEventListener('click', () => dialog.close());
		dialog.addEventListener('close', () => {
			if (!ModalSurface.active)
				document.documentElement.classList.remove('is-locked');
		});
		dialog.addEventListener('click', (event) => {
			const rect = dialog.getBoundingClientRect();
			if (
				event.target === dialog &&
				(event.clientX < rect.left ||
					event.clientX > rect.right ||
					event.clientY < rect.top ||
					event.clientY > rect.bottom)
			)
				dialog.close();
		});
	}

	showInfo(title, text, image) {
		const dialog = document.getElementById('info-dialog');
		dialog.querySelector('#info-title').textContent = title;
		const body = dialog.querySelector('[data-info-copy]');
		body.replaceChildren();
		if (text) {
			const paragraph = document.createElement('p');
			paragraph.textContent = text;
			body.append(paragraph);
		}
		if (image) {
			const photo = document.createElement('img');
			photo.src = image;
			photo.alt = title;
			body.append(photo);
		}
		document.documentElement.classList.add('is-locked');
		dialog.showModal();
	}

	setupNewsletter() {
		document
			.querySelector('[data-newsletter]')
			?.addEventListener('submit', (event) => {
				event.preventDefault();
				document.querySelector('[data-newsletter-feedback]').textContent =
					'This is a preview. Your email has not been sent or saved.';
			});
	}

	readCart() {
		try {
			const saved = JSON.parse(localStorage.getItem('email-preview-cart-v2'));
			if (Array.isArray(saved))
				return saved.filter(
					(line) =>
						this.products.some((product) => product.slug === line.slug) &&
						Number.isInteger(line.quantity) &&
						line.quantity > 0 &&
						line.quantity <= 99,
				);
		} catch {}
		return [
			{ slug: 'casserole-mint', quantity: 1, size: '3.5 L' },
			{ slug: 'jug-delft', quantity: 1, size: '1.8 L' },
			{ slug: 'cup-jade', quantity: 2, size: '300 ml' },
		];
	}
}

window.ModalSurface = ModalSurface;
window.Store = new StorePreview();
