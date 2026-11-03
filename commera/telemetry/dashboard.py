"""The events the dashboard sends, and the only values each may carry (docs/telemetry.md).

The browser never posts to Pulse itself: it posts here, and anything not listed below is dropped.
"""

import re

import frappe
from frappe.utils.data import cint

from commera.telemetry import capture, telemetry_event

# The keys of STEPS in dashboard/src/ia/onboardingSteps.js.
ONBOARDING_STEPS = ("you", "store", "brand", "theme", "selling", "products", "done")
# The keys of SETUP_STEPS in dashboard/src/data/firstRun.js.
SETUP_PANEL_STEPS = ("product", "payments", "shipping", "theme")
# A vue-router path pattern such as `/products/:id`: the pattern, never a URL a record fills in.
ROUTE_PATTERN = re.compile(r"^/[A-Za-z0-9/:_-]{0,100}$")


def one_of(*values):
	return lambda value: value if value in values else None


def count(value):
	return cint(value) if value is not None else None


def flag(value):
	return bool(value)


def route(value):
	return value if isinstance(value, str) and ROUTE_PATTERN.match(value) else None


onboarding_step = one_of(*ONBOARDING_STEPS)
STEP_SETTLED = {
	"step": onboarding_step,
	"step_number": count,
	"total_steps": count,
	"duration_seconds": count,
}

EVENTS = {
	"pageview": {"route": route},
	# The onboarding funnel, named as Frappe's setup wizard names its own (and Raven's).
	"started_setup": {"step": onboarding_step, "resumed": flag, "total_steps": count},
	"completed_setup_step": STEP_SETTLED,
	"skipped_setup_step": STEP_SETTLED,
	"went_back_in_setup": {"from_step": onboarding_step, "to_step": onboarding_step},
	"left_setup": {"step": onboarding_step, "duration_seconds": count},
	"onboarding_accounting_opened": {},
	"products_import_opened": {"surface": one_of("onboarding", "products", "search")},
	"setup_step_opened": {
		"step": one_of(*SETUP_PANEL_STEPS),
		"surface": one_of("panel"),
		"steps_done": count,
	},
	"setup_dismissed": {"steps_done": count},
	"setup_skipped": {"steps_done": count},
	"billing_opened": {"surface": one_of("settings", "trial_card"), "trial": flag},
}


def get_known_properties(event: str, properties: dict) -> dict:
	"""Only the properties `event` lists, each through its check; a value that fails it is dropped."""
	known = {}
	for key, check in EVENTS[event].items():
		value = check(properties[key]) if key in properties else None
		if value is not None:
			known[key] = value
	return known


@telemetry_event
def record(event: str, properties: dict | str | None):
	capture(event, **get_known_properties(event, frappe.parse_json(properties) or {}))
