import { toast } from 'frappe-ui';
import { ref } from 'vue';
import { errorMessage } from './api';

/** Runs one action at a time, toasts the message it answers with, or its error, and then calls `onDone`. */
export function useActions(onDone) {
	const busy = ref('');

	async function run(action, task, failure) {
		busy.value = action;
		try {
			toast.success(await task());
			onDone();
		} catch (error) {
			toast.error(errorMessage(error, failure));
		} finally {
			busy.value = '';
		}
	}

	return { busy, run };
}

export function publishedMessage({ published, skipped }) {
	if (!published.length) return 'Nothing to publish yet: every page is empty.';
	const empty = skipped.length
		? ` ${listOf(skipped)} ${
				skipped.length > 1 ? 'are' : 'is'
		  } empty, so not published.`
		: '';
	return `Published ${listOf(published)}.${empty}`;
}

const listOf = (labels) =>
	new Intl.ListFormat('en', { type: 'conjunction' }).format(labels);
