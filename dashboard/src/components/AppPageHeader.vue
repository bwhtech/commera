<script setup>
import { Breadcrumbs, PageHeader, PageHeaderBackButton } from 'frappe-ui'

defineProps({
  title: { type: String, required: true },
  backTo: { type: [String, Object], default: null },
  breadcrumbs: { type: Array, default: null },
})
</script>

<template>
  <PageHeader>
    <!-- PageHeader's own row is `flex items-center justify-between` with nothing
         allowed to shrink, so without min-w-0 the title reports its full width and
         the page overflows sideways instead of the title ellipsising. -->
    <div class="flex min-w-0 items-center gap-1">
      <!-- Desktop keeps its sidebar and its breadcrumbs; the phone has neither
           once the rail is gone, so `backTo` only becomes a control down there.
           It goes back through history and falls back to `backTo` on a cold load. -->
      <!-- `-ml-2` is optical alignment, not a nudge: the button is icon-only at
           its `size="md"` default, so it draws a 32px box around an 18px glyph
           and carries a 7px inset of its own. Pulling 8px back off PageHeader's
           12px `px-3` gutter puts the glyph at 11px, level with the content
           below, instead of the box's padding pushing it in to 19px. Recheck it
           if that button ever stops defaulting to `md`. -->
      <PageHeaderBackButton v-if="backTo" class="-ml-2 shrink-0 sm:hidden" :fallback-route="backTo" />
      <Breadcrumbs v-if="breadcrumbs" class="min-w-0" :items="breadcrumbs" />
      <h1 v-else class="min-w-0 truncate text-lg-semibold text-ink-gray-8">{{ title }}</h1>
    </div>
    <div class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </PageHeader>
</template>

