// The storefront preview inside the editor's iframe. In Commera this page is
// the real Jinja render of the draft layout (the theme_editor_preview route);
// the editor talks to it only through postMessage, so either side can change.
import './preview.css'
import { renderPage } from './sections.js'

const root = document.getElementById('storefront')
let payload = null

function applyThemeSettings(settings) {
  const style = document.documentElement.style
  style.setProperty('--accent', settings.accent)
  style.setProperty('--text', settings.text)
  style.setProperty('--background', settings.background)
  style.setProperty('--radius', `${settings.radius}px`)
  style.setProperty('--heading-font', settings.heading_font === 'Georgia' ? 'Georgia, serif' : `'${settings.heading_font}', system-ui, sans-serif`)
}

function markSelection(selectedId, scroll) {
  root.querySelectorAll('.is-selected').forEach((element) => element.classList.remove('is-selected'))
  if (!selectedId) return
  const element = root.querySelector(`[data-section-id="${selectedId}"], [data-block-id="${selectedId}"]`)
  if (!element) return
  element.classList.add('is-selected')
  if (scroll) element.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

window.addEventListener('message', (event) => {
  if (event.origin !== window.location.origin) return
  const { type, data, scroll } = event.data ?? {}
  if (type !== 'commera:render') return
  // A different page starts at its top, as it would when navigating.
  const pageChanged = payload && payload.template !== data.template
  payload = data
  document.documentElement.lang = data.language
  document.documentElement.dir = data.language === 'ar' ? 'rtl' : 'ltr'
  applyThemeSettings(data.settings)
  // Whole-page re-render keeps the prototype simple; the real preview would
  // re-render only the changed section (Section Rendering, spec 04).
  root.innerHTML = renderPage(data)
  if (pageChanged) window.scrollTo(0, 0)
  markSelection(data.selectedId, scroll)
})

// A click selects the innermost block, else its section, in the editor.
root.addEventListener('click', (event) => {
  event.preventDefault()
  const target = event.target.closest('[data-block-id], [data-section-id]')
  if (!target) return
  const id = target.dataset.blockId ?? target.dataset.sectionId
  window.parent.postMessage({ type: 'commera:select', id }, window.location.origin)
  markSelection(id, false)
})

window.parent.postMessage({ type: 'commera:preview-ready' }, window.location.origin)
