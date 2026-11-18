<!-- Laid out as Commera's Themes screen (dashboard pages/storefront/Themes.vue): the live theme, then the library. -->
<template>
	<div class="flex h-full flex-col">
		<PageHeader>
			<h1 class="min-w-0 truncate text-lg-semibold text-ink-gray-8">Store themes</h1>
			<Button
				v-if="canCreateThemes()"
				label="New theme"
				:icon-left="PlusIcon"
				variant="solid"
				theme="gray"
				@click="isCreating = true" />
		</PageHeader>

		<div class="flex-1 overflow-y-auto">
			<PageBody>
				<div v-if="!themes" aria-hidden="true">
					<Skeleton class="h-3.5 w-24 rounded-4" />
					<div class="mt-2 flex items-center gap-4 rounded-5 border border-outline-gray-2 px-4 py-5">
						<Skeleton class="aspect-video w-44 shrink-0 rounded-4" />
						<div class="min-w-0 flex-1">
							<Skeleton class="h-4 w-32 rounded-4" />
							<Skeleton class="mt-2 h-3.5 w-56 max-w-full rounded-4" />
						</div>
					</div>
				</div>

				<EmptyState
					v-else-if="loadError"
					:icon="AlertIcon"
					title="Could not load store themes"
					:description="loadError" />

				<EmptyState
					v-else-if="!themes.length"
					:icon="PaletteIcon"
					title="No store themes yet"
					description="A new theme starts with empty Home, Listing and Product pages. Ask Bob to design them.">
					<Button
						v-if="canCreateThemes()"
						label="New theme"
						:icon-left="PlusIcon"
						@click="isCreating = true" />
				</EmptyState>

				<template v-else>
					<section v-if="liveTheme">
						<h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Live theme</h2>
						<div class="mt-2 overflow-hidden rounded-5 border border-outline-gray-2">
							<ThemeRow :theme="liveTheme" featured @open="emit('open', $event)" />
						</div>
					</section>

					<section v-if="libraryThemes.length" :class="{ 'mt-8': liveTheme }">
						<h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Theme library</h2>
						<p class="text-p-sm text-ink-gray-5">{{ libraryNote }}</p>
						<div class="mt-2 divide-y divide-outline-gray-1 overflow-hidden rounded-5 border border-outline-gray-2">
							<ThemeRow
								v-for="theme in libraryThemes"
								:key="theme.theme"
								:theme="theme"
								:activating="activating === theme.theme"
								:disabled="Boolean(activating)"
								@open="emit('open', $event)"
								@activate="confirmActivate" />
						</div>
					</section>
				</template>
			</PageBody>
		</div>

		<NewThemeDialog v-model:open="isCreating" />
	</div>
</template>

<script setup>
import { lucideIcon } from 'builder';
import { Button, PageHeader, Skeleton } from 'frappe-ui';
import { computed, ref } from 'vue';
import { errorMessage, getThemes } from '../api';
import { canCreateThemes } from '../storeThemes';
import EmptyState from './EmptyState.vue';
import NewThemeDialog from './NewThemeDialog.vue';
import PageBody from './PageBody.vue';
import ThemeRow from './ThemeRow.vue';
import { useSwitchTheme } from './useSwitchTheme';

const emit = defineEmits(['open']);

const PlusIcon = lucideIcon('lucide-plus');
const AlertIcon = lucideIcon('lucide-triangle-alert');
const PaletteIcon = lucideIcon('lucide-palette');

const themes = ref(null);
const liveThemeName = ref('');
const loadError = ref('');
const isCreating = ref(false);

const liveTheme = computed(() => themes.value?.find((theme) => theme.is_live) ?? null);
const libraryThemes = computed(() => themes.value?.filter((theme) => !theme.is_live) ?? []);
// the live theme can be one that is not designed in Builder, such as the starter theme
const libraryNote = computed(() =>
	liveTheme.value ? 'Shoppers only see the live theme.' : `Shoppers see ${liveThemeName.value} until you switch to one of these.`,
);

async function load() {
	try {
		const result = await getThemes();
		themes.value = result.themes;
		liveThemeName.value = result.live_theme;
	} catch (error) {
		themes.value = [];
		loadError.value = errorMessage(error, 'Try again in a moment.');
	}
}
load();

const { activating, confirmActivate } = useSwitchTheme(() => liveThemeName.value, load);
</script>
