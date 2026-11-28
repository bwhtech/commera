class CollectionSection {
	constructor() {
		this.products = window.CATALOG.products;
		this.category =
			new URLSearchParams(location.search).get('category') || 'All';
		this.colours = new Set();
		this.setupCategories();
		this.setupFilters();
		this.render();
	}

	setupCategories() {
		const names = [
			'All',
			'Cookware',
			'Tableware',
			'Coffee & tea',
			'Kitchen tools',
			'Home',
			'Sale',
		];
		if (!names.includes(this.category)) this.category = 'All';
		document.querySelector('[data-categories]').innerHTML = names
			.map((name) => {
				const count = this.products.filter((product) =>
					this.matchesCategory(product, name),
				).length;
				return `<button class="chip" data-category="${name}" aria-pressed="${
					name === this.category
				}">${name}<span class="chip-count">${count}</span></button>`;
			})
			.join('');
		for (const button of document.querySelectorAll('[data-category]'))
			button.addEventListener('click', () => {
				this.category = button.dataset.category;
				this.render();
				const url = new URL(location.href);
				this.category === 'All'
					? url.searchParams.delete('category')
					: url.searchParams.set('category', this.category);
				history.replaceState(null, '', url);
			});
		document
			.querySelector('[data-collection-sort]')
			.addEventListener('change', () => this.render());
	}

	setupFilters() {
		const colours = [
			...new Set(this.products.map((product) => product.colour)),
		].sort();
		document.querySelector('[data-colour-filters]').innerHTML = colours
			.map(
				(colour) =>
					`<label class="check"><input type="checkbox" value="${colour}" data-colour>${colour}<span class="num muted">${
						this.products.filter((product) => product.colour === colour).length
					}</span></label>`,
			)
			.join('');
		for (const input of document.querySelectorAll('[data-colour]'))
			input.addEventListener('change', () => {
				input.checked
					? this.colours.add(input.value)
					: this.colours.delete(input.value);
				this.render();
			});
		for (const input of document.querySelectorAll(
			'[data-min-price],[data-max-price],[data-sale-only]',
		))
			input.addEventListener('input', () => this.render());
		for (const button of document.querySelectorAll('[data-clear-filters]'))
			button.addEventListener('click', () => this.clear());
		const filters = document.querySelector('.filters');
		const modal = new window.ModalSurface(filters, '[data-close-filters]');
		const toggle = document.querySelector('.filter-toggle');
		modal.onClose = () => {
			filters.inert = false;
			filters.removeAttribute('aria-hidden');
			filters.removeAttribute('role');
			filters.removeAttribute('aria-modal');
			document.querySelector('.filter-scrim').classList.remove('open');
			toggle.setAttribute('aria-expanded', 'false');
		};
		toggle.addEventListener('click', () => {
			modal.open();
			filters.setAttribute('role', 'dialog');
			filters.setAttribute('aria-modal', 'true');
			document.querySelector('.filter-scrim').inert = false;
			document.querySelector('.filter-scrim').classList.add('open');
			toggle.setAttribute('aria-expanded', 'true');
		});
		for (const button of document.querySelectorAll('[data-close-filters]'))
			button.addEventListener('click', () => modal.close());
		matchMedia('(min-width: 901px)').addEventListener('change', (event) => {
			if (event.matches && filters.classList.contains('open')) modal.close();
		});
	}

	render() {
		const minimum =
			Number(document.querySelector('[data-min-price]').value) || 0;
		const maximum = document.querySelector('[data-max-price]').value;
		const sale = document.querySelector('[data-sale-only]').checked;
		const matches = this.products.filter(
			(product) =>
				this.matchesCategory(product, this.category) &&
				(!this.colours.size || this.colours.has(product.colour)) &&
				product.amount >= minimum &&
				(!maximum || product.amount <= Number(maximum)) &&
				(!sale || product.compare),
		);
		const order = document.querySelector('[data-collection-sort]').value;
		if (order === 'price-asc') matches.sort((a, b) => a.amount - b.amount);
		if (order === 'price-desc') matches.sort((a, b) => b.amount - a.amount);
		document.querySelector('[data-collection-grid]').innerHTML = matches
			.map((product) => product.card)
			.join('');
		document.querySelector('[data-collection-empty]').hidden = !!matches.length;
		document.querySelector('[data-collection-count]').textContent = `${
			matches.length
		} ${matches.length === 1 ? 'piece' : 'pieces'}`;
		document.querySelector('[data-collection-end]').textContent = matches.length
			? `You’ve seen all ${matches.length} ${
					matches.length === 1 ? 'piece' : 'pieces'
			  } in this selection.`
			: '';
		const title = this.category === 'All' ? 'The collection' : this.category;
		document.querySelector('[data-collection-title]').textContent = title;
		document.querySelector('[data-collection-crumb]').textContent = title;
		document.title = `${title} · Émail`;
		for (const link of document.querySelectorAll('.nav a')) {
			const url = new URL(link.href);
			const active =
				url.pathname.endsWith('collection.html') &&
				(url.searchParams.get('category') || 'All') === this.category;
			active
				? link.setAttribute('aria-current', 'page')
				: link.removeAttribute('aria-current');
		}
		for (const button of document.querySelectorAll('[data-category]'))
			button.setAttribute(
				'aria-pressed',
				String(button.dataset.category === this.category),
			);
		const count =
			this.colours.size +
			Number(minimum > 0) +
			Number(!!maximum) +
			Number(sale);
		document.querySelector('[data-filter-count]').textContent = count
			? `(${count})`
			: '';
	}

	clear() {
		this.colours.clear();
		for (const input of document.querySelectorAll(
			'[data-colour],[data-sale-only]',
		)) {
			input.checked = false;
		}
		for (const input of document.querySelectorAll(
			'[data-min-price],[data-max-price]',
		)) {
			input.value = '';
		}
		this.render();
	}

	matchesCategory(product, category) {
		return (
			category === 'All' ||
			(category === 'Sale' ? !!product.compare : product.category === category)
		);
	}
}

new CollectionSection();
