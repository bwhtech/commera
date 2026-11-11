<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Progress, Select, Spinner, TabButtons, toast, useFileUpload } from 'frappe-ui'
import { beginPhase, canChangeStep, endPhase, imp, isCurrentImport } from '../../../data/importFlow'
import { useAdminAction, trySubmit } from '../../../data/api'
import CoachTip from '../CoachTip.vue'
import { __ } from '../../../data/translation'

const emit = defineEmits(['next'])

const { upload } = useFileUpload()
const matchAction = useAdminAction('imports.match_import_images')

const uploading = computed(() => imp.phase === 'uploading')
const chosenCount = ref(0)
const doneCount = ref(0)

const bulkInput = ref(null)
const groupInput = ref(null)
const activeGroupKey = ref('')

const groups = computed(() => imp.imageMatch?.groups ?? [])

// Split around the placeholder so the example file name keeps its own colour inside one translated sentence.
const matchExample = __('We match each file to a product by its name, so {0} lands on Oversized Tee in Black.').split('{0}')

function assignedPhotos(key) {
  return imp.imageAssignments[key] ?? []
}

const assignedFileUrls = computed(() => new Set(Object.values(imp.imageAssignments).flat()))
const unplacedFiles = computed(() => imp.imageFiles.filter((file) => !assignedFileUrls.value.has(file.file_url)))
const groupsWithPhoto = computed(() => groups.value.filter((group) => assignedPhotos(group.key).length).length)

const groupOptions = computed(() => [
  { label: __('Leave unmatched'), value: '' },
  ...groups.value.map((group) => ({ label: `${group.title} — ${group.color}`, value: group.key })),
])

// A merchant's manual pick beats the file-name match, so re-running the match after another
// upload never drags a photo back off the product they put it on by hand.
function rebuildAssignments() {
  const assignments = {}
  const add = (key, fileUrl) => {
    if (!assignments[key]) assignments[key] = []
    assignments[key].push(fileUrl)
  }
  // A pick made under an earlier column mapping may name a group that no longer exists.
  const groupKeys = new Set(groups.value.map((group) => group.key))
  for (const match of imp.imageMatch?.matched ?? []) {
    if (imp.imageChoices[match.file_url] && groupKeys.has(imp.imageChoices[match.file_url])) continue
    add(match.key, match.file_url)
  }
  for (const [fileUrl, key] of Object.entries(imp.imageChoices)) {
    if (key && groupKeys.has(key)) add(key, fileUrl)
  }
  imp.imageAssignments = assignments
}

// Called with the ticket of an upload already in flight, so the match after it does not need a
// second phase; on its own (on mount) it takes one, which keeps Continue shut until the groups land.
async function matchUploadedFiles(uploadTicket = null) {
  const ticket = uploadTicket ?? beginPhase('matching')
  if (ticket === null) return
  const matched = await trySubmit(matchAction, {
    file_url: imp.fileUrl,
    column_mapping: { ...imp.mapping },
    image_files: imp.imageFiles,
  })
  if (matched && isCurrentImport(ticket)) {
    imp.imageMatch = matchAction.data
    rebuildAssignments()
  }
  if (!uploadTicket) endPhase(ticket)
}

async function addFiles(files, groupKey = '') {
  if (!files.length) return
  const ticket = beginPhase('uploading')
  if (ticket === null) return
  chosenCount.value = files.length
  doneCount.value = 0

  const uploadedFiles = []
  for (const file of files) {
    try {
      // Public: these are storefront product photos, not access-controlled files.
      const result = await upload(file, { private: false })
      // The dialog was reset under this loop: the rest of the batch belongs to a flow that is gone.
      if (!isCurrentImport(ticket)) return
      uploadedFiles.push({ file_name: result.file_name, file_url: result.file_url })
      if (groupKey) imp.imageChoices[result.file_url] = groupKey
      // Counted inside the try: a file that failed is not one of "8 of 8 uploaded".
      doneCount.value += 1
    } catch {
      if (!isCurrentImport(ticket)) return
      toast.error(__('Could not upload {0}', [file.name]))
    }
  }

  imp.imageFiles.push(...uploadedFiles)
  if (uploadedFiles.length) await matchUploadedFiles(ticket)
  endPhase(ticket)
}

function setAssignment(fileUrl, key) {
  imp.imageChoices[fileUrl] = key
  rebuildAssignments()
}

function onBulkFilesPicked(event) {
  const files = [...(event.target.files ?? [])]
  event.target.value = ''
  addFiles(files)
}

