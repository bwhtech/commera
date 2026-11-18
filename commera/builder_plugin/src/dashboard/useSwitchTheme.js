import { dialog, toast } from 'frappe-ui';
import { ref } from 'vue';
import { makeThemeLive } from '../api';

/** Commera's Switch Theme confirmation. `liveTheme` gives the theme shoppers see now. */
export function useSwitchTheme(liveTheme, onSwitched) {
	const activating = ref('');

	function confirmActivate({ theme }) {
		const previous = liveTheme();
		dialog.confirm({
			title: `Switch to ${theme}?`,
			message: previous
				? `Shoppers see ${theme} straight away. ${previous} moves to the theme library and keeps all its changes.`
				: `Shoppers see ${theme} straight away.`,
			confirmLabel: 'Switch Theme',
			onConfirm: async () => {
				activating.value = theme;
				try {
					await makeThemeLive(theme);
					toast.success(`${theme} is now the live theme`);
					await onSwitched();
				} finally {
					activating.value = '';
				}
			},
		});
	}

	return { activating, confirmActivate };
}
