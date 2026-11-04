<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Dialog, Skeleton, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import StorefrontPreview from '../components/home/StorefrontPreview.vue'
import StoreOverview from '../components/home/StoreOverview.vue'
import TaskHeading from '../components/home/TaskHeading.vue'
import TaskList from '../components/home/TaskList.vue'
import { trySubmit, useAdminAction, useAdminRead } from '../data/api'
import { customDomain, loadDomains } from '../data/cloudDomains'
import { buildHomeTasks, describeStoreStatus, listBlockers, needsPreviewCapture, storeSlug } from '../data/home'
import { captureStorePreview } from '../data/storePreview'
import { dismissTask, dismissedTasks, homeArrival, restoreTasks } from '../ia/homeTasks'
import { lookFor } from '../ia/onboarding'
import { whenIdle } from '../utils/whenIdle'

const homeRequest = useAdminRead('home.get_home')
const publishAction = useAdminAction('home.set_storefront_published')

const home = computed(() => homeRequest.data)

// A missing or day-old preview is captured once, after the page has settled: the capture renders the
// homepage in a hidden frame, which is work Home's first paint should not wait on.

watch(home, (record) => {
  if (!needsPreviewCapture(record?.preview)) return
  whenIdle(async () => {
    if (await captureStorePreview(record.theme)) homeRequest.reload()
  })
})

onMounted(loadDomains)

// Staged only on a page load and on the hand-off from onboarding; see ia/homeTasks.
const playEntrance = homeArrival.playEntrance
homeArrival.playEntrance = false
// 75ms apart reads as one sequence: the store, then what to do with it, then the list.
const STAGGER = ['delay-0', 'delay-75', 'delay-150']
const entrance = (step) => ({
  appear: playEntrance,
  enterActiveClass: ['transition-[opacity,transform] duration-500 ease-out-strong', STAGGER[step]].join(' '),
  enterFromClass: 'translate-y-2 opacity-0 motion-reduce:translate-y-0',
})

const isLive = computed(() => Boolean(home.value?.published))
const host = computed(() => customDomain.value?.status === 'connected' ? customDomain.value.name : window.location.host)
const storeUrl = computed(() => `${window.location.protocol}//${host.value}/`)

const tasks = computed(() => (home.value ? buildHomeTasks(home.value, customDomain.value, window.location.host) : []))
const openTasks = computed(() => tasks.value.filter((task) => !task.done))
const visibleTasks = computed(() => openTasks.value.filter((task) => !dismissedTasks.value.includes(task.key)))
const dismissedCount = computed(() => openTasks.value.length - visibleTasks.value.length)
const blockers = computed(() => openTasks.value.filter((task) => task.required))

// What the card drawings personalise: the store's slug, category, country, brand colour and theme look.
const artStore = computed(() => {
  const record = home.value ?? {}
  return {
    slug: storeSlug(record.store_name),
    category: record.store_category,
    country: record.country,
    codEnabled: record.cod_enabled,
    primaryColor: record.primary_color,
    look: lookFor(record.theme, record.theme_names ?? []),
  }
})

const status = computed(() => describeStoreStatus(isLive.value, blockers.value.length))

const publishOpen = ref(false)
const unpublishOpen = ref(false)
const storeName = computed(() => home.value?.store_name || 'your store')

async function setPublished(published, close) {
  if (!(await trySubmit(publishAction, { published: published ? 1 : 0 }))) return
  close()
  homeRequest.reload()
  if (published) toast.success(`${storeName.value} is live`)
  else toast.success('Your store is private again')
}

const publishActions = computed(() => {
  const publish = { label: blockers.value.length ? 'Publish anyway' : 'Publish store', onClick: ({ close }) => setPublished(true, close) }
  if (!blockers.value.length) return [{ ...publish, variant: 'solid' }]
  return [{ label: 'Finish setup first', variant: 'solid', onClick: ({ close }) => close() }, publish]
})

async function copyLink() {
  try {
    await navigator.clipboard.writeText(storeUrl.value)
    toast.success('Link copied')
  } catch {
    toast.error('Could not copy the link')
  }
}
</script>

