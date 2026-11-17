<template>
	<div
		class="flex w-80 flex-col gap-4 p-3 transition-opacity"
		:class="{ 'pointer-events-none opacity-60': isStale }"
		:inert="isStale">
		<div class="flex items-start justify-between gap-2">
			<div class="flex min-w-0 flex-col gap-1">
				<span class="truncate text-base font-medium text-ink-gray-9">{{ bar.theme }}</span>
				<span class="text-p-sm text-ink-gray-5">
					{{ bar.is_live ? 'Shoppers see this theme.' : 'Shoppers do not see this theme yet.' }}
				</span>
			</div>
			<Badge v-if="bar.is_live" label="Live theme" theme="green" />
		</div>

		<PageTabs :bar="bar" />

		<div v-if="bar.preview" class="flex flex-col gap-1.5">
			<span class="text-sm font-medium text-ink-gray-7">Preview with {{ bar.preview.label.toLowerCase() }}</span>
			<ProductPicker v-if="bar.preview.variable === 'route'" :preview="bar.preview" />
			<CollectionPicker v-else :preview="bar.preview" />
		</div>

		<div class="grid grid-cols-2 gap-2 border-t border-outline-gray-1 pt-3">
			<Button
				label="Publish theme"
				:variant="bar.is_live ? 'solid' : 'subtle'"
				:loading="busy === 'publish'"
				:disabled="Boolean(busy)"
				@click="publish" />
			<Button
				v-if="bar.is_live"
				label="View on store"
				:icon-right="ExternalLinkIcon"
				@click="viewOnStore" />
			<Button
				v-else
				label="Activate theme"
				variant="solid"
				:loading="busy === 'activate'"
				:disabled="Boolean(busy)"
				@click="activate" />
		</div>
	</div>
</template>

<script setup>
import { lucideIcon, usePageStore } from 'builder';
import { Badge, Button, toast } from 'frappe-ui';
import { ref } from 'vue';
import CollectionPicker from './CollectionPicker.vue';
import PageTabs from './PageTabs.vue';
import ProductPicker from './ProductPicker.vue';
import { errorMessage, makeThemeLive, publishTheme } from './api';

const props = defineProps({
	bar: { type: Object, required: true },
	isStale: { type: Boolean, default: false },
});
const emit = defineEmits(['changed']);

const ExternalLinkIcon = lucideIcon('lucide-external-link');
const pageStore = usePageStore();
const busy = ref('');

/** Runs one action at a time, and toasts the message it answers with, or its error. */
async function run(action, task, failure) {
	busy.value = action;
	try {
		toast.success(await task());
		emit('changed');
	} catch (error) {
		toast.error(errorMessage(error, failure));
	} finally {
		busy.value = '';
	}
}

const publish = () => {
	const { theme } = props.bar;
	const pageName = pageStore.selectedPage;
	const pageLoadToken = pageStore.pageLoadToken;
	return run(
		'publish',
		async () => {
			await pageStore.waitTillPageIsSaved();
			const result = await publishTheme(theme);
			// the editor's own status pill and Publish button read the page
			const page = await pageStore.fetchActivePage(pageName);
			// another page may have opened meanwhile, and its canvas autosaves to activePage
			if (pageLoadToken === pageStore.pageLoadToken && pageStore.selectedPage === pageName) {
				pageStore.activePage = page;
			}
			return publishedMessage(result);
		},
		'Could not publish the theme',
	);
};

const activate = () => {
	const { theme } = props.bar;
	return run(
		'activate',
		async () => {
			await makeThemeLive(theme);
			return `${theme} is now the live theme`;
		},
		'Could not activate the theme',
	);
};

function publishedMessage({ published, skipped }) {
	if (!published.length) return 'Nothing to publish yet: every page is empty.';
	const empty = skipped.length
		? ` ${listOf(skipped)} ${skipped.length > 1 ? 'are' : 'is'} empty, so not published.`
		: '';
	return `Published ${listOf(published)}.${empty}`;
}

const listOf = (labels) =>
	new Intl.ListFormat('en', { type: 'conjunction' }).format(labels);

function viewOnStore() {
	const { bar } = props;
	const variables = pageStore.routeVariables;
	let path = bar.storefront_path;
	if (bar.page_type === 'Product Detail') {
		path += encodeURIComponent(
			variables.route || bar.preview.options[0]?.value || '',
		);
	} else if (bar.page_type === 'Product Listing' && variables.category) {
		path += `?category=${encodeURIComponent(variables.category)}`;
	}
	window.open(path, '_blank');
}
</script>
