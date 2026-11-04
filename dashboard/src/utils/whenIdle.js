// Safari has no requestIdleCallback, so it waits a second instead.
export function whenIdle(callback) {
  if ('requestIdleCallback' in window) return requestIdleCallback(callback, { timeout: 3000 })
  return setTimeout(callback, 1000)
}