function onDrop(event) {
  addFiles([...(event.dataTransfer?.files ?? [])])
}

function chooseGroupFiles(key) {
  activeGroupKey.value = key
  groupInput.value.click()
}

function onGroupFilesPicked(event) {
  const files = [...(event.target.files ?? [])]
  event.target.value = ''
  addFiles(files, activeGroupKey.value)
}

onMounted(() => {
  if (!imp.imageMatch) matchUploadedFiles()
})
</script>

<template>
  <div class="space-y-6">
    <input ref="bulkInput" type="file" accept="image/*" multiple class="hidden" @change="onBulkFilesPicked" />
    <input ref="groupInput" type="file" accept="image/*" multiple class="hidden" @change="onGroupFilesPicked" />

    <div class="flex flex-col items-start gap-3 sm:flex-row sm:gap-4">
      <div class="min-w-0 flex-1">
        <h2 class="text-xl text-ink-gray-9">{{ __('Add product photos') }}</h2>
        <p class="mt-1 text-p-base text-ink-gray-6">
          {{ __('Products sell far better with a photo. You can also skip this and add them later.') }}
        </p>
      </div>
      <!-- The tabs are unbreakable content, wider than the dialog body on a phone.
           Scroll the strip in place rather than letting it push the body. -->
      <TabButtons
        v-model="imp.imagesMode"
        class="max-w-full overflow-x-auto sm:shrink-0 sm:overflow-visible"
        :options="[
          { label: __('Drop a folder'), value: 'bulk' },
          { label: __('One by one'), value: 'each' },
        ]"
      />
    </div>

    <div v-if="imp.phase === 'matching'" class="flex items-center gap-3 text-base text-ink-gray-6">
      <Spinner class="size-4" />
      {{ __('Reading your products…') }}
    </div>

    <!-- A: a folder of files, matched on the product and colour in each name -->
    <template v-if="imp.imagesMode === 'bulk'">
      <div
        v-if="uploading"
        class="rounded-5 border border-outline-gray-1 p-4"
      >
        <div class="flex items-center gap-3">
          <Spinner class="size-4" />
          <span class="text-base text-ink-gray-8">
            {{ matchAction.loading ? __('Matching photos to your products…') : __('Uploading photos') }}
          </span>
          <span class="ms-auto text-sm tabular-nums text-ink-gray-5">{{ __('{0} of {1} uploaded', [doneCount, chosenCount]) }}</span>
        </div>
        <Progress :value="Math.round((doneCount / chosenCount) * 100)" size="sm" class="mt-3" />
      </div>

      <div
        v-else-if="!imp.imageFiles.length"
        class="flex flex-col items-center justify-center rounded-5 border-2 border-dashed border-outline-gray-2 bg-surface-gray-1 px-6 py-12 text-center"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <div class="flex size-11 items-center justify-center rounded-full bg-surface-base text-ink-gray-6 shadow-sm">
          <span class="lucide-images size-5" aria-hidden="true" />
        </div>
        <p class="mt-3 text-base text-ink-gray-7">{{ __('Drop your photos here') }}</p>
        <p class="mt-1 max-w-[440px] text-p-sm text-ink-gray-5">
          {{ matchExample[0] }}<span class="text-ink-gray-7">oversized-tee-black-1.jpg</span>{{ matchExample[1] }}
        </p>
        <Button
          class="mt-3"
          variant="solid"
          theme="gray"
          :label="__('Browse photos')"
          :disabled="!canChangeStep"
          @click="bulkInput.click()"
        />
      </div>

      <template v-else>
        <div class="grid gap-4 sm:grid-cols-3">
          <div class="rounded-5 border border-outline-gray-1 p-4">
            <div class="text-2xl tabular-nums text-ink-green-6">{{ assignedFileUrls.size }}</div>
            <div class="mt-0.5 text-sm text-ink-gray-5">
              {{ __('of {0} photos matched to a product', [imp.imageFiles.length]) }}
            </div>
          </div>
          <div class="rounded-5 border border-outline-gray-1 p-4">
            <div class="text-2xl tabular-nums text-ink-amber-7">{{ unplacedFiles.length }}</div>
            <div class="mt-0.5 text-sm text-ink-gray-5">{{ __('could not be matched') }}</div>
          </div>
          <div class="rounded-5 border border-outline-gray-1 p-4">
            <div class="text-2xl tabular-nums text-ink-gray-7">{{ groups.length - groupsWithPhoto }}</div>
            <div class="mt-0.5 text-sm text-ink-gray-5">{{ __('of {0} products still have no photo', [groups.length]) }}</div>
          </div>
        </div>

        <div v-if="unplacedFiles.length" class="rounded-5 border border-outline-gray-1">
          <div class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
            <span class="text-base-semibold text-ink-gray-8">{{ __('Files we could not place') }}</span>
            <Badge :label="String(unplacedFiles.length)" theme="amber" variant="subtle" />
          </div>
          <div v-scroll-fade class="max-h-72 divide-y divide-outline-gray-1 overflow-y-auto">
            <div v-for="file in unplacedFiles" :key="file.file_url" class="flex items-center gap-3 px-4 py-3">
              <img
                :src="file.file_url"
                alt=""
                class="size-10 shrink-0 rounded-4 border border-outline-gray-1 object-cover"
              />
              <div class="min-w-0 flex-1 truncate text-base text-ink-gray-7">{{ file.file_name }}</div>
              <Select
                :model-value="imp.imageChoices[file.file_url] ?? ''"
                :options="groupOptions"
                class="w-64 shrink-0"
                @update:model-value="(key) => setAssignment(file.file_url, key)"
              />
            </div>
          </div>
        </div>

        <Button icon-left="lucide-plus" :label="__('Add more photos')" :disabled="!canChangeStep" @click="bulkInput.click()" />
      </template>

      <CoachTip
        :title="__('File names do the matching')"
        :text="__('Name each photo after the product and its colour — oversized-tee-black.jpg — and add -1, -2, -3 for extra shots. The first photo for a colour becomes its main image.')"
      />
    </template>

    <!-- B: one product colour at a time -->
    <template v-else>
      <div class="flex flex-wrap items-center gap-3 rounded-4 border border-outline-gray-1 bg-surface-gray-1 px-3 py-2.5">
        <span class="text-base text-ink-gray-7">{{ __('{0} of {1} have a photo', [groupsWithPhoto, groups.length]) }}</span>
        <Progress
          v-if="groups.length"
          :value="Math.round((groupsWithPhoto / groups.length) * 100)"
          size="sm"
          class="max-w-56 flex-1"
        />
        <Button
          class="ms-auto"
          variant="ghost"
          :label="__('Skip the rest for now')"
          :disabled="!canChangeStep"
          @click="emit('next')"
        />
      </div>

      <div v-if="groups.length" class="overflow-hidden rounded-5 border border-outline-gray-1">
        <div class="divide-y divide-outline-gray-1">
          <div v-for="group in groups" :key="group.key" class="flex items-center gap-3 px-4 py-3">
            <div class="flex min-w-0 flex-1 items-center gap-3">
              <div class="flex shrink-0 gap-1">
                <img
                  v-for="fileUrl in assignedPhotos(group.key).slice(0, 3)"
                  :key="fileUrl"
                  :src="fileUrl"
                  alt=""
                  class="size-12 rounded-4 border border-outline-gray-1 object-cover"
                />
                <div
                  v-if="!assignedPhotos(group.key).length"
                  class="flex size-12 items-center justify-center rounded-4 border border-dashed border-outline-gray-2 text-ink-gray-4"
                >
                  <span class="lucide-image-off size-4" aria-hidden="true" />
                </div>
              </div>
              <div class="min-w-0">
                <div class="truncate text-base text-ink-gray-8">{{ group.title }}</div>
                <div class="truncate text-sm text-ink-gray-5">{{ group.color }}</div>
              </div>
            </div>
            <Badge
              v-if="assignedPhotos(group.key).length"
              class="shrink-0"
              :label="assignedPhotos(group.key).length === 1 ? __('1 photo') : __('{0} photos', [assignedPhotos(group.key).length])"
              theme="green"
              variant="subtle"
            />
            <Button
              class="shrink-0"
              :variant="assignedPhotos(group.key).length ? 'subtle' : 'solid'"
              theme="gray"
              :disabled="!canChangeStep"
              icon-left="lucide-upload"
              :label="assignedPhotos(group.key).length ? __('Add more') : __('Upload')"
              @click="chooseGroupFiles(group.key)"
            />
          </div>
        </div>
      </div>

      <CoachTip
        icon="lucide-clock"
        :title="__('Slow going for a long catalogue')"
        :text="__('For {0} product colours, dropping a folder of named photos is far quicker.', [groups.length])"
      />
    </template>
  </div>
</template>
