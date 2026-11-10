// Python's round() and '%.*f' work on the exact binary value of a float. These do the same
// with BigInt, so a large or high-precision amount keeps every digit Python prints.

// '%.*f' % (precision, round(value, precision)) without the sign, as fmt_money writes it.
export function python_fixed(value, precision) {
	const rounded = python_round(value, precision);
	return units_to_text(
		round_units(exact_decimal(rounded), precision),
		precision,
	);
}

// round(value, precision): the exact value rounded half to even, then read back as a float.
export function python_round(value, precision) {
	const units = round_units(exact_decimal(value), precision);
	const rounded = Number(units_to_text(units, precision));
	return value < 0 ? -rounded : rounded;
}

// |value| as [digits, scale], where |value| = digits / 10 ** scale exactly.
function exact_decimal(value) {
	const view = new DataView(new ArrayBuffer(8));
	view.setFloat64(0, Math.abs(value));
	const bits = view.getBigUint64(0);
	const exponent = Number(bits >> 52n);
	const fraction = bits & ((1n << 52n) - 1n);
	const mantissa = exponent ? fraction | (1n << 52n) : fraction;
	const power = Math.max(exponent, 1) - 1075;
	if (power >= 0) {
		return [mantissa << BigInt(power), 0];
	}
	return [mantissa * 5n ** BigInt(-power), -power];
}

// The value in units of 10 ** -precision, a tie going to the even unit.
function round_units([digits, scale], precision) {
	if (scale <= precision) {
		return digits * 10n ** BigInt(precision - scale);
	}
	const divisor = 10n ** BigInt(scale - precision);
	const units = digits / divisor;
	const twice_rest = (digits % divisor) * 2n;
	const rounds_up =
		twice_rest > divisor || (twice_rest === divisor && units % 2n === 1n);
	return rounds_up ? units + 1n : units;
}

function units_to_text(units, precision) {
	const text = units.toString().padStart(precision + 1, '0');
	return precision
		? `${text.slice(0, -precision)}.${text.slice(-precision)}`
		: text;
}
