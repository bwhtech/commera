class ProductSection {
	constructor() {
		const slug =
			new URLSearchParams(location.search).get('item') || 'casserole-mint';
		this.product =
			Store.products.find((product) => product.slug === slug) ||
			Store.products[0];
		this.variants = Store.products.filter(
			(product) => product.title === this.product.title,
		);
		this.quantity = 1;
		this.size = this.product.meta.split(' · ')[1] || '';
		this.setupGallery();
		this.setupOptions();
		this.setupPurchase();
		this.update(this.product);
		this.selectPhoto(
			this.photos.findIndex((photo) => photo.slug === this.product.slug),
		);
	}

	setupGallery() {
		this.track = document.querySelector('.gallery-track');
		this.photos = this.variants.map((product) => ({
			slug: product.slug,
			background: product.background,
			source: `img/${product.slug}.jpg`,
			label: product.colour,
		}));
		const alternate = {
			'bowl-white-2': ['bowl-white', 'bowl-white-3'],
			'cup-seafoam': ['cup-seafoam-2'],
			'cup-sky': ['cup-sky-2'],
		};
		for (const slug of alternate[this.product.slug] || [])
			this.photos.push({
				slug: this.product.slug,
				background: this.product.background,
				source: `img/${slug}.jpg`,
				label: `${this.product.colour}, another view`,
			});
		this.track.innerHTML = this.photos
			.map(
				(photo) =>
					`<img style="background:${photo.background}" src="${photo.source}" alt="${this.product.title}, ${photo.label}" width="900" height="675">`,
			)
			.join('');
		document.querySelector('.thumbs').innerHTML = this.photos
			.map(
				(photo, index) =>
					`<button class="thumb" style="background:${
						photo.background
					}" role="radio" aria-checked="${index === 0}" tabindex="${
						index === 0 ? 0 : -1
					}" data-photo="${index}" aria-label="${photo.label}"><img src="${
						photo.source
					}" alt=""></button>`,
			)
			.join('');
		document.querySelector('.thumbs').hidden = this.photos.length < 2;
		document
			.querySelector('.thumbs')
			.addEventListener('optionchange', (event) =>
				this.selectPhoto(Number(event.detail.dataset.photo)),
			);
		this.track.addEventListener('scroll', () => {
			cancelAnimationFrame(this.scrollFrame);
			this.scrollFrame = requestAnimationFrame(() =>
				this.syncPhoto(
					Math.round(this.track.scrollLeft / this.track.clientWidth),
				),
			);
		});
		this.track.addEventListener('keydown', (event) => {
			if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
			event.preventDefault();
			const direction = event.key === 'ArrowRight' ? 1 : -1;
			this.selectPhoto(
				(this.photoIndex + direction + this.photos.length) % this.photos.length,
			);
		});
		document
			.querySelector('.gallery-zoom')
			.addEventListener('click', () =>
				Store.showInfo(
					`${this.product.title}, ${this.product.colour}`,
					null,
					this.photos[this.photoIndex].source,
				),
			);
	}

	setupOptions() {
		const colours = window.CATALOG.colours;
		const swatches = document.querySelector('.swatches');
		swatches.innerHTML = this.variants
			.map(
				(product) =>
					`<button class="swatch" role="radio" aria-checked="${
						product.slug === this.product.slug
					}" tabindex="${
						product.slug === this.product.slug ? 0 : -1
					}" data-value="${product.colour}" data-slug="${
						product.slug
					}" aria-label="${product.colour}"><span style="background:${
						colours[product.colour.toLowerCase()]
					}"></span></button>`,
			)
			.join('');
		swatches.addEventListener('optionchange', (event) =>
			this.selectPhoto(
				this.photos.findIndex(
					(photo) => photo.slug === event.detail.dataset.slug,
				),
			),
		);
		const sizes = document.querySelector('.sizes');
		if (this.product.title !== 'Lidded casserole') {
			document.querySelector('[data-size-option]').hidden = true;
		} else {
			for (const option of sizes.querySelectorAll('[role="radio"]')) {
				option.tabIndex =
					option.getAttribute('aria-checked') === 'true' ? 0 : -1;
			}
			sizes.addEventListener('optionchange', (event) => {
				this.size = event.detail.dataset.value;
				document.querySelector('[data-capacity]').textContent = this.size;
			});
		}
	}

	setupPurchase() {
		const stepper = document.querySelector('.buy-actions .stepper');
		for (const [index, button] of stepper
			.querySelectorAll('button')
			.entries()) {
			button.addEventListener('click', () => {
				this.quantity = Math.max(
					1,
					Math.min(99, this.quantity + (index ? 1 : -1)),
				);
				stepper.querySelector('output').textContent = this.quantity;
				stepper.querySelector('button').disabled = this.quantity === 1;
				stepper.querySelectorAll('button')[1].disabled = this.quantity === 99;
			});
		}
		stepper.querySelector('button').disabled = true;
		stepper.querySelector('output').setAttribute('aria-live', 'polite');
		for (const button of document.querySelectorAll(
			'.add-to-cart,[data-sticky-add]',
		))
			button.addEventListener('click', () =>
				Store.add(this.product.slug, this.quantity, this.size),
			);
		const sticky = document.querySelector('.sticky-buy');
		const mainButton = document.querySelector('.add-to-cart');
		const isPhone = matchMedia('(max-width: 600px)');
		let frame = 0;
		const update = () => {
			frame = 0;
			const visible =
				isPhone.matches && mainButton.getBoundingClientRect().bottom < 64;
			sticky.classList.toggle('is-visible', visible);
			sticky.setAttribute('aria-hidden', String(!visible));
			sticky.inert = !visible;
		};
		const schedule = () => {
			frame ||= requestAnimationFrame(update);
		};
		addEventListener('scroll', schedule, { passive: true });
		addEventListener('resize', schedule);
		update();
	}

	selectPhoto(index) {
		const photo = Math.max(index, 0);
		this.track.scrollTo({
			left: photo * this.track.clientWidth,
			behavior: 'instant',
		});
		this.syncPhoto(photo);
	}

	syncPhoto(index) {
		const photo = this.photos[index];
		if (!photo) return;
		this.photoIndex = index;
		document.querySelector('.gallery-main').style.background = photo.background;
		document.querySelector('.gallery-counter').textContent = `${index + 1} / ${
			this.photos.length
		}`;
		for (const button of document.querySelectorAll('[data-photo]')) {
			const checked = Number(button.dataset.photo) === index;
			button.setAttribute('aria-checked', String(checked));
			button.tabIndex = checked ? 0 : -1;
		}
		this.update(Store.products.find((product) => product.slug === photo.slug));
	}

	update(product) {
		this.product = product;
		document.title = `${product.title}, ${product.colour} · Émail`;
		for (const element of document.querySelectorAll(
			'[data-product-title],[data-product-crumb],[data-sticky-title]',
		)) {
			element.textContent = product.title;
		}
		document.querySelector('[data-product-category]').textContent =
			product.category;
		const parent = document.querySelector('[data-product-parent]');
		parent.textContent = product.category;
		parent.href = `collection.html?category=${encodeURIComponent(
			product.category,
		)}`;
		document.querySelector('[data-product-price]').innerHTML = product.price;
		document.querySelector('[data-sticky-price]').innerHTML = product.price;
		document.querySelector(
			'.add-to-cart',
		).innerHTML = `Add to cart <span class="num">· $${product.amount}</span>`;
		document.querySelector('#colour-value').textContent = product.colour;
		document.querySelector('[data-finish]').textContent = product.colour;
		if (product.title !== 'Lidded casserole')
			this.size = product.meta.split(' · ')[1] || '';
		document.querySelector('[data-capacity]').textContent =
			this.size || 'See photograph';
		document.querySelector(
			'[data-capacity]',
		).previousElementSibling.textContent = this.size.includes('cm')
			? 'Size'
			: 'Capacity';
		document.querySelector('[data-product-description]').textContent =
			product.title === 'Lidded casserole'
				? `A deep, two-handled casserole in ${product.colour.toLowerCase()} enamel. A generous shape, an original finish and a snug lid. Made for slow afternoons and a full table.`
				: `An original vintage ${product.title.toLowerCase()} in ${product.colour.toLowerCase()} enamel. A useful piece with the marks and character of a previous life, cleaned by hand in our Lisbon workshop.`;
		for (const button of document.querySelectorAll('[data-slug]')) {
			const checked = button.dataset.slug === product.slug;
			button.setAttribute('aria-checked', String(checked));
			button.tabIndex = checked ? 0 : -1;
		}
		const url = new URL(location.href);
		url.searchParams.set('item', product.slug);
		history.replaceState(null, '', url);
	}
}

new ProductSection();
