const DEVICES = [
  { label: 'Desktop', value: 'desktop', icon: 'lucide-monitor' },
  { label: 'Mobile', value: 'mobile', icon: 'lucide-smartphone' },
  { label: 'Desktop and mobile', value: 'both', icon: 'lucide-columns-2' },
]

const DIRECTIONS = [
  { label: 'Left to right', value: 'en', icon: 'lucide-pilcrow-right' },
  { label: 'Right to left', value: 'ar', icon: 'lucide-pilcrow-left' },
]

function radioGroup(group, choices, current, pick) {
  return {
    group,
    options: choices.map((choice) => ({
      label: choice.label,
      icon: choice.icon,
      selected: choice.value === current,
      onClick: () => pick(choice.value),
    })),
  }
}

export function previewMenu(state, { devices = true } = {}) {
  const groups = [radioGroup('Text direction', DIRECTIONS, state.language, (value) => (state.language = value))]
  if (devices) groups.unshift(radioGroup('Device', DEVICES, state.device, (value) => (state.device = value)))
  return groups
}
