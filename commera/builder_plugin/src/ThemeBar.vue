<template>
	<Popover v-if="bar" v-model:open="isOpen" side="bottom" align="center" :offset="8">
		<template #trigger>
			<Button
				variant="subtle"
				:icon-left="StoreIcon"
				:icon-right="ChevronIcon"
				:title="`${bar.theme} · ${currentPage?.label ?? ''}`">
				<span class="flex min-w-0 items-center gap-1">
					<span class="max-w-40 truncate">{{ bar.theme }}</span>
					<span class="text-ink-gray-4">·</span>
					<span class="shrink-0">{{ currentPage?.label }}</span>
				</span>
			</Button>
		</template>
		<ThemePanel :bar="bar" :is-stale="barPage !== pageId" @changed="load" />
	</Popover>
</template>

<script>
import { ref } from 'vue';

const isOpen = ref(false);

/** The Open button in the plugin's details page. */
export const openThemeBar = () => {
	isOpen.value = true;
};
</script>

<script setup>
import { lucideIcon, usePageStore } from 'builder';
import { Button, Popover, toast } from 'frappe-ui';
import { computed, watch } from 'vue';
import { getThemeBar } from './api';
import ThemePanel from './ThemePanel.vue';

const StoreIcon = lucideIcon('lucide-store');
const ChevronIcon = lucideIcon('lucide-chevron-down');

const pageStore = usePageStore();
const bar = ref(null);
// the page `bar` was loaded for; until the new page's bar arrives, the panel is disabled
const barPage = ref(null);
const pageId = computed(() => pageStore.activePage?.name);
const currentPage = computed(() => bar.value?.pages.find((page) => page.page_type === bar.value.page_type));

let latest = 0;
async function load() {
	const request = ++latest;
	const page = pageId.value;
	const result = page ? await getThemeBar(page).catch(() => null) : null;
	// a slow reply must not replace a newer one, or show for a page the editor has left
	if (request !== latest || page !== pageId.value) return;
	bar.value = result;
	barPage.value = page;
}
watch(pageId, load, { immediate: true });

watch(isOpen, (open) => {
	if (!open) return;
	if (!bar.value) {
		isOpen.value = false;
		toast.info('Open a page of a Commera theme to see its theme bar.');
		return;
	}
	// the editor's own saves and Publish button change the page statuses
	load();
});
</script>
