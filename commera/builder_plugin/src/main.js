import { toolbarItems } from 'builder';
import ThemeBar from './ThemeBar.vue';
import './index.css';
import { openStoreThemes, registerStoreThemes } from './storeThemes';

export default {
	install(_app, context) {
		toolbarItems.register({
			name: 'commera-theme-bar',
			region: 'center',
			component: ThemeBar,
		});
		if (registerStoreThemes()) context.setOpenHandler(openStoreThemes);
	},
};
