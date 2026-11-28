/**
 * Ends a bottom sheet's leftover mouse or pen gesture before a plain hover can drag the sheet.
 *
 * frappe-ui's useSheetDrag (1.0.2) arms a gesture on a pointerdown inside the sheet and clears it
 * only when that press's pointerup or pointercancel reaches the sheet. A press that opens a picker
 * (the Collection select, whose list is portalled to <body>) ends on the picker, outside the sheet,
 * so the gesture stays armed. The next move over the sheet, with no button held, then passes its
 * slop check as a downward drag: the sheet slid about 200px and took its footer off the screen.
 *
 * A move with no button held cannot belong to a drag. So when one arrives while a press is still
 * open, this hands the sheet a pointercancel first. That runs frappe-ui's own finish(cancelled):
 * the phase goes back to idle and any offset springs back. It is a capture listener on the sheet,
 * so it runs before frappe-ui's bubble listener on the same element sees the move.
 *
 * Touch is left alone: frappe-ui runs it on touch events, and a touchend always reaches the sheet.
 *
 * ponytail: a workaround for frappe-ui's useSheetDrag; drop it once frappe-ui ends an armed gesture
 * on a move with no button held (the upstream diff is in council-product-ux/v10/upstream).
 *
 * Returns the function that removes the listeners.
 */
export function endStaleSheetGestures(sheet) {
  let pressOpen = false

  function onPointerDown(event) {
    if (event.pointerType !== 'touch') pressOpen = true
  }

  function onPointerUp(event) {
    if (event.pointerType !== 'touch') pressOpen = false
  }

  function onPointerMove(event) {
    if (!pressOpen || event.pointerType === 'touch' || event.buttons !== 0) return
    pressOpen = false
    sheet.dispatchEvent(
      new PointerEvent('pointercancel', { pointerId: event.pointerId, pointerType: event.pointerType }),
    )
  }

  sheet.addEventListener('pointerdown', onPointerDown, true)
  sheet.addEventListener('pointerup', onPointerUp, true)
  sheet.addEventListener('pointercancel', onPointerUp, true)
  sheet.addEventListener('pointermove', onPointerMove, true)

  return () => {
    sheet.removeEventListener('pointerdown', onPointerDown, true)
    sheet.removeEventListener('pointerup', onPointerUp, true)
    sheet.removeEventListener('pointercancel', onPointerUp, true)
    sheet.removeEventListener('pointermove', onPointerMove, true)
  }
}
