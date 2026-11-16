<template>
	<div class="flex flex-col gap-1.5">
		<TextInput v-model="query" placeholder="Search products" aria-label="Search products">
			<template #prefix>
				<component :is="SearchIcon" class="size-4 text-ink-gray-5" />
			</template>
			<template #suffix>
				<LoadingIndicator v-if="isSearching" class="size-3.5 text-ink-gray-5" />
			</template>
		</TextInput>
		<div class="-mx-1 flex max-h-56 flex-col gap-0.5 overflow-y-auto px-1">
			<button
				v-for="option in options"
				:key="option.value"
				type="button"
				class="flex items-center gap-2 rounded-[7px] px-1.5 py-1 text-left transition-colors"
				:class="option.value === selected ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
				:aria-pressed="option.value === selected"
				@click="pageStore.setRouteVariable('route', option.value)">
				<img
					v-if="option.image"
					:src="option.image"
					alt=""
					class="size-8 shrink-0 rounded-2 border border-outline-gray-1 bg-surface-gray-2 object-cover" />
				<span v-else class="flex size-8 shrink-0 items-center justify-center rounded-2 bg-surface-gray-2">
					<component :is="ImageIcon" class="size-4 text-ink-gray-4" />
				</span>
				<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">{{ option.label }}</span>
				<component :is="CheckIcon" v-if="option.value === selected" class="size-4 shrink-0 text-ink-gray-7" />
			</button>
			<p v-if="!options.length && !isSearching" class="px-1.5 py-2 text-p-sm text-ink-gray-5">
				{{ query ? `No products match "${query}".` : 'Your store has no products yet.' }}
			</p>
		</div>
	</div>
</template>

<script setup>
import { lucideIcon, usePageStore } from 'builder';
import { LoadingIndicator, TextInput } from 'frappe-ui';
import { computed, ref, watch } from 'vue';
import { searchProducts } from './api';

const props = defineProps({ preview: { type: Object, required: true } });

const SEARCH_DELAY_MS = 250;
const SearchIcon = lucideIcon('lucide-search');
const ImageIcon = lucideIcon('lucide-image');
const CheckIcon = lucideIcon('lucide-check');

const pageStore = usePageStore();
const query = ref('');
const options = ref(props.preview.options);
const isSearching = ref(false);
// with no product chosen, the canvas previews the newest one, which heads the first list
const selected = computed(
	() => pageStore.routeVariables.route || props.preview.options[0]?.value,
);

let timer = null;
// a slow reply for an older query must not overwrite a newer one
let latest = 0;

watch(query, (value) => {
	clearTimeout(timer);
	isSearching.value = true;
	timer = setTimeout(async () => {
		const request = ++latest;
		const results = await searchProducts(value.trim()).catch(() => []);
		if (request !== latest) return;
		options.value = results;
		isSearching.value = false;
	}, SEARCH_DELAY_MS);
});
</script>
