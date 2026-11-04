import assert from 'node:assert/strict';
import { test } from 'node:test';
import { select_variant } from '../product.js';

const small = { id: 'RUNNER-BLUE-S', title: 'S', available: true };
const medium = { id: 'RUNNER-BLUE-M', title: 'M', available: false };
const product = {
	options: [
		{
			name: 'Colour',
			values: [
				{ name: 'Blue', handle: 'runner-blue', selected: true },
				{ name: 'Red', handle: 'runner-red', selected: false },
			],
		},
		{ name: 'Größe', values: [{ name: 'S' }, { name: 'M' }] },
	],
	variants: [small, medium],
};

test('select_variant matches the size option, whatever its translated name', () => {
	assert.equal(select_variant(product, { Colour: 'Blue', Größe: 'M' }), medium);
});

test('select_variant returns null until a size is chosen', () => {
	assert.equal(select_variant(product, { Colour: 'Blue' }), null);
	assert.equal(select_variant(product, { Größe: 'XL' }), null);
});

test('select_variant returns the only variant of a one-size product', () => {
	assert.equal(select_variant({ options: [], variants: [small] }), small);
});
