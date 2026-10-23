# Copyright (c) 2026, hussain@buildwithhussain.com and Contributors
# See license.txt

import os
import time
import unittest

from frappe.tests import IntegrationTestCase

from commera.search.meili_search import MeilisearchEngine
from commera.search.remote_engine_tests import RemoteEngineTests

# Set both to run these tests against a live server, for example a local Docker container.
MEILI_URL = os.environ.get("COMMERA_TEST_MEILI_URL")
MEILI_KEY = os.environ.get("COMMERA_TEST_MEILI_KEY")


@unittest.skipUnless(MEILI_URL and MEILI_KEY, "COMMERA_TEST_MEILI_URL and COMMERA_TEST_MEILI_KEY are not set")
class TestMeilisearchEngine(RemoteEngineTests, IntegrationTestCase):
	ENGINE = MeilisearchEngine
	URL = MEILI_URL
	KEY = MEILI_KEY

	def wait_for_writes(self):
		"""Writes are async tasks; wait until the products index has applied them."""
		client = self.engine.client
		deadline = time.monotonic() + 10
		while client.get("/tasks", indexUids=self.engine.products_uid, statuses="enqueued,processing")[
			"total"
		]:
			self.assertLess(time.monotonic(), deadline, "Meilisearch writes did not finish")
			time.sleep(0.1)

	def leftover_indexes(self):
		temporary = [f"{uid}_rebuild" for uid in (self.engine.products_uid, self.engine.categories_uid)]
		return [uid for uid in temporary if self.engine.client.get(f"/indexes/{uid}")]
