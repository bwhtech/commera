import { definePlugin } from '@commera/plugin-kit';

export default definePlugin({
	sidebar: [
		{
			name: 'open',
			label: 'CRM',
			requires: 'CRM Lead',
			run: ({ openUrl }) => openUrl('/crm'),
		},
	],
});
