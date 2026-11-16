import { toolbarItems } from 'builder';
import './index.css';
import ThemeBar, { openThemeBar } from './ThemeBar.vue';

export default {
	install(_app, context) {
		toolbarItems.register({
			name: 'commera-theme-bar',
			region: 'center',
			component: ThemeBar,
		});
		context.setOpenHandler(openThemeBar);
	},
};
