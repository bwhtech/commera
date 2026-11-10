import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Formatter } from '../formatter.js';

// commera/localization/test_formatter.py reads the same cases, so both formatters give one answer.
const cases = JSON.parse(
	readFileSync(new URL('./formatter-cases.json', import.meta.url)),
);

function formatter_for(language) {
	return new Formatter({
		language,
		...cases.languages[language],
		currency_symbols: cases.currency_symbols,
		currency_number_formats: cases.currency_number_formats,
	});
}

test('money matches the Python formatter for each language and currency', () => {
	for (const {
		language,
		currency,
		amount,
		precision,
		expected,
	} of cases.money) {
		assert.equal(
			formatter_for(language).money(amount, currency, precision ?? undefined),
			expected,
			`${language} ${currency} ${amount}`,
		);
	}
});

test('number matches the Python formatter for each language', () => {
	for (const { language, value, precision, expected } of cases.number) {
		assert.equal(
			formatter_for(language).number(value, precision),
			expected,
			`${language} ${value}`,
		);
	}
});

test('date matches the Python formatter for each language and style', () => {
	for (const { language, value, style, expected } of cases.date) {
		assert.equal(
			formatter_for(language).date(value, style),
			expected,
			`${language} ${value} ${style}`,
		);
	}
});

test('a right-to-left language puts the symbol after the amount', () => {
	const arabic = formatter_for('ar');
	assert.equal(arabic.money(1234.5, 'USD'), '1,234.50\u00a0$');
	assert.equal(formatter_for('en').money(1234.5, 'USD'), '$1,234.50');
	assert.equal(arabic.money(10, 'XTS'), '10.00\u00a0XTS');
});

test('money_text spells out an HTML symbol on the correct side', () => {
	assert.equal(
		formatter_for('en').money_text(1250, 'SAR'),
		'SAR\u00a01,250.00',
	);
	assert.equal(
		formatter_for('ar').money_text(1250, 'SAR'),
		'1,250.00\u00a0SAR',
	);
});

test('compact_money follows the number format and the direction', () => {
	assert.equal(formatter_for('en').compact_money(482300, 'INR'), '₹4.8L');
	assert.equal(formatter_for('en').compact_money(482300, 'USD'), '$482.3K');
	assert.equal(
		formatter_for('de').compact_money(1500000, 'EUR'),
		'€1,5\u00a0Mio.',
	);
	assert.equal(
		formatter_for('ar').compact_money(-1500, 'USD'),
		'-1.5\u00a0ألف\u00a0$',
	);
});

test('a Date keeps its local calendar day', () => {
	assert.equal(
		formatter_for('en').date(new Date(2026, 2, 5, 23, 30)),
		'Mar 5, 2026',
	);
	assert.equal(formatter_for('en').date(null), '');
});

test('an unknown number format falls back to the default', () => {
	assert.equal(
		new Formatter({ number_format: '#~###' }).number(1234567),
		'1,234,567',
	);
});
