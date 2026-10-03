<script setup>
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { BottomSheet, MobileNav, MobileNavItem, MobileShell } from 'frappe-ui'
import { activeNavTarget, sections } from '../ia/nav'
import AppIcon from './AppIcon.vue'

// The four destinations that earn a permanent tab. Everything else is reached
// through "More", so the bar stays thumb-sized on a 375px screen.
const TAB_TARGETS = ['/', '/orders', '/products', '/customers']

// Read the tabs off the shared nav definition rather than restating them, so a
// label or icon change in the sidebar lands here too.
const navItems = sections.flatMap((section) => section.items)
const tabs = TAB_TARGETS.map((to) => navItems.find((item) => item.to === to)).filter(Boolean)

// The sheet is one flat list per section: a parent row (Analytics) is a
// disclosure rather than a destination, so its reports stand in for it.
const moreSections = sections
  .map((section) => ({
    id: section.id,
    label: section.label,
    items: section.items
      .flatMap((item) => item.children ?? [item])
      .filter((item) => !TAB_TARGETS.includes(item.to)),
  }))
  .filter((section) => section.items.length)

const rowClass =
  'flex min-h-12 w-full items-center gap-3 rounded px-3 text-base text-ink-gray-8 active:bg-surface-gray-2'

const route = useRoute()
const activeTarget = computed(() => activeNavTarget(route.path))

// "More" stays lit for anything that has no tab of its own.
const moreIsActive = computed(() => Boolean(activeTarget.value) && !TAB_TARGETS.includes(activeTarget.value))

const moreOpen = ref(false)

// Both a link tap and an action row close the sheet: whatever it opens is about
// to replace what sits under it.
function closeMore(item) {
  moreOpen.value = false
  item?.onClick?.()
}
</script>

<template>
  <MobileShell>
    <slot />

    <template #nav>
      <MobileNav>
        <MobileNavItem
          v-for="tab in tabs"
          :key="tab.to"
          :label="tab.label"
          :icon="tab.icon"
          :to="tab.to"
          :active="tab.to === activeTarget"
        />
        <MobileNavItem label="More" icon="lucide-ellipsis" :active="moreIsActive" @click="moreOpen = true" />
      </MobileNav>
    </template>
  </MobileShell>

  <BottomSheet v-model:open="moreOpen" title="More">
    <div class="px-2 pb-8">
      <div v-for="section in moreSections" :key="section.id" class="pt-2 first:pt-0">
        <p v-if="section.label" class="px-3 pb-1 pt-2 text-xs-medium text-ink-gray-5">{{ section.label }}</p>

        <template v-for="item in section.items" :key="item.to ?? item.label">
          <RouterLink
            v-if="item.to"
            :to="item.to"
            :class="[rowClass, item.to === activeTarget ? 'bg-surface-gray-2' : '']"
            @click="closeMore()"
          >
            <AppIcon v-if="item.iconUrl" :src="item.iconUrl" class="size-5 text-ink-gray-7" />
            <span v-else :class="item.icon" class="size-5 text-ink-gray-7" aria-hidden="true" />
            {{ item.label }}
          </RouterLink>

          <!-- An item without `to` is an action row (Search): it opens an
               overlay rather than routing, so it never takes active state. -->
          <button v-else type="button" :class="rowClass" @click="closeMore(item)">
            <span :class="item.icon" class="size-5 text-ink-gray-7" aria-hidden="true" />
            {{ item.label }}
          </button>
        </template>
      </div>
    </div>
  </BottomSheet>
</template>
