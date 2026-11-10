import { toolbarItems, usePageStore } from 'builder';
import router from 'builder/internal/router';
import { Badge, Button, FormControl, Popover, call, toast } from 'frappe-ui';
// The Commera theme bar: switch between a theme's pages, pick what the canvas previews, publish the theme
// and make it live, without leaving the editor. It shows only on pages of a Commera theme.
import { computed, h, ref, watch } from 'vue';

const API = 'commera.api.admin.builder_theme.';
const SEARCH_DELAY_MS = 250;

function page_status(page) {
	if (!page.is_published) return 'Draft';
	return page.has_unpublished_changes ? 'Edited' : 'Published';
}

const PageTabs = {
	props: ['bar'],
	setup(props) {
		const open_page = (page) =>
			router.push({ name: 'builder', params: { pageId: page.page } });
		return () =>
			h(
				'div',
				{ class: 'grid grid-cols-3 gap-1' },
				props.bar.pages.map((page) => {
					const current = page.page_type === props.bar.page_type;
					return h(
						'div',
						{
							class: [
								'flex flex-col gap-1 rounded-4 p-2 cursor-pointer border',
								current
									? 'bg-surface-gray-2 border-outline-gray-2'
									: 'border-transparent hover:bg-surface-gray-2',
							],
							onClick: () => current || open_page(page),
						},
						[
							h(
								'span',
								{ class: 'text-sm font-medium text-ink-gray-9 truncate' },
								page.label,
							),
							h(
								'span',
								{ class: 'text-xs text-ink-gray-5 truncate' },
								page_status(page),
							),
						],
					);
				}),
			);
	},
};

const ProductPicker = {
	props: ['preview'],
	setup(props) {
		const pageStore = usePageStore();
		const query = ref('');
		const options = ref(props.preview.options);
		let timer = null;

		watch(query, (value) => {
			clearTimeout(timer);
			timer = setTimeout(async () => {
				options.value = await call(`${API}search_preview_products`, {
					query: value,
				}).catch(() => []);
			}, SEARCH_DELAY_MS);
		});

		// with no product chosen, the canvas previews the newest one, which heads the list
		const selected = computed(
			() => pageStore.routeVariables.route || props.preview.options[0]?.value,
		);
		const tile = (option) =>
			h(
				'div',
				{
					class: [
						'flex items-center gap-2 rounded-4 px-2 py-1 cursor-pointer',
						option.value === selected.value
							? 'bg-surface-gray-2'
							: 'hover:bg-surface-gray-2',
					],
					onClick: () => pageStore.setRouteVariable('route', option.value),
				},
				[
					option.image
						? h('img', {
								src: option.image,
								alt: '',
								class: 'size-8 rounded-4 object-cover',
								'data-preview': '',
						  })
						: null,
					h(
						'span',
						{ class: 'text-sm text-ink-gray-7 truncate' },
						option.label,
					),
				],
			);

		return () =>
			h('div', { class: 'flex flex-col gap-2' }, [
				h(FormControl, {
					type: 'text',
					placeholder: 'Search products',
					modelValue: query.value,
					'onUpdate:modelValue': (value) => {
						query.value = value;
					},
				}),
				h(
					'div',
					{
						class: 'flex flex-col gap-1 overflow-hidden',
						style: 'max-height: 220px; overflow-y: auto',
					},
					options.value.length
						? options.value.map(tile)
						: [
								h(
									'span',
									{ class: 'text-p-sm text-ink-gray-5 px-2' },
									'No products match.',
								),
						  ],
				),
			]);
	},
};

const CollectionPicker = {
	props: ['preview'],
	setup(props) {
		const pageStore = usePageStore();
		return () =>
			h(FormControl, {
				type: 'select',
				options: props.preview.options.map((option) => ({
					label: option.label,
					value: option.value,
				})),
				modelValue: pageStore.routeVariables.category || '',
				'onUpdate:modelValue': (value) =>
					pageStore.setRouteVariable('category', value),
			});
	},
};

