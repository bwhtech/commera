// Pure shapers over the Settings › Languages screen, apart so node unit tests can import them.

// The boot list's order: the default first, then the published languages, then the hidden ones.
export function toBootLanguages({ languages, default_language: defaultCode }) {
  const ordered = [
    ...languages.filter((language) => language.code === defaultCode),
    ...languages.filter((language) => language.code !== defaultCode && language.published),
    ...languages.filter((language) => !language.published),
  ]
  return ordered.map(({ code, name, endonym, direction }) => ({ code, name, endonym, direction }))
}

// The default language lives at the root; every other one under its own code.
export function languagePrefix(code, defaultCode) {
  return code === defaultCode ? '/' : `/${code.toLowerCase()}/`
}
