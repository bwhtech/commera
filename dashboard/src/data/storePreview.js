const triedThemes = new Set()

export async function captureStorePreview(theme) {
  if (triedThemes.has(theme)) return false
  triedThemes.add(theme)
  try {
    // Lazy: this pulls in modern-screenshot and the layout editor's data module.
    const { saveThemeThumbnail } = await import('./themeLayout')
    await saveThemeThumbnail(theme)
    return true
  } catch (error) {
    console.warn('[commera] could not capture the storefront preview', error)
    return false
  }
}

export async function captureMissingThumbnails(themes, onCaptured) {
  const missing = themes.filter((theme) => theme.theme_type === 'Sections' && (!theme.thumbnail || !theme.thumbnail_dark))
  for (const theme of missing) {
    if (await captureStorePreview(theme.name)) await onCaptured(theme)
  }
}
