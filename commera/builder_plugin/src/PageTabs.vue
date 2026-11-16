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

const props = defineProps({ bar: { type: Object, required: true } });

// the editor's page status dots: filled is live, hollow is a draft or edits waiting to publish
const STATUS_DOTS = {
	Published: 'bg-current text-ink-green-7',
	Edited: 'border-[1.5px] border-current text-ink-green-7',
	Draft: 'border-[1.5px] border-current text-ink-gray-4',
	Empty: 'border-[1.5px] border-dashed border-current text-ink-gray-4',
};
const STATUS_HINTS = {
	Published: 'Published',
	Edited: 'Published, with changes not published yet',
	Draft: 'Not published yet',
	Empty: 'Nothing on this page yet, so the store shows the parent theme here',
};

const isCurrent = (page) => page.page_type === props.bar.page_type;

function status(page) {
	if (!page.is_published) return page.is_empty ? 'Empty' : 'Draft';
	return page.has_unpublished_changes ? 'Edited' : 'Published';
}

function open(page) {
	if (!isCurrent(page))
		router.push({ name: 'builder', params: { pageId: page.page } });
}
</script>
