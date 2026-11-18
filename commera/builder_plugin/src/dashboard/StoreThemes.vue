<template>
	<ThemeDetail v-if="path[0]" :key="path[0]" :theme="path[0]" @back="navigate([])" />
	<ThemeList v-else @open="(theme) => navigate([theme])" />
</template>

<script setup>
import ThemeDetail from './ThemeDetail.vue';
import ThemeList from './ThemeList.vue';

// Builder gives a dashboard view the URL after /dashboard/commera/, so a theme's page can be linked to
defineProps({
	path: { type: Array, required: true },
	navigate: { type: Function, required: true },
});
</script>