const ThemePanel = {
	props: ['bar', 'onChanged'],
	setup(props) {
		const pageStore = usePageStore();
		const busy = ref('');

		async function publish() {
			busy.value = 'publish';
			try {
				await pageStore.waitTillPageIsSaved();
				const result = await call(`${API}publish_theme`, {
					theme: props.bar.theme,
				});
				const skipped = result.skipped.length
					? ` ${result.skipped.join(', ')} not built yet, so not published.`
					: '';
				toast.success(
					`Published ${result.published.join(', ') || 'nothing'}.${skipped}`,
				);
				pageStore.activePage = await pageStore.fetchActivePage(
					pageStore.selectedPage,
				);
				props.onChanged();
			} catch (error) {
				toast.error(error?.messages?.[0] || 'Could not publish the theme');
			} finally {
				busy.value = '';
			}
		}

		async function make_live() {
			busy.value = 'live';
			try {
				await call(`${API}make_theme_live`, { theme: props.bar.theme });
				toast.success(`${props.bar.theme} is now your live theme.`);
				props.onChanged();
			} catch (error) {
				toast.error(error?.messages?.[0] || 'Could not make the theme live');
			} finally {
				busy.value = '';
			}
		}

		function view_on_store() {
			let path = props.bar.storefront_path;
			if (props.bar.page_type === 'Product Detail') {
				path +=
					pageStore.routeVariables.route ||
					props.bar.preview.options[0]?.value ||
					'';
			} else if (
				props.bar.page_type === 'Product Listing' &&
				pageStore.routeVariables.category
			) {
				path += `?category=${encodeURIComponent(
					pageStore.routeVariables.category,
				)}`;
			}
			window.open(path, '_blank');
		}

		const preview = () => {
			const { preview } = props.bar;
			if (!preview) return null;
			const picker =
				preview.variable === 'route' ? ProductPicker : CollectionPicker;
			return h('div', { class: 'flex flex-col gap-2' }, [
				h(
					'span',
					{ class: 'text-xs font-medium text-ink-gray-5' },
					`Preview with ${preview.label.toLowerCase()}`,
				),
				h(picker, { preview, key: props.bar.page_type }),
			]);
		};

		return () =>
			h('div', { class: 'flex flex-col gap-3 p-3', style: 'width: 320px' }, [
				h('div', { class: 'flex items-center justify-between gap-2' }, [
					h(
						'span',
						{ class: 'text-base font-medium text-ink-gray-9 truncate' },
						props.bar.theme,
					),
					h(Badge, {
						label: props.bar.is_live ? 'Live' : 'Not live',
						theme: props.bar.is_live ? 'green' : 'gray',
					}),
				]),
				h(PageTabs, { bar: props.bar }),
				preview(),
				h('div', { class: 'flex flex-col gap-2' }, [
					h(Button, {
						label: 'Publish theme',
						variant: props.bar.is_live ? 'solid' : 'subtle',
						loading: busy.value === 'publish',
						onClick: publish,
					}),
					props.bar.is_live
						? h(Button, {
								label: 'View on store',
								variant: 'ghost',
								iconLeft: 'lucide-external-link',
								onClick: view_on_store,
						  })
						: h(Button, {
								label: 'Make live',
								variant: 'solid',
								loading: busy.value === 'live',
								onClick: make_live,
						  }),
				]),
				props.bar.is_live
					? null
					: h(
							'span',
							{ class: 'text-p-sm text-ink-gray-5' },
							'Published pages go to your store once the theme is live.',
					  ),
			]);
	},
};

const ThemeBar = {
	setup() {
		const pageStore = usePageStore();
		const bar = ref(null);
		const open = ref(false);
		const page_id = computed(() => pageStore.activePage?.name);

		async function load() {
			const page = page_id.value;
			const result = page
				? await call(`${API}get_theme_bar`, { page_id: page }).catch(() => null)
				: null;
			if (page === page_id.value) bar.value = result;
		}
		watch(page_id, load, { immediate: true });

		return () => {
			if (!bar.value) return null;
			const current = bar.value.pages.find(
				(page) => page.page_type === bar.value.page_type,
			);
			return h(
				Popover,
				{
					open: open.value,
					'onUpdate:open': (value) => {
						open.value = value;
					},
					side: 'bottom',
					align: 'center',
				},
				{
					trigger: () =>
						h(Button, {
							variant: 'subtle',
							size: 'sm',
							iconLeft: 'lucide-store',
							iconRight: 'lucide-chevron-down',
							label: `${bar.value.theme} · ${current?.label ?? ''}`,
						}),
					default: () => h(ThemePanel, { bar: bar.value, onChanged: load }),
				},
			);
		};
	},
};

export default {
	install() {
		toolbarItems.register({
			name: 'commera-theme-bar',
			region: 'center',
			component: ThemeBar,
		});
	},
};
