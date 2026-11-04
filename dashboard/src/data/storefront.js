import { ref } from 'vue'
import { bootValue } from './boot'

// One owner for "is the store live": seeded from the boot, so Home paints the right state on its
// first frame, and kept current by Home's read and by publishing. A Home remount reads this, not
// a fresh request that starts empty.
export const isStorefrontPublished = ref(bootValue('storefront_published', false))
