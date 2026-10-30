from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone
from frappe.utils.data import cint, flt

# Canonical units at the provider boundary are kg and cm (see ShippingProviderBase). ERPNext stores
# parcel templates in whatever the site chose, so everything is converted once, here, on the way in.
WEIGHT_IN_KG = {
	"kg": 1.0,
	"kgs": 1.0,
	"kilogram": 1.0,
	"g": 0.001,
	"gram": 0.001,
	"lb": 0.45359237,
	"lbs": 0.45359237,
	"pound": 0.45359237,
	"oz": 0.028349523125,
	"ounce": 0.028349523125,
}

LENGTH_IN_CM = {
	"cm": 1.0,
	"centimeter": 1.0,
	"mm": 0.1,
	"millimeter": 0.1,
	"m": 100.0,
	"meter": 100.0,
	"in": 2.54,
	"inch": 2.54,
	"ft": 30.48,
	"foot": 30.48,
}

# Volumetric divisor for cm/kg. 5000 is the domestic figure Shiprocket's couriers use; a provider
# with a different contract passes its own.
DEFAULT_VOLUMETRIC_DIVISOR = 5000

WEIGHT_PRECISION = 3
LENGTH_PRECISION = 2


def to_kg(value: float, unit: str = "kg") -> float:
	return flt(flt(value) * get_factor(WEIGHT_IN_KG, unit, _("weight")), WEIGHT_PRECISION)


def to_cm(value: float, unit: str = "cm") -> float:
	return flt(flt(value) * get_factor(LENGTH_IN_CM, unit, _("length")), LENGTH_PRECISION)


def get_factor(table: dict, unit: str, kind: str) -> float:
	"""Refuse an unknown unit. A default factor of 1 would ship grams as kilograms."""
	key = (unit or "").strip().casefold().rstrip(".")
	if key in table:
		return table[key]
	frappe.throw(_("{0} is not a {1} unit this app can convert").format(frappe.bold(unit), kind))


def normalise_parcel(parcel: dict) -> dict:
	"""Return one parcel in canonical units, with its count preserved."""
	weight_unit = parcel.get("weight_unit") or "kg"
	length_unit = parcel.get("length_unit") or "cm"
	return {
		"length": to_cm(parcel.get("length"), length_unit),
		"width": to_cm(parcel.get("width"), length_unit),
		"height": to_cm(parcel.get("height"), length_unit),
		"weight": to_kg(parcel.get("weight"), weight_unit),
		"count": cint(parcel.get("count")) or 1,
		"items": parcel.get("items") or [],
	}


def normalise_parcels(parcels: list[dict]) -> list[dict]:
	if not parcels:
		frappe.throw(_("At least one parcel is needed to quote or book a shipment"))
	return [normalise_parcel(parcel) for parcel in parcels]


def volumetric_weight(parcel: dict, divisor: int = DEFAULT_VOLUMETRIC_DIVISOR) -> float:
	if not divisor:
		return 0.0
	volume = flt(parcel.get("length")) * flt(parcel.get("width")) * flt(parcel.get("height"))
	return flt(volume / divisor, WEIGHT_PRECISION)


def billable_weight(parcels: list[dict], divisor: int = DEFAULT_VOLUMETRIC_DIVISOR) -> float:
	"""Total chargeable weight: per parcel, the greater of actual and volumetric. Compared per parcel
	because carriers rate each box."""
	total = 0.0
	for parcel in parcels:
		chargeable = max(flt(parcel.get("weight")), volumetric_weight(parcel, divisor))
		total += chargeable * (cint(parcel.get("count")) or 1)
	return flt(total, WEIGHT_PRECISION)


def total_weight(parcels: list[dict]) -> float:
	"""Actual scale weight of the consignment, ignoring volumetric rating."""
	total = sum(flt(parcel.get("weight")) * (cint(parcel.get("count")) or 1) for parcel in parcels)
	return flt(total, WEIGHT_PRECISION)


def enclosing_dimensions(parcels: list[dict]) -> dict:
	"""One length/width/height for providers that book a consignment. Length is summed and the rest
	take the maximum, which overstates on purpose to avoid a carrier reweigh charge."""
	if not parcels:
		frappe.throw(_("At least one parcel is needed to quote or book a shipment"))
	return {
		"length": flt(
			sum(flt(parcel.get("length")) * (cint(parcel.get("count")) or 1) for parcel in parcels),
			LENGTH_PRECISION,
		),
		"width": flt(max(flt(parcel.get("width")) for parcel in parcels), LENGTH_PRECISION),
		"height": flt(max(flt(parcel.get("height")) for parcel in parcels), LENGTH_PRECISION),
	}


def to_system_datetime(value):
	"""A provider's timestamp as a naive datetime in system time. MySQL Datetime columns reject an
	offset, so aware values are converted first; naive values pass through."""
	if not value:
		return None

	parsed = get_datetime(value)
	if parsed is None or parsed.tzinfo is None:
		return parsed
	return parsed.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)
