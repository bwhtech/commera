// A write that returns store or shopper text still marks it untrusted.
export const RETURNS_STORE_DATA = { untrustedContentHint: true };
export const READS_STORE_DATA = {
	readOnlyHint: true,
	untrustedContentHint: true,
};
export const NO_INPUT = { type: 'object', properties: {} };

export function navigate(path) {
	globalThis.location.assign(path);
	return { navigating_to: path };
}
