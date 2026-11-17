import { toolbarItems } from 'builder';
import ThemeBar, { openThemeBar } from './ThemeBar.vue';
import './index.css';

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
