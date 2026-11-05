// One try per theme per page load, so a theme whose homepage will not render does not retry on every visit.
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

// Serial on purpose: each capture renders a full storefront homepage in a hidden iframe.
// Classic themes are skipped because save_thumbnail refuses them.
export async function captureMissingThumbnails(themes, onCaptured) {
  const missing = themes.filter((theme) => theme.theme_type === 'Sections' && !theme.thumbnail)
  for (const theme of missing) {
    if (await captureStorePreview(theme.name)) await onCaptured(theme)
  }
}
