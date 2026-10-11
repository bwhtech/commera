<script setup>
import { computed, onUnmounted, provide, shallowRef, toValue, watchEffect } from 'vue'
import { Button, Dropdown } from 'frappe-ui'
import { PAGE_CONTEXT } from '../plugin-api/context'
import { appLocation, lucideIcon } from '../ia/plugins'
import AppPageHeader from './AppPageHeader.vue'
import PluginHost from './PluginHost.vue'
import PageBody from './PageBody.vue'
import ResponsiveButton from './ResponsiveButton.vue'

const props = defineProps({
  entry: { type: Object, required: true },
  path: { type: String, default: '' },
  query: { type: Object, default: () => ({}) },
})

const VARIANTS = ['solid', 'subtle', 'ghost']

// Each setter keeps what it was given, unread, so a ref or a getter passed in stays live.
const titleSource = shallowRef(null)
const breadcrumbsSource = shallowRef(null)
const actionsSource = shallowRef(null)

function clear() {
  breadcrumbsSource.value = null
  actionsSource.value = null
}

provide(PAGE_CONTEXT, {
  setTitle: (title) => (titleSource.value = title),
  setBreadcrumbs: (breadcrumbs) => (breadcrumbsSource.value = breadcrumbs),
  setActions: (actions) => (actionsSource.value = actions),
})

const title = computed(() => toValue(titleSource.value) || props.entry.label)

const breadcrumbs = computed(() => {
  const crumbs = toValue(breadcrumbsSource.value)
  if (!crumbs?.length) return null
  return crumbs.map((crumb) => ({
    label: toValue(crumb.label),
    route: crumb.to == null ? undefined : appLocation(props.entry.app, toValue(crumb.to)),
  }))
})

// On a phone the breadcrumbs collapse into one back button, which goes to the nearest crumb above this one.
const backTo = computed(() => breadcrumbs.value?.slice(0, -1).findLast((crumb) => crumb.route)?.route ?? null)

const actions = computed(() =>
  (toValue(actionsSource.value) ?? []).map((action) => ({
    label: toValue(action.label),
    icon: action.icon ? lucideIcon(toValue(action.icon)) : null,
    variant: VARIANTS.includes(toValue(action.variant)) ? toValue(action.variant) : 'subtle',
    theme: 'gray',
    loading: Boolean(toValue(action.loading)),
    disabled: Boolean(toValue(action.disabled)),
    onClick: () => action.onClick?.(),
  })),
)

// The first action is the page's main one: it stays a button at the right edge, like an order's Fulfil items,
// and past two the rest fold into the More menu so a phone header never wraps.
const headerButtons = computed(() => (actions.value.length > 2 ? actions.value.slice(0, 1) : [...actions.value].reverse()))
const overflowOptions = computed(() =>
  actions.value.length > 2
    ? actions.value.slice(1).map((action) => ({
        label: action.label,
        icon: action.icon ?? undefined,
        disabled: action.disabled || action.loading,
        onClick: action.onClick,
      }))
    : [],
)

const titleBeforeMount = document.title
watchEffect(() => (document.title = title.value))
onUnmounted(() => (document.title = titleBeforeMount))
</script>

<template>
  <AppPageHeader :title="title" :breadcrumbs="breadcrumbs" :back-to="backTo">
    <template #actions>
      <Dropdown v-if="overflowOptions.length" :options="overflowOptions">
        <Button icon="lucide-ellipsis" label="More actions" />
      </Dropdown>
      <component
        :is="action.icon ? ResponsiveButton : Button"
        v-for="action in headerButtons"
        :key="action.label"
        v-bind="action"
      />
    </template>
  </AppPageHeader>

  <PageBody>
    <PluginHost :entry="entry" :path="path" :query="query" :compact="false" @failed="clear" />
  </PageBody>
</template>
