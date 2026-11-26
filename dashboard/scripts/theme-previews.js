// Regenerates the Home preview each shipped theme falls back to before its owner captures one.
// Usage, from dashboard/: COMMERA_BASE=http://site:8000 node scripts/theme-previews.js ["Theme Name" ...]
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { BASE, adminGet, closeSession, openSession } from '../tests/e2e/harness.js'

const THEMES_DIR = fileURLToPath(new URL('../../commera/public/themes/', import.meta.url))
const SOURCES_DIR = fileURLToPath(new URL('../../commera/themes/', import.meta.url))
const VIEWPORT = { width: 1280, height: 720, deviceScaleFactor: 0.75 }
const FILES = { light: 'preview.webp', dark: 'preview-dark.webp' }

const slug = (theme) => theme.toLowerCase().replaceAll(' ', '_')

async function shoot(page, theme, scheme) {
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
  const params = new URLSearchParams({ theme, page: 'index' })
  await page.goto(`${BASE}/theme_editor_preview?${params}`, { waitUntil: 'networkidle0', timeout: 120000 })
  const followsSystem = await page.evaluate(async () => {
    for (const element of document.querySelectorAll('.wow')) {
      element.classList.remove('wow')
      element.style.visibility = 'visible'
      element.style.animation = 'none'
    }
    const settled = Promise.all([
      document.fonts.ready,
      ...[...document.images].map((image) => image.decode().catch(() => null)),
    ])
    await Promise.race([settled, new Promise((resolve) => setTimeout(resolve, 10000))])
    return document.documentElement.dataset.colorScheme === 'System'
  })
  const folder = THEMES_DIR + slug(theme)
  const file = `${folder}/${FILES[scheme]}`
  if (scheme === 'dark' && !followsSystem) {
    fs.rmSync(file, { force: true })
    return null
  }
  fs.mkdirSync(folder, { recursive: true })
  await page.screenshot({ path: file, type: 'webp', quality: 82 })
  return file
}

const session = await openSession()
try {
  const { page } = session
  await page.setViewport(VIEWPORT)
  const { themes } = await adminGet(page, 'theme.get_editor_data')
  const requested = process.argv.slice(2)
  const shipped = themes.filter(
    (theme) => theme.is_standard && !theme.is_base && fs.existsSync(SOURCES_DIR + slug(theme.name)),
  )
  for (const theme of requested.length ? shipped.filter((theme) => requested.includes(theme.name)) : shipped) {
    for (const scheme of Object.keys(FILES)) {
      const file = await shoot(page, theme.name, scheme)
      if (file) console.log(`${theme.name} ${scheme}: ${(fs.statSync(file).size / 1024).toFixed(1)} KB`)
    }
  }
} finally {
  await closeSession(session)
}
