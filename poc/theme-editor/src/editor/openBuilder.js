import { toast } from 'frappe-ui'

// Builder is another app on the same site, so it opens in a new tab and the
// editor stays where the merchant left it. Coming back refreshes the preview
// (PreviewFrame re-posts on focus), which is when Builder edits show up here.
export function openBuilder(url, what) {
  window.open(url, '_blank', 'noopener')
  toast.info(`Opening ${what} in Frappe Builder`)
}
