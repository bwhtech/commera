// Every request a screen sends for "the current thing" takes a ticket, and only the newest ticket
// may write its answer. frappe-ui's `useCall` aborts the request in flight when the same call
// starts again, but two different calls (a page switch and a reload, a dialog's open and its
// reopen) do not abort each other, so whichever answer lands last would otherwise win.
// `cancel()` retires every ticket, for a dialog closing or a screen moving on.
export function createSequence() {
  let latest = 0
  return {
    next: () => ++latest,
    isLatest: (ticket) => ticket === latest,
    cancel: () => {
      latest += 1
    },
  }
}
