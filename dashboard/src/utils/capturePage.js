import { domToCanvas } from 'modern-screenshot'
import { embeddedFontCss } from './embeddedFontCss'

const IMAGE_WAIT_MS = 5000
const XML_ATTRIBUTE_NAME = /^[A-Za-z_][\w.-]*$/

function dropNonXmlAttributes(cloned) {
  if (cloned.nodeType !== Node.ELEMENT_NODE) return
  for (const attribute of [...cloned.attributes]) {
    if (!attribute.namespaceURI && !XML_ATTRIBUTE_NAME.test(attribute.name)) cloned.removeAttribute(attribute.name)
  }
}

const startsAbove = (height) => (node) => node.nodeType !== Node.ELEMENT_NODE || node.getBoundingClientRect().top < height

function loadFrame(frame, url) {
  return new Promise((resolve, reject) => {
    frame.addEventListener('load', resolve, { once: true })
    frame.addEventListener('error', reject, { once: true })
    frame.src = url
  })
}

function settleImages(frameDocument) {
  const images = [...frameDocument.images]
  for (const image of images) image.loading = 'eager'
  const pending = images
    .filter((image) => !image.complete)
    .map((image) => new Promise((resolve) => {
      image.addEventListener('load', resolve, { once: true })
      image.addEventListener('error', resolve, { once: true })
    }))
  const timeout = new Promise((resolve) => setTimeout(resolve, IMAGE_WAIT_MS))
  return Promise.race([Promise.all(pending), timeout])
}

function settleAnimations(frameDocument) {
  const finite = frameDocument.getAnimations().filter((animation) => animation.effect?.getComputedTiming().endTime !== Infinity)
  const timeout = new Promise((resolve) => setTimeout(resolve, IMAGE_WAIT_MS))
  return Promise.race([Promise.all(finite.map((animation) => animation.finished.catch(() => null))), timeout])
}

function resizeToWebp(source, width, height, quality) {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  context.imageSmoothingQuality = 'high'
  context.drawImage(source, 0, 0, width, height)
  return canvas.toDataURL('image/webp', quality)
}

export async function capturePage(url, { width, height, scale = 1, outputWidth = width, quality = 0.85, beforeCapture } = {}) {
  const frame = document.createElement('iframe')
  frame.width = String(width)
  frame.height = String(height)
  frame.tabIndex = -1
  frame.setAttribute('aria-hidden', 'true')
  frame.className = 'pointer-events-none fixed left-0 top-0 -z-10 opacity-0'
  document.body.appendChild(frame)
  try {
    await loadFrame(frame, url)
    const frameDocument = frame.contentDocument
    beforeCapture?.(frameDocument)
    await Promise.all([frameDocument.fonts.ready, settleImages(frameDocument), settleAnimations(frameDocument)])
    const canvas = await domToCanvas(frameDocument.documentElement, {
      width,
      height,
      scale,
      filter: startsAbove(height),
      onCloneEachNode: dropNonXmlAttributes,
      timeout: IMAGE_WAIT_MS,
      font: { cssText: await embeddedFontCss(frameDocument) },
      backgroundColor: frame.contentWindow.getComputedStyle(frameDocument.body).backgroundColor,
    })
    return resizeToWebp(canvas, outputWidth, Math.round((outputWidth * height) / width), quality)
  } finally {
    frame.remove()
  }
}
