import { __ } from './translation.js'

const SOURCE_STEP = { key: 'source', label: __('Source') }

export const SOURCE_STEPS = {
  csv: [
    SOURCE_STEP,
    { key: 'upload', label: __('Upload') },
    { key: 'map', label: __('Match columns') },
    { key: 'images', label: __('Photos') },
    { key: 'review', label: __('Review') },
    { key: 'run', label: __('Import') },
  ],
  erpnext: [SOURCE_STEP, { key: 'pick', label: __('Pick items') }, { key: 'run', label: __('Import') }],
}

// The source step is a choice, so it is left out when the spreadsheet is the only source there is.
export function stepsFor(source, hasSourceChoice = true) {
  const steps = SOURCE_STEPS[source] ?? SOURCE_STEPS.csv
  return hasSourceChoice ? steps : steps.filter((step) => step.key !== 'source')
}

export const stepIndex = (source, key, hasSourceChoice = true) =>
  stepsFor(source, hasSourceChoice).findIndex((step) => step.key === key)
