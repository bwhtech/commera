// One try per page load: a capture that fails (a theme whose homepage will not render) must not
// retry on every visit to Home, and two Home mounts must not capture twice.
let hasTried = false

/**
 * Renders the live theme's homepage once, small, and saves it as the theme's thumbnail — the same
 * capture the theme editor runs on publish. Resolves true when a new image was saved.
 */
export async function captureStorePreview(theme) {
  if (hasTried) return false
  hasTried = true
  try {
    // Lazy: the capture pulls in modern-screenshot and the layout editor's data module, which a
    // Home visit with a fresh thumbnail never needs.
    const { saveThemeThumbnail } = await import('./themeLayout')
    await saveThemeThumbnail(theme)
    return true
  } catch (error) {
    // The preview is decoration: a failed capture leaves the placeholder, it does not toast.
    console.warn('[commera] could not capture the storefront preview', error)
    return false
  }
}