<template>
  <AppPageHeader title="Home" />

  <PageBody width="wide">
    <!-- Hero row: the store on the left, what it is and what to do next on the right. -->
    <section class="flex flex-col gap-10 pt-4 sm:flex-row sm:items-center sm:gap-12">
      <Transition v-bind="entrance(0)">
        <div class="shrink-0">
          <StorefrontPreview :live="isLive" :url="storeUrl" :host="host" :image="home?.preview?.image" />
        </div>
      </Transition>

      <!-- min-w-0: the URL line truncates instead of pushing the column past the preview. -->
      <Transition v-bind="entrance(1)">
        <div class="min-w-0 flex-1">
          <template v-if="home">
            <div class="flex items-center gap-2 text-sm text-ink-gray-7">
              <span class="size-2 rounded-full" :class="status.dot" />
              {{ status.label }}
            </div>
            <h1 class="mt-3 text-3xl-semibold text-ink-gray-9">{{ status.headline }}</h1>
            <p class="mt-2 text-p-lg text-ink-gray-6">{{ status.subline }}</p>
            <div class="mt-6 flex flex-wrap items-center gap-2">
              <template v-if="isLive">
                <Button variant="solid" size="md" label="View store" icon-right="lucide-arrow-up-right" :href="storeUrl" />
                <Button size="md" label="Copy link" icon-left="lucide-copy" @click="copyLink" />
                <Button
                  v-if="home.can_publish"
                  variant="ghost"
                  size="md"
                  label="Make private"
                  icon-left="lucide-lock"
                  @click="unpublishOpen = true"
                />
              </template>
              <template v-else>
                <Button
                  v-if="home.can_publish"
                  variant="solid"
                  size="md"
                  label="Publish store"
                  icon-left="lucide-rocket"
                  @click="publishOpen = true"
                />
                <Button size="md" label="Preview" icon-right="lucide-arrow-up-right" :href="storeUrl" />
              </template>
            </div>
            <p class="mt-3 flex min-w-0 items-center gap-1.5 text-sm text-ink-gray-5">
              <span class="size-3.5 shrink-0" :class="isLive ? 'lucide-globe' : 'lucide-lock'" aria-hidden="true" />
              <span class="truncate">{{ isLive ? host : 'Visitors see a coming-soon page.' }}</span>
            </p>
          </template>

          <!-- The finished column's rows, so nothing moves when the read lands. -->
          <div v-else aria-hidden="true">
            <Skeleton class="h-4 w-40 rounded-4" />
            <Skeleton class="mt-3 h-9 w-full max-w-sm rounded-4" />
            <Skeleton class="mt-2 h-5 w-64 rounded-4" />
            <Skeleton class="mt-6 h-8 w-56 rounded-4" />
          </div>
        </div>
      </Transition>
    </section>

    <Transition v-bind="entrance(2)">
      <div class="mt-12">
        <StoreOverview v-if="isLive">
          <template #after-stats>
            <section v-if="openTasks.length" class="mt-10">
              <TaskHeading
                title="Grow your store"
                :done="tasks.length - openTasks.length"
                :total="tasks.length"
                :dismissed-count="dismissedCount"
                @restore="restoreTasks"
              />
              <TaskList :tasks="visibleTasks" :store="artStore" @dismiss="dismissTask" />
            </section>
          </template>
        </StoreOverview>

        <section v-else-if="home">
          <TaskHeading
            title="Get ready to sell"
            :done="tasks.length - openTasks.length"
            :total="tasks.length"
            :dismissed-count="dismissedCount"
            @restore="restoreTasks"
          />
          <TaskList :tasks="visibleTasks" :store="artStore" @dismiss="dismissTask" />
        </section>

        <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
          <Skeleton v-for="card in 3" :key="card" class="h-72 rounded-6" />
        </div>
      </div>
    </Transition>
  </PageBody>

  <Dialog
    v-model:open="publishOpen"
    :title="blockers.length ? 'Publish before you can sell?' : `Publish ${storeName}?`"
    icon="lucide-rocket"
    :theme="blockers.length ? 'amber' : 'green'"
    :message="
      blockers.length
        ? `You have not set up ${listBlockers(blockers)} yet. Visitors can browse, but checkout will not work.`
        : `Anyone with the link to ${host} can browse and buy. You can make it private again any time.`
    "
    :actions="publishActions"
  />

  <Dialog
    v-model:open="unpublishOpen"
    title="Make your store private?"
    icon="lucide-lock"
    theme="amber"
    message="Visitors will see a coming-soon page and cannot place orders until you publish again."
    :actions="[{ label: 'Make private', variant: 'solid', onClick: ({ close }) => setPublished(false, close) }]"
  />
</template>
