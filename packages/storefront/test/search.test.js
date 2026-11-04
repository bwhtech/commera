import assert from 'node:assert/strict';
import { test } from 'node:test';
import { get_recommendations, get_typeahead } from '../search.js';
import { add_fake_fetch } from './fake-fetch.js';

test('get_typeahead sends the query and limit with GET', async () => {
	const typeahead = { products: [], collections: [] };
	const calls = add_fake_fetch({
		get_typeahead: { body: { data: typeahead } },
	});
	assert.deepEqual(await get_typeahead('run shoe', 4), typeahead);
	assert.equal(calls[0].options.method, 'GET');
	assert.equal(
		calls[0].url,
		'/api/v2/method/commera.api.storefront.search.get_typeahead?query=run+shoe&limit=4',
	);
});

test('get_typeahead leaves out a missing limit so the server default applies', async () => {
	const calls = add_fake_fetch();
	await get_typeahead('runner');
	assert.equal(
		calls[0].url,
		'/api/v2/method/commera.api.storefront.search.get_typeahead?query=runner',
	);
});

test('get_recommendations sends the product handle and limit with GET', async () => {
	const cards = [{ id: 'RUNNER-RED', handle: 'runner-red' }];
	const calls = add_fake_fetch({
		get_recommendations: { body: { data: cards } },
	});
	assert.deepEqual(await get_recommendations('runner-blue', 8), cards);
	assert.equal(calls[0].options.method, 'GET');
	assert.equal(
		calls[0].url,
		'/api/v2/method/commera.api.storefront.search.get_recommendations?handle=runner-blue&limit=8',
	);
});

test('get_recommendations without a handle throws before calling the store', async () => {
	const calls = add_fake_fetch();
	await assert.rejects(get_recommendations(undefined, 4), {
		name: 'StorefrontError',
		message: 'A product handle is required.',
	});
	assert.equal(calls.length, 0);
});
