<!-- One page of a theme, in the row style of Commera's Themes screen. A click opens it in the editor. -->
<template>
	<div class="relative flex items-center gap-4 px-4 py-3 hover:bg-surface-gray-1">
		<img
			v-if="page.preview"
			:src="page.preview"
			alt=""
			class="aspect-video w-40 shrink-0 rounded-4 border border-outline-gray-2 bg-surface-gray-2 object-cover object-top" />
		<span
			v-else
			class="flex aspect-video w-40 shrink-0 items-center justify-center rounded-4 bg-surface-gray-3"
			aria-hidden="true">
			<component :is="page.is_empty ? SparklesIcon : ImageIcon" class="!size-5 text-ink-gray-4" />
		</span>
		<div class="min-w-0 flex-1">
			<button
				type="button"
				class="truncate text-left text-base font-medium text-ink-gray-9 after:absolute after:inset-0 after:rounded-[inherit] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-outline-gray-3"
				:aria-label="`Edit the ${page.label} page`"
				@click="openPage(page.page, { askBob: page.is_empty })">
				{{ page.label }}
			</button>
			<p class="mt-1 flex items-center gap-1.5 text-sm text-ink-gray-5">
				<span class="size-1.5 shrink-0 rounded-full" :class="STATUS_DOTS[status]" />
				<span class="truncate">{{ page.is_empty ? 'Empty. Open it to ask Bob to design it.' : STATUS_HINTS[status] }}</span>
			</p>
		</div>
		<component :is="ChevronIcon" class="!size-4 shrink-0 text-ink-gray-5 rtl:-scale-x-100" />
	</div>
</template>

<script setup>
import { lucideIcon } from 'builder';
import { computed } from 'vue';
import { STATUS_DOTS, STATUS_HINTS, pageStatus } from '../pageStatus';
import { openPage } from '../storeThemes';

const props = defineProps({ page: { type: Object, required: true } });

const ChevronIcon = lucideIcon('lucide-chevron-right');
const ImageIcon = lucideIcon('lucide-image');
const SparklesIcon = lucideIcon('lucide-sparkles');
const status = computed(() => pageStatus(props.page));
</script>
