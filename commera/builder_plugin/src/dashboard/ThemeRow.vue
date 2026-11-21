<!-- Commera's ThemeRow, desktop layout only: the editor's stylesheet loads after ours, so its `flex-col`
	or `w-28` would beat an `sm:` variant here. -->
<template>
	<div
		class="relative flex items-center gap-4 px-4 hover:bg-surface-gray-1"
		:class="featured ? 'py-5' : 'py-3'">
		<img
			v-if="theme.preview"
			:src="theme.preview"
			alt=""
			class="shrink-0 rounded-4 border border-outline-gray-2 bg-surface-gray-2 object-cover object-top"
			:class="imageSize" />
		<span v-else class="shrink-0 rounded-4 bg-surface-gray-3" :class="imageSize" aria-hidden="true" />
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<button
					type="button"
					class="truncate text-left text-ink-gray-9 after:absolute after:inset-0 after:rounded-[inherit] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-outline-gray-3"
					:class="featured ? 'text-lg-semibold' : 'text-base font-medium'"
					:aria-label="`Open ${theme.theme}`"
					@click="$emit('open', theme.theme)">
					{{ theme.theme }}
				</button>
				<Badge v-if="theme.is_live" label="Live" theme="green" variant="subtle" />
			</div>
			<PageDots class="mt-1" :pages="theme.pages" />
		</div>
		<Button
			v-if="!theme.is_live"
			class="relative z-10"
			label="Switch Theme"
			:loading="activating"
			:disabled="disabled"
			@click="$emit('activate', theme)" />
		<component :is="ChevronIcon" class="!size-4 shrink-0 text-ink-gray-5 rtl:-scale-x-100" />
	</div>
</template>

<script setup>
import { lucideIcon } from 'builder';
import { Badge, Button } from 'frappe-ui';
import { computed } from 'vue';
import PageDots from './PageDots.vue';

const props = defineProps({
	theme: { type: Object, required: true },
	featured: { type: Boolean, default: false },
	activating: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
});
defineEmits(['open', 'activate']);

const ChevronIcon = lucideIcon('lucide-chevron-right');
const imageSize = computed(() => (props.featured ? 'aspect-video w-60' : 'aspect-video w-40'));
</script>
