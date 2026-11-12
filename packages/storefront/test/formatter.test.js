import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Formatter } from '../formatter.js';

// commera/localization/test_formatter.py reads the same cases, so both formatters give one answer.
const cases = JSON.parse(
	readFileSync(new URL('./formatter-cases.json', import.meta.url)),
);

function formatter_for(language, options = {}) {
	return new Formatter({
		language,
		...cases.languages[language],
		currency_symbols: cases.currency_symbols,
		money_formats: cases.money_formats.currency_format_on,
		date_formats: cases.date_formats[language],
		...options,
	});
}

// `rules` names the money formats the server resolves under one set of System Settings.
test('money matches the Python formatter for each language and currency', () => {
	for (const {
		language,
		rules,
		currency,
		amount,
		precision,
		expected,
	} of cases.money) {
		const money_formats = cases.money_formats[rules];
		assert.equal(
			formatter_for(language, { money_formats }).money(
				amount,
				currency,
				precision ?? undefined,
			),
			expected,
			`${language} ${rules} ${currency} ${amount}`,
		);
	}
});

test('number matches the Python formatter for each language', () => {
	for (const {
		language,
		number_format,
		value,
		precision,
		expected,
	} of cases.number) {
		const options = number_format ? { number_format } : {};
		assert.equal(
			formatter_for(language, options).number(value, precision),
			expected,
			`${language} ${number_format} ${value} ${precision}`,
		);
	}
});

test("date renders Babel's pattern for each Frappe language and style", () => {
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

test('money_text spells out a currency sign on the correct side', () => {
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
	const indian = formatter_for('en', { number_format: '#,##,###.##' });
	assert.equal(indian.compact_money(482300, 'INR'), '₹4.8L');
	assert.equal(formatter_for('en').compact_money(482300, 'INR'), '₹482.3K');
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

test('without the server patterns a date falls back to Intl, Gregorian and Latin digits', () => {
	const persian = new Formatter({ language: 'fa' });
	assert.equal(persian.date('2026-03-05', 'short'), '2026/3/5');
	assert.throws(() => persian.date('2026-03-05', 'tiny'), RangeError);
});

test('a currency the server did not resolve takes the language format', () => {
	const german = formatter_for('de', { money_formats: {} });
	assert.equal(german.money(1234.5, 'JPY'), '¥1.234,50');
	assert.equal(german.money(1.2, 'KWD', 3), 'د.ك1,20');
});

test('an unknown number format falls back to the default', () => {
	assert.equal(
		new Formatter({ number_format: '#~###' }).number(1234567),
		'1,234,567',
	);
});

test('decimal.js avoids syntax the ES2015 dashboard build cannot keep for BigInt', () => {
	// esbuild turns ** into Math.pow, which throws on a BigInt, and cannot lower 52n at all.
	const code = readFileSync(new URL('../decimal.js', import.meta.url), 'utf8')
		.split('\n')
		.filter((line) => !line.trim().startsWith('//'))
		.join('\n');
	assert.doesNotMatch(code, /\*\*/);
	assert.doesNotMatch(code, /\b\d+n\b/);
});
