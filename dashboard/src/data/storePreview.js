// One try per page load, so a theme whose homepage will not render does not retry on every Home visit.
let hasTried = false

export async function captureStorePreview(theme) {
  if (hasTried) return false
  hasTried = true
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
