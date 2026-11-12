"""The search index priced cards with supplier rows and with rows past their valid_upto. Reindex once
with the public prices of today; the nightly rebuild keeps the dates current afterwards."""


def execute():
	from commera.search.build import enqueue_full_rebuild

	enqueue_full_rebuild(deduplicate=True)
