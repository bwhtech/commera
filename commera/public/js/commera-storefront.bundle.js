import * as commera from '../../../packages/storefront/index.js';

window.commera = commera;

if (window.commera_storefront_config?.webmcp) {
	commera.webmcp.register_tools();
}
