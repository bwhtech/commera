<template>
	<div class="grid grid-cols-3 gap-0.5 rounded-4 bg-surface-gray-2 p-0.5">
		<button
			v-for="page in bar.pages"
			:key="page.page_type"
			type="button"
			class="flex min-w-0 flex-col items-start gap-0.5 rounded-[7px] px-2 py-1.5 text-left transition-colors"
			:class="isCurrent(page) ? 'bg-surface-elevation-3 shadow-base' : 'hover:bg-surface-gray-3'"
			:aria-current="isCurrent(page) ? 'page' : undefined"
			:title="STATUS_HINTS[status(page)]"
			@click="open(page)">
			<span class="w-full truncate text-sm font-medium text-ink-gray-9">{{ page.label }}</span>
			<span class="flex items-center gap-1 text-xs text-ink-gray-5">
				<span class="size-1.5 shrink-0 rounded-full" :class="STATUS_DOTS[status(page)]" />
				{{ status(page) }}
			</span>
		</button>
	</div>
</template>

<script setup>
import router from 'builder/internal/router';
import { STATUS_DOTS, STATUS_HINTS, pageStatus as status } from './pageStatus';

const props = defineProps({ bar: { type: Object, required: true } });

const isCurrent = (page) => page.page_type === props.bar.page_type;

function open(page) {
	if (!isCurrent(page))
		router.push({ name: 'builder', params: { pageId: page.page } });
}
</script>
