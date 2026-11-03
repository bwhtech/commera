# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

from datetime import datetime
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from commera.shipping.units import to_system_datetime


@patch("commera.shipping.units.get_system_timezone", return_value="Asia/Kolkata")
class TestToSystemDatetime(IntegrationTestCase):
	def test_offset_aware_timestamp_keeps_the_instant(self, _timezone):
		self.assertEqual(to_system_datetime("2026-09-03T10:00:00+05:30"), datetime(2026, 9, 3, 10, 0, 0))
		self.assertEqual(to_system_datetime("2026-09-03T04:30:00Z"), datetime(2026, 9, 3, 10, 0, 0))

	def test_offset_is_converted_not_truncated(self, _timezone):
		self.assertEqual(to_system_datetime("2026-09-03T10:00:00+00:00"), datetime(2026, 9, 3, 15, 30, 0))

	def test_naive_timestamp_passes_through(self, _timezone):
		self.assertEqual(to_system_datetime("2026-09-03 10:00:00"), datetime(2026, 9, 3, 10, 0, 0))

	def test_missing_timestamp_is_none(self, _timezone):
		for value in (None, "", 0):
			self.assertIsNone(to_system_datetime(value))
