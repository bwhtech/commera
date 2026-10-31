(() => {
	const origin = window.location.origin;
	const target_selector = '[data-commera-block], [data-commera-section]';
	let highlighted = null;

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

	const outline = document.createElement('div');
	outline.style.cssText =
		'position:absolute;pointer-events:none;z-index:2147483647;display:none;outline:2px solid #171717;outline-offset:-2px;box-shadow:0 0 0 2px #fff inset';
	document.body.appendChild(outline);

	function post(type, data = {}) {
		window.parent.postMessage({ type, ...data }, origin);
	}

	function find_target(group, section, id) {
		const section_element = document.querySelector(
			`[data-commera-group="${CSS.escape(
				group,
			)}"][data-commera-section="${CSS.escape(section)}"]`,
		);
		if (!section_element || id === section) return section_element;
		return (
			section_element.querySelector(
				`[data-commera-block="${CSS.escape(id)}"]`,
			) || section_element
		);
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

	function refresh_outline() {
		const rect = highlighted && get_rect(highlighted);
		if (!rect) {
			outline.style.display = 'none';
			return;
		}
		Object.assign(outline.style, {
			display: 'block',
			top: `${rect.top}px`,
			left: `${rect.left}px`,
			width: `${rect.width}px`,
			height: `${rect.height}px`,
		});
	}

	function highlight({ group, section, id, scroll }) {
		highlighted = group && section ? find_target(group, section, id) : null;
		refresh_outline();
		const rect = scroll && highlighted && get_rect(highlighted);
		if (rect) window.scrollTo({ top: Math.max(rect.top - 80, 0) });
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

	window.addEventListener('message', (event) => {
		if (event.origin !== origin || event.source !== window.parent) return;
		const { type, ...data } = event.data || {};
		if (type === 'commera:highlight') highlight(data);
		if (type === 'commera:scroll-to')
			window.scrollTo({ top: Number(data.y) || 0, behavior: 'instant' });
	});

	window.addEventListener('resize', refresh_outline);
	window.addEventListener('load', refresh_outline);
	window.addEventListener('pagehide', () =>
		post('commera:scroll', { y: window.scrollY }),
	);

	post('commera:preview-ready');
})();
