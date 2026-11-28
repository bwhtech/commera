const catalog = window.CATALOG;
const MAX_ROWS = 6;

function getTokens(query) {
	return query.toLowerCase().trim().split(/\s+/).filter(Boolean);
}

function findProducts(query) {
	const tokens = getTokens(query);
	if (!tokens.length) return [];
	return catalog.products.filter((product) =>
		tokens.every((token) => product.terms.includes(token)),
	);
}

function findCollections(query) {
	const tokens = getTokens(query);
	return catalog.collections.filter((collection) =>
		tokens.some((token) => collection.title.toLowerCase().startsWith(token)),
	);
}

function escapeHtml(text) {
	return text.replace(
		/[&<>"]/g,
		(character) =>
			({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[character],
	);
}

function highlight(text, query) {
	const tokens = getTokens(query).map((token) =>
		token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
	);
	if (!tokens.length) return escapeHtml(text);
	const expression = new RegExp(`(${tokens.join('|')})`, 'gi');
	return text
		.split(expression)
		.map((part, index) =>
			index % 2 ? `<mark>${escapeHtml(part)}</mark>` : escapeHtml(part),
		)
		.join('');
}

function searchUrl(query) {
	return `search.html?q=${encodeURIComponent(query.trim())}`;
}

function renderRow(product, query) {
	return `<a class="search-row" role="option" href="product.html?item=${
		product.slug
	}" id="search-option-${product.slug}" aria-selected="false">
		<span class="search-row-media" style="background:${
			product.background
		}"><img src="img/${product.slug}.jpg" alt=""></span>
		<span class="search-row-text"><span class="search-row-title">${highlight(
			product.title,
			query,
		)}</span><span class="small muted">${highlight(product.meta, query)}</span></span>
		<span class="search-row-price price num small">${product.price}</span>
	</a>`;
}

function renderCollectionLinks(collections, query) {
	if (!collections.length) return '';
	const links = collections.map(
		(collection) =>
			`<li><a href="search.html?q=${encodeURIComponent(
				collection.title,
			)}">${highlight(collection.title, query)} <span class="num">${
				collection.count
			}</span></a></li>`,
	);
	return `<p class="eyebrow">Collections</p><ul class="search-links">${links.join(
		'',
	)}</ul>`;
}

function renderEmpty(query) {
	return `<div class="search-empty">
		<p class="h3">No results for “${escapeHtml(query)}”</p>
		<p class="small muted">Check the spelling, or try a shorter word like <a class="link" href="${searchUrl(
			'casserole',
		)}">casserole</a> or a colour like <a class="link" href="${searchUrl(
			'mint',
		)}">mint</a>.</p>
	</div>`;
}

function renderLive(query) {
	const products = findProducts(query);
	const collections = findCollections(query);
	const rows = products
		.slice(0, MAX_ROWS)
		.map((product) => renderRow(product, query))
		.join('');
	const results = products.length
		? `<p class="eyebrow">Products <span class="num">${
				products.length
		  }</span></p><div class="search-rows" role="listbox" id="search-options" aria-label="Products">${rows}</div>
			<a class="btn btn-secondary btn-block search-all" href="${searchUrl(
				query,
			)}">View all ${products.length} results for “${escapeHtml(
				query.trim(),
			)}”</a>`
		: renderEmpty(query.trim());
	const aside =
		renderCollectionLinks(collections, query) ||
		'<p class="eyebrow">Collections</p><p class="small muted">No matching collections.</p>';
	return `<aside class="search-aside${
		collections.length ? '' : ' is-empty'
	}">${aside}</aside><div>${results}</div>`;
}

function setupOverlay() {
	const overlay = document.getElementById('search');
	const input = document.getElementById('search-input');
	const idle = overlay.querySelector('.search-idle');
	const live = overlay.querySelector('.search-live');
	const clear = overlay.querySelector('[data-clear-search]');
	let activeIndex = -1;

	const modal = new window.ModalSurface(overlay, '#search-input');
	const setOpen = (open) => {
		if (open) {
			const fromMenu = Store.menu.element.classList.contains('open');
			Store.menu.close();
			if (fromMenu) document.querySelector('[data-open=menu]').focus();
			modal.open();
		} else modal.close();
	};

	const update = () => {
		const hasQuery = input.value.trim().length > 0;
		idle.hidden = hasQuery;
		live.hidden = !hasQuery;
		clear.hidden = !hasQuery;

		live.innerHTML = hasQuery ? renderLive(input.value) : '';
		const hasResults = !!live.querySelector('.search-row');
		input.setAttribute('aria-expanded', String(hasResults));
		if (hasResults) input.setAttribute('aria-controls', 'search-options');
		else input.removeAttribute('aria-controls');
		activeIndex = -1;
		input.removeAttribute('aria-activedescendant');
	};

	const moveActive = (step) => {
		const rows = [...live.querySelectorAll('.search-row')];
		if (!rows.length) return;
		activeIndex =
			activeIndex < 0
				? step > 0
					? 0
					: rows.length - 1
				: (activeIndex + step + rows.length) % rows.length;
		for (const [index, row] of rows.entries()) {
			row.setAttribute('aria-selected', String(index === activeIndex));
		}
		input.setAttribute('aria-activedescendant', rows[activeIndex].id);
		rows[activeIndex].scrollIntoView({ block: 'nearest' });
	};

	input.addEventListener('input', update);
	input.addEventListener('keydown', (event) => {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			moveActive(event.key === 'ArrowDown' ? 1 : -1);
		}
		if (event.key === 'Enter' && activeIndex >= 0) {
			event.preventDefault();
			live.querySelectorAll('.search-row')[activeIndex].click();
		}
	});
	clear.addEventListener('click', () => {
		input.value = '';
		update();
		input.focus();
	});
	for (const button of document.querySelectorAll('[data-open-search]'))
		button.addEventListener('click', () => setOpen(true));
	for (const button of overlay.querySelectorAll('[data-close-search]'))
		button.addEventListener('click', () => setOpen(false));
	document.addEventListener('keydown', (event) => {
		const isTyping = /INPUT|TEXTAREA|SELECT/.test(
			document.activeElement.tagName,
		);

		if (
			event.key === '/' &&
			!isTyping &&
			!event.metaKey &&
			!event.ctrlKey &&
			!document.querySelector('dialog[open]')
		) {
			event.preventDefault();
			setOpen(true);
		}
	});
}

function sortProducts(products, order) {
	const sorted = [...products];
	if (order === 'price-asc') sorted.sort((a, b) => a.amount - b.amount);
	if (order === 'price-desc') sorted.sort((a, b) => b.amount - a.amount);
	return sorted;
}

function setupResultsPage() {
	const page = document.querySelector('[data-search-page]');
	if (!page) return;
	const query = new URLSearchParams(location.search).get('q') || '';
	const products = findProducts(query);
	const collections = findCollections(query);
	page.querySelector('[name=q]').value = query;
	const quoted = `<span>“${escapeHtml(query)}”</span>`;
	page.querySelector('[data-title]').innerHTML = !query
		? 'What are you looking for?'
		: products.length
		  ? `Results for ${quoted}`
		  : `No results for ${quoted}`;
	page.querySelector('[data-count]').textContent = `${products.length} ${
		products.length === 1 ? 'product' : 'products'
	}`;
	page.querySelector('[data-collections]').innerHTML = collections
		.map(
			(collection) =>
				`<a class="chip" href="search.html?q=${encodeURIComponent(
					collection.title,
				)}">${escapeHtml(collection.title)} <span class="chip-count">${
					collection.count
				}</span></a>`,
		)
		.join('');
	page.querySelector('[data-collections-row]').hidden = !collections.length;
	page.querySelector('[data-results]').hidden = !products.length;
	page.querySelector('[data-empty]').hidden = products.length > 0;
	const grid = page.querySelector('[data-grid]');
	const sort = page.querySelector('[data-sort]');
	const renderGrid = () => {
		grid.innerHTML = sortProducts(products, sort.value)
			.map((product) => product.card)
			.join('');
	};
	sort.addEventListener('change', renderGrid);
	renderGrid();
}

setupOverlay();
setupResultsPage();
