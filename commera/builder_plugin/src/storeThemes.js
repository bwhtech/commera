import * as builder from 'builder';
import router from 'builder/internal/router';
import { ref } from 'vue';
import { getThemeAccess } from './api';
import StoreThemes from './dashboard/StoreThemes.vue';

const VIEW = 'commera';
export const STORE_THEMES_ROUTE = {
	name: 'dashboard-item',
	params: { item: VIEW },
};
const access = ref({ can_read: false, can_create: false });

export const canCreateThemes = () => access.value.can_create;

/** The Store themes view in Builder's dashboard, for users who can read themes. */
export function registerStoreThemes() {
	// a namespace import, so an editor without dashboard views still loads the theme bar
	if (!builder.dashboardItems) return false;
	builder.dashboardItems.register({
		name: VIEW,
		label: 'Store themes',
		icon: builder.lucideIcon('lucide-store'),
		component: StoreThemes,
		condition: () => access.value.can_read,
	});
	loadAccess();
	return true;
}

/** The Open button of the plugin's details page, in Settings. */
export function openStoreThemes() {
	// the editor's Settings dialog; the dashboard keeps its own open, and a plugin cannot close it
	builder.useBuilderStore().showSettingsDialog = false;
	router.push(STORE_THEMES_ROUTE);
}

/**
 * Opens a theme page in the editor. `askBob` opens it on the Chat tab, for a page with nothing on it yet.
 * The tab sets up AI itself when the site has none.
 */
export function openPage(page, { askBob = false } = {}) {
	if (askBob) builder.useBuilderStore().leftPanelActiveTab = 'Chat';
	router.push({ name: 'builder', params: { pageId: page } });
}

async function loadAccess() {
	try {
		access.value = await getThemeAccess();
	} catch {
		// without access the view stays hidden
	}
}
