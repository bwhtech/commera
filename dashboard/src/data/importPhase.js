// What the import flow is doing right now, as one value rather than a flag per request: a step
// may only be left, and a new request only started, when nothing is in flight, and nothing may
// be redone once the write has landed.
//   idle      waiting on the merchant
//   parsing   uploading the spreadsheet and reading it back (Upload)
//   checking  re-validating the column mapping (Match columns)
//   matching  matching uploaded photos to products (Images)
//   uploading uploading photos (Images)
//   running   run_import is writing (Import)
//   done      the import landed; terminal until the dialog is reset
//   failed    run_import refused; the merchant may go back and retry
export const BUSY_PHASES = ['parsing', 'checking', 'matching', 'uploading', 'running']

export const isBusy = (phase) => BUSY_PHASES.includes(phase)

// `done` is terminal: going back to Review after a landed import would offer a second write of
// the same file, which run_import has no way to tell from a fresh one.
export const canMove = (phase) => !isBusy(phase) && phase !== 'done'

// Moving to `phase` is refused while something else is in flight or once the import landed.
export function nextPhase(current, phase) {
  return canMove(current) ? phase : null
}
