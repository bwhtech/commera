<template>
	<span class="flex min-w-0 items-center gap-3">
		<span
			v-for="page in pages"
			:key="page.page_type"
			class="flex items-center gap-1 text-sm text-ink-gray-6"
			:title="`${page.label}: ${STATUS_HINTS[pageStatus(page)]}`">
			<span class="size-1.5 shrink-0 rounded-full" :class="STATUS_DOTS[pageStatus(page)]" />
			{{ page.label }}
		</span>
	</span>
</template>

<script setup>
import { STATUS_DOTS, STATUS_HINTS, pageStatus } from '../pageStatus';

defineProps({ pages: { type: Array, required: true } });
</script>
