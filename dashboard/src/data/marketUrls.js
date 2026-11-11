// The URL rules mirror commera/localization/markets.py: the primary market has the store's language
// prefixes, any other market `/<language>-<country>/` for each of its languages and countries.

export function marketUrls(market, { defaultLanguage, countryCode }) {
  if (market.is_primary) {
    return market.languages.map((language) => ({
      url: language === defaultLanguage ? '/' : `/${language.toLowerCase()}/`,
      language,
      country: '',
      hreflang: language,
    }))
  }
  const countries = market.countries
    .map((country) => ({ country, code: countryCode(country) }))
    .filter(({ code }) => code)
  return market.languages.flatMap((language) =>
    countries.map(({ country, code }) => ({
      url: `/${language.toLowerCase()}-${code.toLowerCase()}/`,
      language,
      country,
      hreflang: marketHreflang(language, code),
    })),
  )
}

// `<language>-<COUNTRY>`, with a script in title case: `zh-Hans-AE`.
export function marketHreflang(language, code) {
  const [base, script] = language.split('-')
  const titled = script ? script[0].toUpperCase() + script.slice(1).toLowerCase() : ''
  return [base.toLowerCase(), titled, code.toUpperCase()].filter(Boolean).join('-')
}

// The first two URLs and a count of the rest, for a list row.
export function urlSummary(urls, shown = 2) {
  const paths = urls.map(({ url }) => url)
  const head = paths.slice(0, shown).join(' ')
  return paths.length > shown ? `${head} +${paths.length - shown}` : head
}

// Country name → the name of the other market that has it.
export function countryOwners(markets, handle) {
  const owners = new Map()
  for (const market of markets) {
    if (market.handle === handle) continue
    for (const country of market.countries) owners.set(country, market.market_name)
  }
  return owners
}

// The field a refused save belongs to, read off the error's title. The server sends the titles in
// the admin's own language, so they match what it throws.
export function errorField(error, errorFields) {
  return (error?.title && errorFields?.[error.title]) || null
}
