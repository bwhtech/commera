<!-- One theme, in the style of Commera's Themes screen: its card, then its three pages. -->
<template>
	<div class="flex h-full flex-col">
		<PageHeader>
			<Breadcrumbs class="min-w-0" :items="breadcrumbs" />
			<div v-if="details" class="flex shrink-0 items-center gap-2">
				<Button label="Publish theme" :loading="busy === 'publish'" :disabled="Boolean(busy)" @click="publish" />
				<Button
					v-if="details.is_live"
					label="View on store"
					:icon-right="ExternalLinkIcon"
					@click="viewOnStore" />
				<Button
					v-else
					label="Switch Theme"
					variant="solid"
					theme="gray"
					:loading="Boolean(activating)"
					:disabled="Boolean(busy)"
					@click="confirmActivate(details)" />
			</div>
		</PageHeader>

		<div class="flex-1 overflow-y-auto">
			<PageBody>
				<EmptyState v-if="failure" :icon="AlertIcon" :title="`Could not open ${theme}`" :description="failure">
					<Button label="Back to store themes" @click="emit('back')" />
				</EmptyState>
				<div v-else-if="!details" aria-hidden="true">
					<div class="flex items-center gap-4 rounded-5 border border-outline-gray-2 px-4 py-5">
						<Skeleton class="aspect-video w-44 shrink-0 rounded-4" />
						<div class="min-w-0 flex-1">
							<Skeleton class="h-4 w-32 rounded-4" />
							<Skeleton class="mt-2 h-3.5 w-56 max-w-full rounded-4" />
						</div>
					</div>
				</div>
				<template v-else>
					<section>
						<h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">
							{{ details.is_live ? 'Live theme' : 'Theme library' }}
						</h2>
						<div class="mt-2 flex items-center gap-4 rounded-5 border border-outline-gray-2 px-4 py-5">
							<img
								v-if="details.preview"
								:src="details.preview"
								alt=""
								class="aspect-video w-60 shrink-0 rounded-4 border border-outline-gray-2 bg-surface-gray-2 object-cover object-top" />
							<span v-else class="aspect-video w-60 shrink-0 rounded-4 bg-surface-gray-3" aria-hidden="true" />
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2">
									<span class="truncate text-lg-semibold text-ink-gray-9">{{ details.theme }}</span>
									<Badge v-if="details.is_live" label="Live" theme="green" variant="subtle" />
								</div>
								<p class="mt-1 text-sm text-ink-gray-5">
									{{ details.is_live ? 'Shoppers see this theme.' : 'Shoppers do not see this theme yet.' }}
								</p>
							</div>
						</div>
					</section>

					<section class="mt-8">
						<h2 class="text-sm font-medium uppercase tracking-wide text-ink-gray-5">Pages</h2>
						<p class="text-p-sm text-ink-gray-5">
							An empty page is not published, so the store shows the starter theme's page there.
						</p>
						<div class="mt-2 divide-y divide-outline-gray-1 overflow-hidden rounded-5 border border-outline-gray-2">
							<PageRow v-for="page in details.pages" :key="page.page_type" :page="page" />
						</div>
					</section>
				</template>
			</PageBody>
		</div>
	</div>
</template>

<script setup>
import { lucideIcon } from 'builder';
import { Badge, Breadcrumbs, Button, PageHeader, Skeleton } from 'frappe-ui';
import { computed, ref } from 'vue';
import { errorMessage, getTheme, publishTheme } from '../api';
import { STORE_THEMES_ROUTE } from '../storeThemes';
import { publishedMessage, useActions } from '../useActions';
import EmptyState from './EmptyState.vue';
import PageBody from './PageBody.vue';
import PageRow from './PageRow.vue';
import { useSwitchTheme } from './useSwitchTheme';

const props = defineProps({ theme: { type: String, required: true } });
const emit = defineEmits(['back']);

const AlertIcon = lucideIcon('lucide-triangle-alert');
const ExternalLinkIcon = lucideIcon('lucide-external-link');

const details = ref(null);
const failure = ref('');
const breadcrumbs = computed(() => [
	{ label: 'Store themes', route: STORE_THEMES_ROUTE },
	{ label: props.theme },
]);

async function load() {
	try {
		details.value = await getTheme(props.theme);
	} catch (error) {
		failure.value = errorMessage(error, 'Try again in a moment.');
	}
}
load();

const { busy, run } = useActions(load);
const { activating, confirmActivate } = useSwitchTheme(() => details.value?.live_theme, load);

const publish = () =>
	run('publish', async () => publishedMessage(await publishTheme(props.theme)), 'Could not publish the theme');

const viewOnStore = () => window.open(details.value.store_url, '_blank');
</script>
