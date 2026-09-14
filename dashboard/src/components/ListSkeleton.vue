<script setup>
import { Skeleton } from 'frappe-ui'
import { ListCell, ListRow } from 'frappe-ui/list'

defineProps({
  // Cells per row — match the parent List's column count so the placeholder
  // bars line up under the real headers.
  columns: { type: Number, required: true },
  rows: { type: Number, default: 5 },
})

// A row of identical bars reads as a progress bar, not as content. Cycling the
// widths gives the block the ragged edge real data has.
const widths = ['w-24', 'w-40', 'w-16', 'w-28', 'w-20', 'w-32']
</script>

<template>
  <!-- These rows carry no `value`, so a list in selection mode draws them without
       a checkbox. Harmless — the checkbox is start-padding rather than its own grid
       track, so the columns still line up — but it is why a refetch mid-selection
       looks a row narrower.
       The parent List and its headers stay mounted above this, and above an empty
       state too: showing the columns while there is nothing to put in them is the
       approved look here, not an oversight. -->
  <ListRow v-for="row in rows" :key="row" aria-hidden="true">
    <ListCell v-for="column in columns" :key="column">
      <Skeleton class="h-3.5 rounded" :class="widths[(row + column) % widths.length]" />
    </ListCell>
  </ListRow>
</template>
