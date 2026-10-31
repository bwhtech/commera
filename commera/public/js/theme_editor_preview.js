(() => {
	const origin = window.location.origin;
	const target_selector = '[data-commera-block], [data-commera-section]';
	const outline_style =
		'position:absolute;pointer-events:none;z-index:2147483647;outline:2px solid #171717;outline-offset:2px;box-shadow:0 0 0 2px #fff';
	let highlighted = [];
	let outlines = [];
	let selected_blocks = [];
	let selected_detail = null;
	let pending_scroll = false;
	const resize_observer = new ResizeObserver(() => refresh_outlines());
	let scroll_frame = null;
	let ignore_scroll = false;

	if (Number(new URLSearchParams(window.location.search).get('render')) > 1) {
		const settled = document.createElement('style');
		settled.textContent =
			'.wow{visibility:visible!important;animation:none!important}';
		const held = document.createElement('style');
		held.textContent =
			'*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important;transition-delay:0s!important}';
		document.head.append(settled, held);
		window.addEventListener('load', () => {
			held.remove();
			for (const animation of document.getAnimations()) {
				if (Number.isFinite(animation.effect?.getComputedTiming().endTime))
					animation.finish();
			}
		});
	}

	function post(type, data = {}) {
		window.parent.postMessage({ type, ...data }, origin);
	}

	function find_targets(group, section, id) {
		const section_element = document.querySelector(
			`[data-commera-group="${CSS.escape(
				group,
			)}"][data-commera-section="${CSS.escape(section)}"]`,
		);
		if (!section_element) return [];
		if (id === section) return [section_element];
		const blocks = section_element.querySelectorAll(
			`[data-commera-block="${CSS.escape(id)}"]`,
		);
		return blocks.length ? [...blocks] : [section_element];
	}

	function get_rect(element) {
		const rects = [element, ...element.children]
			.map((child) => child.getBoundingClientRect())
			.filter((rect) => rect.width || rect.height);
		if (!rects.length) return null;
		const top = Math.min(...rects.map((rect) => rect.top));
		const left = Math.min(...rects.map((rect) => rect.left));
		return {
			top: top + window.scrollY,
			left: left + window.scrollX,
			width: Math.max(...rects.map((rect) => rect.right)) - left,
			height: Math.max(...rects.map((rect) => rect.bottom)) - top,
		};
	}

	function refresh_outlines() {
		for (const outline of outlines) outline.remove();
		outlines = highlighted
			.map(get_rect)
			.filter(Boolean)
			.map((rect) => {
				const outline = document.createElement('div');
				outline.dataset.commeraOutline = '';
				outline.style.cssText = outline_style;
				Object.assign(outline.style, {
					top: `${rect.top}px`,
					left: `${rect.left}px`,
					width: `${rect.width}px`,
					height: `${rect.height}px`,
				});
				return document.body.appendChild(outline);
			});
		const rect =
			pending_scroll && highlighted.length && get_rect(highlighted[0]);
		if (rect) {
			pending_scroll = false;
			window.scrollTo({ top: Math.max(rect.top - 80, 0) });
		}
	}

	function dispatch(elements, type, detail) {
		for (const element of elements)
			element.dispatchEvent(new CustomEvent(type, { bubbles: true, detail }));
	}

	function select_blocks(blocks, detail) {
		const unchanged =
			blocks.length === selected_blocks.length &&
			blocks.every((element, index) => element === selected_blocks[index]);
		if (unchanged) return;
		dispatch(selected_blocks, 'commera:block:deselect', selected_detail);
		selected_blocks = blocks;
		selected_detail = detail;
		dispatch(selected_blocks, 'commera:block:select', selected_detail);
	}

	function highlight({ group, section, id, scroll }) {
		highlighted = group && section ? find_targets(group, section, id) : [];
		select_blocks(
			highlighted.filter((element) => element.dataset.commeraBlock),
			{ group, section, id },
		);
		pending_scroll = Boolean(scroll);
		resize_observer.disconnect();
		for (const element of highlighted) resize_observer.observe(element);
		refresh_outlines();
	}

	document.addEventListener(
		'click',
		(event) => {
			const link = event.target.closest('a, button[type="submit"]');
			const target = event.target.closest(target_selector);
			if (link || target) event.preventDefault();
			if (!target) return;
			event.stopPropagation();
			const section_element = target.closest('[data-commera-section]');
			if (!section_element) return;
			const { commeraGroup: group, commeraSection: section } =
				section_element.dataset;
			post('commera:select', {
				group,
				section,
				id: target.dataset.commeraBlock || section,
			});
		},
		true,
	);
	document.addEventListener('submit', (event) => event.preventDefault(), true);

	function top_section() {
		for (const element of document.querySelectorAll('[data-commera-section]')) {
			const rect = element.getBoundingClientRect();
			if (rect.bottom <= 0 || !rect.height) continue;
			return {
				group: element.dataset.commeraGroup,
				section: element.dataset.commeraSection,
				fraction: Math.min(Math.max(-rect.top / rect.height, 0), 1),
			};
		}
		return {};
	}

	function scroll_position() {
		return { y: window.scrollY, ...top_section() };
	}

	function scroll_to_section({ group, section, fraction }) {
		const [element] =
			group && section ? find_targets(group, section, section) : [];
		if (!element) return;
		const rect = element.getBoundingClientRect();
		ignore_scroll = true;
		window.scrollTo({
			top: rect.top + window.scrollY + (Number(fraction) || 0) * rect.height,
			behavior: 'instant',
		});
		requestAnimationFrame(() => {
			ignore_scroll = false;
		});
	}

	window.addEventListener('scroll', () => {
		if (ignore_scroll || scroll_frame) return;
		scroll_frame = requestAnimationFrame(() => {
			scroll_frame = null;
			post('commera:scroll', scroll_position());
		});
	});

	window.addEventListener('message', (event) => {
		if (event.origin !== origin || event.source !== window.parent) return;
		const { type, ...data } = event.data || {};
		if (type === 'commera:highlight') highlight(data);
		if (type === 'commera:scroll-to')
			window.scrollTo({ top: Number(data.y) || 0, behavior: 'instant' });
		if (type === 'commera:scroll-to-section') scroll_to_section(data);
	});

	window.addEventListener('resize', refresh_outlines);
	window.addEventListener('load', () => {
		dispatch(selected_blocks, 'commera:block:select', selected_detail);
		refresh_outlines();
	});
	window.addEventListener('pagehide', () =>
		post('commera:scroll', scroll_position()),
	);

	post('commera:preview-ready');
})();
