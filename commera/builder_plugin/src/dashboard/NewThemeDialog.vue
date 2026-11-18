<!-- Commera's New theme dialog (dashboard NewBuilderThemeDialog.vue). Here the Home page opens in this editor. -->
<template>
	<Dialog v-model:open="open" title="New theme" size="sm" :dismissible="!creating">
		<template #default>
			<form :id="formId" class="space-y-3" @submit.prevent="create">
				<FormControl v-model="themeName" label="Theme name" required placeholder="Autumn drop" />
				<p class="text-p-sm text-ink-gray-5">
					Its Home page opens next, where you can describe the design to Bob.
				</p>
				<ErrorMessage v-if="failure" :message="failure" />
			</form>
		</template>

		<template #actions>
			<Button
				class="w-full"
				type="submit"
				:form="formId"
				variant="solid"
				theme="gray"
				label="Create theme"
				:loading="creating" />
		</template>
	</Dialog>
</template>

<script setup>
import { Button, Dialog, ErrorMessage, FormControl } from 'frappe-ui';
import { ref, useId, watch } from 'vue';
import { createTheme, errorMessage } from '../api';
import { openPage, openTheme } from '../storeThemes';

const open = defineModel('open', { type: Boolean, required: true });

// the submit button sits outside the form, so `form` is what runs the name's `required` check
const formId = useId();

const themeName = ref('');
const creating = ref(false);
const failure = ref('');

watch(open, (isOpen) => {
	if (!isOpen) return;
	themeName.value = '';
	failure.value = '';
});

async function create() {
	creating.value = true;
	failure.value = '';
	try {
		const theme = await createTheme(themeName.value.trim());
		open.value = false;
		// without read access to Builder pages, the theme comes back with none
		const home = theme.pages.find((page) => page.page_type === 'Home');
		if (home) openPage(home.page, { askBob: true });
		else openTheme(theme.theme);
	} catch (error) {
		failure.value = errorMessage(error, 'Could not create the theme');
	} finally {
		creating.value = false;
	}
}
</script>
