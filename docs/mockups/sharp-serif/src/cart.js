class CartSection {
	constructor() {
		this.lines = document.querySelector('.lines');
		this.render();
		this.lines.addEventListener('click', (event) => this.onClick(event));
		document
			.querySelector('[data-gift]')
			.addEventListener('change', (event) => {
				document.querySelector('.gift-note').hidden = !event.target.checked;
			});
		document
			.querySelector('[data-promo]')
			.addEventListener('submit', (event) => {
				event.preventDefault();
				document.querySelector('[data-promo-feedback]').textContent =
					'Discount codes aren’t connected in this preview.';
			});
	}

	onClick(event) {
		const button = event.target.closest('button');
		const line = button?.closest('[data-line]');
		if (!line) return;
		const index = Number(line.dataset.line);
		if (button.classList.contains('line-remove')) {
			Store.cart.splice(index, 1);
			Store.notify('Piece removed from your cart.');
		} else {
			const delta = button.dataset.action === 'increase' ? 1 : -1;
			Store.cart[index].quantity = Math.max(
				1,
				Math.min(99, Store.cart[index].quantity + delta),
			);
		}
		const action = button.dataset.action || 'remove';
		Store.saveCart();
		this.render();
		const nextLine = this.lines.querySelector(
			`[data-line="${Math.min(index, Store.cart.length - 1)}"]`,
		);
		(
			nextLine?.querySelector(`[data-action="${action}"]`) ||
			nextLine?.querySelector('.line-remove') ||
			document.querySelector('.cart-empty a')
		)?.focus();
	}

	render() {
		this.lines.innerHTML = Store.cart
			.map((line, index) => this.renderLine(line, index))
			.join('');
		let subtotal = 0;
		let savings = 0;
		let count = 0;
		for (const line of Store.cart) {
			const product = Store.products.find(
				(product) => product.slug === line.slug,
			);
			subtotal += product.amount * line.quantity;
			count += line.quantity;
			savings +=
				((product.compare || product.amount) - product.amount) * line.quantity;
		}
		document.querySelector(
			'[data-cart-title-count]',
		).textContent = `(${count})`;
		document.querySelector('[data-subtotal]').textContent =
			this.money(subtotal);
		document.querySelector('[data-total]').textContent = this.money(subtotal);
		document.querySelector('[data-shipping]').textContent =
			subtotal > 80 ? 'Free' : 'At checkout';
		document.querySelector('[data-savings]').textContent = savings
			? `You’re saving ${this.money(savings)} on this order.`
			: '';
		document.querySelector('.ship-progress p').textContent =
			subtotal > 80
				? 'Your order qualifies for free tracked shipping.'
				: `You’re ${this.money(81 - subtotal)} away from free shipping.`;
		document.querySelector('.summary').hidden = !count;
		for (const element of document.querySelectorAll(
			'.ship-progress,.line-head,.gift',
		)) {
			element.hidden = !count;
		}
		if (!count) {
			this.lines.innerHTML =
				'<li class="cart-empty"><h2 class="h2">Room for something good.</h2><p class="muted">Your cart is empty. Find a piece with a little history.</p><a class="btn btn-primary" href="collection.html">Explore the collection</a></li>';
			document.querySelector('.gift-note').hidden = true;
		}
	}

	renderLine(line, index) {
		const product = Store.products.find(
			(product) => product.slug === line.slug,
		);
		const description = `${product.title}, ${product.colour}`;
		const url = `product.html?item=${product.slug}`;
		return `<li class="line" data-line="${index}">
			<a href="${url}" class="line-media" style="background:${
				product.background
			}"><img src="img/${product.slug}.jpg" alt="${description}"></a>
			<div class="line-info"><a href="${url}" class="line-title">${
				product.title
			}</a><p class="small muted">${product.colour}${
				line.size ? ` · ${this.escape(line.size)}` : ''
			}</p><p class="small num price">${product.price}</p></div>
			<div class="stepper" role="group" aria-label="Quantity for ${description}"><button aria-label="Decrease ${
				product.title
			} quantity" data-action="decrease" ${
				line.quantity === 1 ? 'disabled' : ''
			}>${window.CATALOG.icons.minus}</button><output aria-label="Quantity">${
				line.quantity
			}</output><button aria-label="Increase ${
				product.title
			} quantity" data-action="increase" ${
				line.quantity === 99 ? 'disabled' : ''
			}>${window.CATALOG.icons.plus}</button></div>
			<p class="line-total num">${this.money(product.amount * line.quantity)}</p>
			<button class="line-remove link small muted" data-action="remove" aria-label="Remove ${description}">Remove</button>
		</li>`;
	}

	money(amount) {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
		}).format(amount);
	}
	escape(value) {
		return String(value).replace(
			/[&<>"']/g,
			(character) =>
				({
					'&': '&amp;',
					'<': '&lt;',
					'>': '&gt;',
					'"': '&quot;',
					"'": '&#39;',
				})[character],
		);
	}
}

new CartSection();
