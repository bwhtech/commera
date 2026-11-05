import { ref } from 'vue'
import { bootValue } from './boot'

export const isStorefrontPublished = ref(bootValue('storefront_published', false))
