<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Button, Dialog, ErrorMessage, TextInput, toast, useFileUpload } from 'frappe-ui'
import SwatchDot from './SwatchDot.vue'
import { useAdminAction } from '../data/api'

const props = defineProps({
  attribute: { type: Object, default: null },
})

const open = defineModel('open', { type: Boolean, default: false })
const emit = defineEmits(['saved'])

const { upload, isUploading } = useFileUpload()
const setAction = useAdminAction('catalog.set_swatch')
const clearAction = useAdminAction('catalog.clear_swatch')
const renameAction = useAdminAction('catalog.rename_attribute_value')
const addAction = useAdminAction('catalog.add_attribute_value')

const rows = ref([])
const fileInputs = ref({})
const nameInputs = ref({})
const savingValue = ref('')
const editingValue = ref('')
const cancelling = ref(false)
const newValue = ref('')

const isColour = computed(() => Boolean(props.attribute?.is_colour))

watch(
  () => props.attribute,
  (attribute) => {
    rows.value = (attribute?.values ?? []).map((entry) => ({ ...entry }))
    editingValue.value = ''
    newValue.value = ''
  },
  { immediate: true },
)

async function startRename(row) {
  if (row.used_by) return
  editingValue.value = row.value
  await nextTick()
  const input = nameInputs.value[row.value]
  input?.focus?.()
  input?.select?.()
}

// Escape leaves through the same blur as Enter, so it has to say it meant to discard.
function cancelRename(event) {
  cancelling.value = true
  event.target.blur()
}

async function commitRename(row, typed) {
  editingValue.value = ''
  if (cancelling.value) {
    cancelling.value = false
    return
  }

  const next = (typed ?? '').trim()
  if (!next || next === row.value) return

  savingValue.value = row.value
  try {
    await renameAction.submit({ attribute: props.attribute.name, value: row.value, new_value: next })
  } catch {
    return
  } finally {
    savingValue.value = ''
  }
  row.value = next
  emit('saved')
}

async function save(row, changes) {
  const next = { ...row, ...changes }
  if (!next.color && !next.image) return clear(row)

  savingValue.value = row.value
  try {
    await setAction.submit({
      attribute: props.attribute.name,
      value: row.value,
      color: next.color ?? '',
      image: next.image ?? '',
    })
  } catch {
    return
  } finally {
    savingValue.value = ''
  }
  Object.assign(row, changes)
  emit('saved')
}

async function clear(row) {
  savingValue.value = row.value
  try {
    await clearAction.submit({ attribute: props.attribute.name, value: row.value })
  } catch {
    return
  } finally {
    savingValue.value = ''
  }
  row.color = null
  row.image = null
  emit('saved')
}

async function uploadImage(row, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  try {
    const uploaded = await upload(file, { private: false })
    await save(row, { image: uploaded.file_url })
  } catch {
    toast.error(`Could not upload ${file.name}`)
  }
}

async function addValue() {
  const value = newValue.value.trim()
  if (!value) return
  try {
    await addAction.submit({ attribute: props.attribute.name, value })
  } catch {
    return
  }
  rows.value.push({ value, color: null, image: null, used_by: 0 })
  newValue.value = ''
  emit('saved')
}
</script>

<template>
  <Dialog v-model:open="open" size="2xl" :title="attribute ? attribute.name : 'Attribute'">
    <div v-if="attribute" class="space-y-4">
      <p class="text-p-sm text-ink-gray-5">
        <template v-if="isColour">
          A shopper sees these instead of the words. Upload an image for a pattern a flat colour
          cannot show — denim, floral, marble.
        </template>
        <template v-else>
          The choices a shopper picks from. Click a name to rename one.
        </template>
      </p>

      <div v-if="rows.length" class="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
        <div v-for="row in rows" :key="row.value" class="flex items-center gap-3 py-3">
          <!-- A plain input, not TextInput: TextInput settles on its own schedule, which committed
               the rename after a single keystroke. -->
          <input
            v-if="editingValue === row.value"
            :ref="(element) => (nameInputs[row.value] = element)"
            :value="row.value"
            class="min-w-0 flex-1 rounded-4 border border-transparent bg-surface-gray-2 px-2 py-1 text-base text-ink-gray-8 hover:bg-surface-gray-3 focus:border-outline-gray-4 focus:bg-surface-base focus:shadow-sm focus:ring-0 focus-visible:outline-none"
            :aria-label="`Rename ${row.value}`"
            @keyup.enter="$event.target.blur()"
            @keyup.escape="cancelRename"
            @blur="commitRename(row, $event.target.value)"
          />
          <button
            v-else
            type="button"
            class="group flex min-w-0 flex-1 items-center gap-1.5 rounded-4 px-2 py-1 text-start text-base"
            :class="
              row.used_by
                ? 'cursor-not-allowed text-ink-gray-5'
                : 'text-ink-gray-8 hover:bg-surface-gray-3'
            "
            :title="
              row.used_by
                ? `Used by ${row.used_by} ${row.used_by === 1 ? 'product' : 'products'} — renaming would leave their SKUs and links saying ${row.value}.`
                : `Rename ${row.value}`
            "
            @click="startRename(row)"
          >
            <span class="min-w-0 flex-1 truncate">{{ row.value }}</span>
            <span
              class="size-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
              :class="row.used_by ? 'lucide-lock' : 'lucide-pencil'"
              aria-hidden="true"
            />
          </button>

          <template v-if="isColour">
            <!-- The circle is the preview and the picker at once, so an uploaded image is visible
                 where the colour would be; the native input sits over it, invisible. -->
            <label class="relative inline-flex size-6 shrink-0 cursor-pointer">
              <SwatchDot
                :color="row.color"
                :image="row.image"
                :label="row.value"
                size="md"
                class="pointer-events-none"
              />
              <input
                :value="row.color || '#000000'"
                type="color"
                class="absolute inset-0 size-full cursor-pointer opacity-0"
                :aria-label="`${row.value} colour`"
                @change="save(row, { color: $event.target.value })"
              />
            </label>

            <!-- TextInput emits update:modelValue on the settled value and has no change event of
                 its own; a @change here would fall through to the native input and hand us a DOM
                 Event instead of the hex. -->
            <TextInput
              :model-value="row.color ?? ''"
              class="w-28 shrink-0"
              placeholder="#000000"
              :aria-label="`${row.value} hex`"
              @update:model-value="save(row, { color: $event })"
            />

            <input
              :ref="(element) => (fileInputs[row.value] = element)"
              type="file"
              accept="image/*"
              class="hidden"
              @change="uploadImage(row, $event)"
            />
            <Button
              class="w-28 shrink-0"
              :loading="isUploading && savingValue === row.value"
              icon-left="lucide-image"
              :label="row.image ? 'Replace' : 'Image'"
              variant="subtle"
              @click="fileInputs[row.value]?.click()"
            />

            <Button
              :disabled="!row.color && !row.image"
              icon="lucide-x"
              :aria-label="`Clear ${row.value} swatch`"
              variant="ghost"
              @click="clear(row)"
            />
          </template>
        </div>
      </div>

      <div class="flex items-end gap-2">
        <TextInput
          v-model="newValue"
          class="min-w-0 flex-1"
          :label="`Add a value to ${attribute.name}`"
          placeholder="Type a new one"
          @keydown.enter="addValue"
        />
        <Button label="Add" :loading="addAction.loading" @click="addValue" />
      </div>
      <ErrorMessage :message="addAction.error?.message" />
    </div>
  </Dialog>
</template>
