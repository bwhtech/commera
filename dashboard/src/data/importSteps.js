import { __ } from './translation.js'

const SOURCE_STEP = { key: 'source', label: __('Source'), icon: 'lucide-plug', hint: __('Where the products live today') }

export const SOURCE_STEPS = {
  csv: [
    SOURCE_STEP,
    { key: 'upload', label: __('Upload'), icon: 'lucide-file-up', hint: __('Your spreadsheet') },
    { key: 'map', label: __('Match columns'), icon: 'lucide-arrow-left-right', hint: __('Your headings to ours') },
    { key: 'images', label: __('Images'), icon: 'lucide-image', hint: __('Photos for each product') },
    { key: 'review', label: __('Review'), icon: 'lucide-list-checks', hint: __('Check before saving') },
    { key: 'run', label: __('Import'), icon: 'lucide-rocket', hint: __('Create everything') },
  ],
  erpnext: [
    SOURCE_STEP,
    { key: 'pick', label: __('Pick items'), icon: 'lucide-list-checks', hint: __('The ERPNext items to bring in') },
    { key: 'run', label: __('Import'), icon: 'lucide-rocket', hint: __('Create and publish') },
  ],
}

export const stepsFor = (source) => SOURCE_STEPS[source] ?? SOURCE_STEPS.csv

export const stepIndex = (source, key) => stepsFor(source).findIndex((step) => step.key === key)

export const resultExits = (canRouteAway) =>
  canRouteAway
    ? [
        { label: __('View my products'), path: '/products' },
        { label: __('Back to overview'), path: '/' },
      ]
    : [{ label: __('Back to setup') }]
