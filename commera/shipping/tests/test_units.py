# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

from datetime import datetime

from frappe.tests import IntegrationTestCase, change_settings

from commera.shipping.units import to_system_datetime


class TestToSystemDatetime(IntegrationTestCase):
	"""A carrier's timestamp has to land in a Datetime column, which stores neither offset nor zone."""

	@change_settings("System Settings", time_zone="Asia/Kolkata")
	def test_offset_aware_timestamp_keeps_the_instant(self):
		"""AfterShip sends offset-aware ISO-8601. The same instant in two spellings must agree."""
		self.assertEqual(to_system_datetime("2026-09-03T10:00:00+05:30"), datetime(2026, 9, 3, 10, 0, 0))
		self.assertEqual(to_system_datetime("2026-09-03T04:30:00Z"), datetime(2026, 9, 3, 10, 0, 0))

	@change_settings("System Settings", time_zone="Asia/Kolkata")
	def test_offset_is_converted_not_truncated(self):
		"""Dropping the offset would keep the digits and move the event by hours."""
		self.assertEqual(to_system_datetime("2026-09-03T10:00:00+00:00"), datetime(2026, 9, 3, 15, 30, 0))

	@change_settings("System Settings", time_zone="Asia/Kolkata")
	def test_naive_timestamp_passes_through(self):
		"""Shiprocket sends a naive local string, which is already system time."""
		self.assertEqual(to_system_datetime("2026-09-03 10:00:00"), datetime(2026, 9, 3, 10, 0, 0))

	def test_missing_timestamp_is_none(self):
		"""A scan with no time is normal: it must not raise, and must not invent one."""
		for value in (None, "", 0):
			self.assertIsNone(to_system_datetime(value))
