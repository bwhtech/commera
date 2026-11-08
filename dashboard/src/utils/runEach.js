// A bulk action with no bulk endpoint: one write per item, one at a time, so the server sees them
// in order and a shared request is never aborted by its own next call. A refusal does not stop the
// run, because the items before it have already landed and stopping would leave the merchant not
// knowing which half did; the caller reloads and reports `failed` instead.
// `write` resolves to anything but `false` for a success, and rejects or resolves `false` for a refusal.
export async function runEach(items, write) {
  const done = []
  const failed = []
  for (const item of items) {
    try {
      if ((await write(item)) === false) failed.push({ item, error: null })
      else done.push(item)
    } catch (error) {
      failed.push({ item, error })
    }
  }
  return { done, failed }
}

// "3 orders marked fulfilled" or "2 of 3 orders marked fulfilled. 1 failed: <reason>".
export function bulkSummary({ done, failed }, noun, verb, reasonFor = (error) => error?.message) {
  const total = done.length + failed.length
  const plural = (count) => `${count} ${noun}${count === 1 ? '' : 's'}`
  if (!failed.length) return `${plural(total)} ${verb}`
  const reason = failed.map(({ error }) => error && reasonFor(error)).find(Boolean)
  const head = `${done.length} of ${plural(total)} ${verb}. ${failed.length} failed`
  return reason ? `${head}: ${reason}` : head
}
