// Safari has no requestIdleCallback, so it waits a second instead.
export function whenIdle(callback) {
  if ('requestIdleCallback' in window) {
    const handle = requestIdleCallback(callback, { timeout: 3000 })
    return () => cancelIdleCallback(handle)
  }
  const handle = setTimeout(callback, 1000)
  return () => clearTimeout(handle)
}
