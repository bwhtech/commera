/** Runs `callback` once the page is idle; Safari has no requestIdleCallback, so it waits a second. */
export function whenIdle(callback) {
  if ('requestIdleCallback' in window) return requestIdleCallback(callback, { timeout: 3000 })
  return setTimeout(callback, 1000)
}
