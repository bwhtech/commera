// Renders the Babel patterns of commera/localization/date_formats.py the way Babel prints them:
// Gregorian, Latin digits, names from the server. `date` is a UTC midnight Date.
export function render_date(date, { parts, names }, style) {
	return parts[style]
		.map((part) => part.text ?? render_field(date, part.field, names))
		.join('');
}

function render_field(date, field, names) {
	if (names[field]) {
		return names[field][name_index(date, field[0])];
	}
	switch (field[0]) {
		case 'y':
			return field.length === 2
				? pad(date.getUTCFullYear(), 2).slice(-2)
				: pad(date.getUTCFullYear(), field.length);
		case 'M':
		case 'L':
			return pad(date.getUTCMonth() + 1, field.length);
		case 'd':
			return pad(date.getUTCDate(), field.length);
		default:
			throw new RangeError(`Date field ${field} is not supported.`);
	}
}

// Eras are BC then AD, months start in January and weekdays on Monday, as Babel indexes them.
function name_index(date, char) {
	if (char === 'G') {
		return 1;
	}
	if (char === 'M' || char === 'L') {
		return date.getUTCMonth();
	}
	return (date.getUTCDay() + 6) % 7;
}

function pad(value, length) {
	return String(value).padStart(length, '0');
}
