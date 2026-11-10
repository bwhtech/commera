// Python's round() and '%.*f' work on the exact binary value of a float. These do the same
// with BigInt, so a large or high-precision amount keeps every digit Python prints.

// BigInt() calls, not literals: the dashboard builds for ES2015, which has neither 52n nor **.
const ONE = BigInt(1);
const TWO = BigInt(2);
const FIVE = BigInt(5);
const TEN = BigInt(10);
const MANTISSA_BITS = BigInt(52);

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
	const exponent = Number(bits >> MANTISSA_BITS);
	const fraction = bits & ((ONE << MANTISSA_BITS) - ONE);
	const mantissa = exponent ? fraction | (ONE << MANTISSA_BITS) : fraction;
	const power = Math.max(exponent, 1) - 1075;
	if (power >= 0) {
		return [mantissa << BigInt(power), 0];
	}
	return [mantissa * big_power(FIVE, BigInt(-power)), -power];
}

// The value in units of 10 ** -precision, a tie going to the even unit.
function round_units([digits, scale], precision) {
	if (scale <= precision) {
		return digits * big_power(TEN, BigInt(precision - scale));
	}
	const divisor = big_power(TEN, BigInt(scale - precision));
	const units = digits / divisor;
	const twice_rest = (digits % divisor) * TWO;
	const rounds_up =
		twice_rest > divisor || (twice_rest === divisor && units % TWO === ONE);
	return rounds_up ? units + ONE : units;
}

function units_to_text(units, precision) {
	const text = units.toString().padStart(precision + 1, '0');
	return precision
		? `${text.slice(0, -precision)}.${text.slice(-precision)}`
		: text;
}

function big_power(base, exponent) {
	let result = ONE;
	for (let step = BigInt(0); step < exponent; step += ONE) result *= base;
	return result;
}
