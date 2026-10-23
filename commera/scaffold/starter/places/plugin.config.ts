import { definePlugin } from '@commera/plugin-kit';

export default definePlugin({
	sidebar: [
		{
			name: 'settings',
			label: 'Settings',
			icon: 'settings',
			order: 9,
			run: ({ openSettings }) => openSettings(),
		},
	],
});
