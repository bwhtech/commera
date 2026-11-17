<template>
	<Select
		:options="preview.options.map(({ label, value }) => ({ label, value }))"
		:model-value="pageStore.routeVariables.category || ''"
		@update:model-value="(value) => pageStore.setRouteVariable('category', value)" />
</template>

<script setup>
import { usePageStore } from 'builder';
import { Select } from 'frappe-ui';

defineProps({ preview: { type: Object, required: true } });

const pageStore = usePageStore();
</script>
