<script setup>
import { computed } from 'vue'
import { longDate } from '../data/format'
import { __ } from '../data/translation'

// Fed straight from the order's own `progress` array (commera.api.admin.orders.describe_progress) —
// each entry already carries the state ('done' | 'current' | 'upcoming') and label the ladder needs;
// this component only adds the icon and the caption text, which are presentational.
const props = defineProps({ progress: { type: Array, required: true } })

const ICONS = {
  confirmation_pending: 'lucide-clock',
  to_fulfil: 'lucide-shopping-bag',
  delivery_note_drafted: 'lucide-file-text',
  packed: 'lucide-package',
  shipped: 'lucide-truck',
  delivered: 'lucide-house',
  cancelled: 'lucide-circle-x',
  returned: 'lucide-rotate-ccw',
}

// A terminal step (cancelled/returned) reads as its own state, layered on top
// of the plain done/current/upcoming three the rest of the ladder uses.
const TERMINAL_KEYS = ['cancelled', 'returned']

const steps = computed(() =>
  props.progress.map((step) => ({
    ...step,
    icon: ICONS[step.key] ?? 'lucide-circle',
    caption: step.note || (step.at ? longDate(step.at) : step.state === 'current' ? __('In progress') : __('Not yet')),
    tone: TERMINAL_KEYS.includes(step.key) && step.state === 'current' ? step.key : step.state,
  })),
)

// The same surface/ink pairings Avatar uses for a letter with no image: a tint
// behind, the matching ink on top, so a step reads as a state and not as a
// button.
const DOT = {
  done: 'bg-surface-green-2 text-ink-green-7',
  current: 'bg-surface-blue-2 text-ink-blue-7',
  upcoming: 'bg-surface-gray-2 text-ink-gray-5',
  cancelled: 'bg-surface-red-2 text-ink-red-7',
  returned: 'bg-surface-gray-2 text-ink-gray-6',
}

const LABEL = {
  done: 'text-ink-gray-8',
  current: 'text-ink-gray-9',
  upcoming: 'text-ink-gray-5',
  cancelled: 'text-ink-red-6',
  returned: 'text-ink-gray-6',
}

// A connector is filled up to the last step the order actually reached.
const REACHED = ['done', 'current', 'cancelled', 'returned']
const reached = (step) => Boolean(step) && REACHED.includes(step.tone)
</script>

<template>
  <div class="rounded-5 border border-outline-gray-1 px-5 py-4">
    <!-- Six steps across a 375px screen leave ~55px each, which truncates every
         label to nonsense. Below sm they wrap to rows of three; the connectors
         go with them, since a rail that runs off the end of a row reads as broken.
         describe_progress returns 2 to 7 steps, so the last row is often short —
         centred, that reads as deliberate rather than as a row that ran out. -->
    <ol class="mx-auto flex max-w-2xl flex-wrap items-start justify-center gap-y-4 sm:flex-nowrap sm:gap-y-0">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="flex min-w-0 basis-1/3 flex-col items-center text-center sm:flex-1 sm:basis-0"
      >
        <!-- The connectors carry the reading: filled up to where the order got.
             Below sm they are display:none, leaving the dot as the row's only child —
             so the row has to centre it to keep it over its own label. -->
        <div class="flex w-full items-center justify-center sm:justify-start">
          <span
            class="hidden h-px flex-1 sm:block"
            :class="index === 0 ? 'bg-transparent' : reached(step) ? 'bg-surface-gray-5' : 'bg-surface-gray-3'"
            aria-hidden="true"
          />
          <span class="mx-2 grid size-8 shrink-0 place-content-center rounded-full" :class="DOT[step.tone]">
            <span :class="[step.tone === 'done' ? 'lucide-check' : step.icon, 'size-4']" aria-hidden="true" />
          </span>
          <span
            class="hidden h-px flex-1 sm:block"
            :class="
              index === steps.length - 1
                ? 'bg-transparent'
                : reached(steps[index + 1])
                  ? 'bg-surface-gray-5'
                  : 'bg-surface-gray-3'
            "
            aria-hidden="true"
          />
        </div>

        <!-- A column never leaves room for "Confirmation pending" on one line, at
             any width — wrapping reads better than an ellipsis that hides the word
             carrying the meaning. -->
        <p class="mt-2 max-w-full text-balance text-base" :class="LABEL[step.tone]">{{ step.label }}</p>
        <p class="mt-0.5 max-w-full text-balance text-sm text-ink-gray-5">{{ step.caption }}</p>
      </li>
    </ol>
  </div>
</template>

