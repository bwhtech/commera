"""The Meilisearch REST API. Meilisearch applies every write as an async task."""

import time

from commera.search.http_client import WRITE_TIMEOUT, SearchHttpClient, SearchServerError

TASK_POLL_INTERVAL = 0.1


class MeiliClient(SearchHttpClient):
	def __init__(self, url, api_key):
		super().__init__(url, {"Authorization": f"Bearer {api_key}"} if api_key else {})

	def wait_for_task(self, task, timeout=WRITE_TIMEOUT):
		"""Block until an enqueued task finishes."""
		deadline = time.monotonic() + timeout
		while True:
			state = self.get(f"/tasks/{task['taskUid']}")
			if state["status"] == "succeeded":
				return state
			if state["status"] in ("failed", "canceled"):
				raise SearchServerError(
					f"Meilisearch task {task['taskUid']} {state['status']}: {state.get('error')}"
				)
			if time.monotonic() > deadline:
				raise SearchServerError(f"Meilisearch task {task['taskUid']} did not finish in {timeout}s")
			time.sleep(TASK_POLL_INTERVAL)
