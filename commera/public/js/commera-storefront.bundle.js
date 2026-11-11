import * as commera from '../../../packages/storefront/index.js';

window.commera = commera;

// Alpine starts after this script, so bindings that call commera.t() see the dictionary arrive.
document.addEventListener('alpine:init', () => {
	commera.make_translations_reactive(window.Alpine.reactive);
});
commera.load_translations();

if (window.commera_storefront_config?.webmcp) {
	commera.webmcp.register_tools();
}
