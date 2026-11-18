<!-- Commera's EmptyState. The icon is a component, since a plugin cannot rely on the editor's icon classes. -->
<template>
	<div class="flex flex-col items-center justify-center gap-3 py-16 text-center" role="status">
		<div class="rounded-full bg-surface-gray-2 p-3 text-ink-gray-5">
			<component :is="icon" class="!size-6" />
		</div>
		<p class="text-base text-ink-gray-7">{{ title }}</p>
		<p v-if="description" class="text-sm text-ink-gray-5">{{ description }}</p>
		<slot />
	</div>
</template>

<script setup>
defineProps({
	icon: { type: [Object, Function], required: true },
	title: { type: String, required: true },
	description: { type: String, default: '' },
});
</script>
