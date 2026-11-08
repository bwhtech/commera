// Every request a screen sends for "the current thing" takes a ticket, and only the newest ticket
// may write its answer. frappe-ui's `useCall` aborts the request in flight when the same call
// starts again, but two different calls (a page switch and a reload, a dialog's open and its
// reopen) do not abort each other, so whichever answer lands last would otherwise win.
// `cancel()` retires every ticket, for a dialog closing or a screen moving on.
export function createSequence() {
  let latest = 0
  return {
    next: () => ++latest,
    // A write started on the current thing takes this, so its answer is dropped once the screen moves on.
    current: () => latest,
    isLatest: (ticket) => ticket === latest,
    cancel: () => {
      latest += 1
    },
  }
}

// Callers that arrive while `run` is in flight share its promise instead of starting another:
// two panels asking for the same store on one open must not send two reads of one shared
// request, where the second aborts the first and the first reports the abort as a failure.
export function singleFlight(run) {
  let inFlight = null
  return () => {
    inFlight ??= Promise.resolve(run()).finally(() => {
      inFlight = null
    })
    return inFlight
  }
}
