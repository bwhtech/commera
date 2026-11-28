import { definePlugin } from '@commera/plugin-kit';

export default definePlugin({
	sidebar: [
		{
			name: 'open',
			label: 'Helpdesk',
			requires: 'HD Ticket',
			run: ({ openUrl }) => openUrl('/helpdesk'),
		},
	],
});
