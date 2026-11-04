const FACE_DESCRIPTORS = ['font-family', 'font-weight', 'font-style', 'font-stretch', 'unicode-range']
const FIRST_URL =/url\(\s*(['"]?)([^'")]+)\1\s*\)(\s*format\(\s*['"]?[^'")]+['"]?\s*\))?/

const unquote = (value) => value.trim().replace(/^["']|["']$/g, '')
const normalWeight = (weight) => ({ normal: '400', bold: '700' })[weight] ?? weight
const faceKey = (family, weight, style, unicodeRange) =>
  [unquote(family), normalWeight(weight || 'normal'), style || 'normal', (unicodeRange || 'U+0-10FFFF').toUpperCase()].join('|')

async function readRules(sheet) {
  try {
    return { rules: [...sheet.cssRules], base: sheet.href }
  } catch {
    const fetched = new CSSStyleSheet()
    fetched.replaceSync(await (await fetch(sheet.href)).text())
    return { rules: [...fetched.cssRules], base: sheet.href }
  }
}

async function collectFontFaceRules(sheet, baseUrl, found) {
  const { rules, base } = await readRules(sheet).catch(() => ({ rules: [], base: null }))
  for (const rule of rules) {
    if (rule.styleSheet) await collectFontFaceRules(rule.styleSheet, rule.styleSheet.href ?? base ?? baseUrl, found)
    else if (rule.constructor.name === 'CSSFontFaceRule') found.push({ rule, base: base ?? baseUrl })
  }
}

async function toDataUrl(url) {
  const blob = await (await fetch(url)).blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

export async function embeddedFontCss(frameDocument) {
  const loaded = new Set(
    [...frameDocument.fonts]
      .filter((face) => face.status === 'loaded')
      .map((face) => faceKey(face.family, face.weight, face.style, face.unicodeRange)),
  )
  const found = []
  for (const sheet of frameDocument.styleSheets) await collectFontFaceRules(sheet, frameDocument.baseURI, found)

  const faces = await Promise.all(
    found.map(async ({ rule, base }) => {
      const style = rule.style
      const key = faceKey(
        style.getPropertyValue('font-family'),
        style.getPropertyValue('font-weight'),
        style.getPropertyValue('font-style'),
        style.getPropertyValue('unicode-range'),
      )
      const source = style.getPropertyValue('src').match(FIRST_URL)
      if (!loaded.has(key) || !source) return ''
      try {
        const dataUrl = await toDataUrl(new URL(source[2], base).href)
        const descriptors = FACE_DESCRIPTORS.map((name) => [name, style.getPropertyValue(name)]).filter(([, value]) => value)
        return `@font-face { ${descriptors.map(([name, value]) => `${name}: ${value};`).join(' ')} src: url("${dataUrl}")${source[3] ?? ''}; }`
      } catch {
        return ''
      }
    }),
  )
  return faces.filter(Boolean).join('\n')
}
