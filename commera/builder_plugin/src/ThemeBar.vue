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
		<ThemePanel :bar="bar" @changed="load" />
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
const pageId = computed(() => pageStore.activePage?.name);
const currentPage = computed(() => bar.value?.pages.find((page) => page.page_type === bar.value.page_type));

async function load() {
	const page = pageId.value;
	const result = page ? await getThemeBar(page).catch(() => null) : null;
	// a slow reply for a page the editor has left must not show
	if (page === pageId.value) bar.value = result;
}
watch(pageId, load, { immediate: true });

watch(isOpen, (open) => {
	if (open && !bar.value) {
		isOpen.value = false;
		toast.info('Open a page of a Commera theme to see its theme bar.');
	}
});
</script>
