import { call } from 'frappe-ui';

const API = 'commera.api.admin.builder_theme.';

export const getThemeBar = (pageId) =>
	call(`${API}get_theme_bar`, { page_id: pageId });
export const searchProducts = (query) =>
	call(`${API}search_preview_products`, { query });
export const publishTheme = (theme) => call(`${API}publish_theme`, { theme });
export const makeThemeLive = (theme) =>
	call(`${API}make_theme_live`, { theme });

export const errorMessage = (error, fallback) =>
	error?.messages?.[0] || fallback;
