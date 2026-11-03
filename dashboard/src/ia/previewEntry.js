const STORAGE_KEY = 'commera:theme-editor:preview-entry'

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

const keyFor = (theme, page) => `${theme}\n${page}`

export function rememberedPreviewEntry(theme, page) {
  return readAll()[keyFor(theme, page)] ?? null
}

export function rememberPreviewEntry(theme, page, entry) {
  const entries = readAll()
  entries[keyFor(theme, page)] = entry
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {}
}
