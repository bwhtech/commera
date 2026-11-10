import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { load_translations, make_translations_reactive, t } from '../index.js';

const ARABIC = {
	'Add to cart': 'أضف إلى السلة',
	'Only {0} left': 'تبقّى {0} فقط',
};

function open_page(language, translations_version) {
	globalThis.commera_storefront_config = {
		localization: {
			language: { code: language },
			default_language: { code: 'en' },
		},
		translations_version,
	};
}

function add_dictionary(messages, { status = 200 } = {}) {
	const urls = [];
	globalThis.fetch = async (url) => {
		urls.push(url);
		return {
			ok: status < 400,
			status,
			json: async () => ({ data: messages }),
		};
	};
	return urls;
}

beforeEach(async () => {
	globalThis.commera_storefront_config = undefined;
	await load_translations();
});

test('t returns the translation of the page language', async () => {
	const urls = add_dictionary(ARABIC);
	open_page('ar', 'v1');
	await load_translations();

	assert.equal(t('Add to cart'), 'أضف إلى السلة');
	assert.deepEqual(urls, [
		'/api/v2/method/commera.api.storefront.translations.get_translations?lang=ar&v=v1',
	]);
});

test('t fills numbered placeholders', async () => {
	add_dictionary(ARABIC);
	open_page('ar', 'v2');
	await load_translations();

	assert.equal(t('Only {0} left', 3), 'تبقّى 3 فقط');
	assert.equal(t('{0} of {1}', 1, 5), '1 of 5');
	assert.equal(t('{0} and {1}', 'one'), 'one and {1}');
});

test('t falls back to the source text', async () => {
	add_dictionary(ARABIC);
	open_page('ar', 'v3');
	await load_translations();

	assert.equal(t('Checkout'), 'Checkout');
	assert.equal(t(undefined), '');
});

test('a page without a dictionary version fetches nothing', async () => {
	const urls = add_dictionary(ARABIC);
	open_page('en', null);
	await load_translations();

	assert.deepEqual(urls, []);
	assert.equal(t('Add to cart'), 'Add to cart');
});

test('the dictionary is fetched once per language and version', async () => {
	const urls = add_dictionary(ARABIC);
	open_page('ar', 'v4');
	await Promise.all([load_translations(), load_translations()]);
	await load_translations();

	assert.equal(urls.length, 1);
});

test('a failed fetch leaves the source text', async () => {
	add_dictionary(null, { status: 500 });
	open_page('ar', 'v5');
	await load_translations();

	assert.equal(t('Add to cart'), 'Add to cart');
});

test('a reactive wrapper sees the dictionary arrive', async () => {
	const assigned = [];
	make_translations_reactive((target) => {
		return new Proxy(target, {
			set(object, key, value) {
				assigned.push(key);
				object[key] = value;
				return true;
			},
		});
	});
	add_dictionary(ARABIC);
	open_page('ar', 'v6');
	await load_translations();

	assert.ok(assigned.includes('messages'));
	assert.equal(t('Add to cart'), 'أضف إلى السلة');
});
