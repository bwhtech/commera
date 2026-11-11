# Storefront search

## Engines

Commera Settings > Search > Search Engine selects the engine that ranks storefront searches.

| Engine | Where the index is | What it adds |
|---|---|---|
| SQLite (default) | A file on the site, `commera_product_search.db` | Nothing to set up. Terms shorter than 4 characters use a `LIKE` query instead. Arabic terms also use it until Arabic is a published language. |

### Engines on a search server

An engine on a search server uses the same settings:

1. Set Search Engine to the engine.
2. Enter the server URL and an API key that can create indexes and write documents.
3. Optional: enter an Index Prefix. Sites that share one server need different prefixes. The default is the site name.
4. Save. Commera checks the connection and the key, then builds the index in a background job.

The storefront uses the `LIKE` query in these cases:

- The index is not ready yet.
- The server does not answer. The first failed request also uses the `LIKE` query. Then Commera does not try the server again for 30 seconds.

A rebuild fills new indexes and then swaps them in, so search keeps working during the build.

To add an engine, subclass `RemoteSearchEngine` in `commera/search/remote_engine.py` and add it to `ENGINES` in `commera/search/engine_cache.py`. Its tests subclass `RemoteEngineTests` in `commera/search/remote_engine_tests.py`.

## Languages

The index holds the title of each product and the name of each category in every published storefront language. The titles come from Content Translation rows. Until #441, an Item's Arabic name fills in for a missing Arabic translation.

- A query in any published language finds the record. The translated titles are part of the record's `content`. Search-server engines also get the Arabic title in `title_ar`.
- SQLite gives each Arabic word a set of search forms (`commera/search/arabic.py`). The index and the query use the same forms.
  - The folded form removes harakat and tatweel. It changes `أ إ آ ٱ` to `ا`, `ة` to `ه` and `ى` to `ي`.
  - When the folded word starts with an article (`ال`, `وال`, `بال`, `كال`, `فال`, `لل`) and 3 letters stay after it, the word also has a form without the article.
  - The index holds the written words and all their forms. The storefront shows the written words unchanged.
  - A query word matches any of its forms, for example `("العاب"* OR "عاب")`. Thus `العاب` finds `ألعاب`, `قميص` finds `القميص`, and `فالنتين` still finds `فالنتين`.
  - Forms of 4 or more letters match as a prefix, as other words do. Thus `الورد` finds `الوردة`. A partial Arabic word that starts a known word is not spell-corrected.
- Saving or deleting a title translation reindexes its record. When an edit moves a translation to a different record or language, the old record is also reindexed.
- A change to the default or the published languages in Commera Settings rebuilds the index. A build compares the languages at its start and end. If they changed while it ran, it enqueues one more build, unless a build is already queued.
- A build saves the languages it started with in the index. When an interrupted build resumes with other languages, it starts again from the beginning.
- The `LIKE` query also looks in the shop-wide title translations of the published languages, so short terms find translated titles.

## Search as you type

One function gives the typeahead result for the REST API, the themes and Jinja.

### REST API

`GET /api/v2/method/commera.api.search.typeahead?q=<text>&limit=<n>`

- Guests can call it. The rate limit is 120 calls a minute.
- `limit` is the number of products and of categories. The default is 6 and the maximum is 20.

The response:

```json
{
  "data": {
    "query": "brkae",
    "products": [{"name": "BRAKE-PADS - Black", "route": "brake-pads-black", "item_name": "...", "effective_price": 74.99, "sizes": [], "...": "..."}],
    "categories": [{"name": "Brake System", "label": "Brake System", "url": "/en/products?category=brake_system"}],
    "corrected_query": "brake"
  }
}
```

- `products` are storefront product cards with live prices, best match first. They have the same keys as the cards on the product listing.
- `categories` are menu entries whose names match. `url` opens the listing for the entry.
- `corrected_query` is the query that the engine searched for after it corrected a typo, else `null`. Show it as "Showing results for ...". SQLite returns it. An engine that corrects typos without reporting them returns `null`.

`commera.api.utils.get_search_results(search)` still works. It returns only the `products` list.

### Jinja

Themes can call `get_typeahead(query, limit=6)` in a template. It returns the same dict as the REST API.

### Themes

The search boxes in the default theme and in the summer theme call the REST API. They show the categories, the corrected query and the product cards. Use them as examples for a new theme.
