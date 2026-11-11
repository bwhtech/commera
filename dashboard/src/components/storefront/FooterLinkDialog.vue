<script setup>
import { computed, ref, useId, watch } from 'vue'
import { Button, Combobox, Dialog, FormControl, toast } from 'frappe-ui'
import { __ } from '../../data/translation'

const props = defineProps({
  section: { type: Object, default: null },
  link: { type: Object, default: null },
  pages: { type: Array, default: () => [] },
  submit: { type: Function, required: true },
})

const open = defineModel('open', { type: Boolean, required: true })

// The submit button sits outside the form, so `form` is what makes the browser run
// each field's `required` check.
const formId = useId()

const SOURCE_OPTIONS = [
  { label: __('Custom URL'), value: 'url' },
  { label: __('Existing page'), value: 'page' },
]

const source = ref('url')
const page = ref('')
const label = ref('')
const url = ref('')
const saving = ref(false)

const isEdit = computed(() => Boolean(props.link))

const pageOptions = computed(() => props.pages.map((row) => ({ label: row.name, value: row.name })))

function pageUrl(route) {
  return route.startsWith('/') ? route : `/${route}`
}

watch(open, (isOpen) => {
  if (!isOpen) return
  source.value = 'url'
  page.value = ''
  label.value = props.link?.link_label ?? ''
  url.value = props.link?.link_url ?? ''
})

watch(page, (name) => {
  const match = props.pages.find((row) => row.name === name)
  if (!match) return
  label.value = match.name
  url.value = pageUrl(match.route)
})

async function save() {
  saving.value = true
  try {
    const saved = await props.submit({ label: label.value.trim(), url: url.value.trim() })
    if (!saved) return

    open.value = false
    toast.success(isEdit.value ? __('Link saved') : __('Link added'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" :title="isEdit ? __('Edit link') : __('Add a link')">
    <template #default>
      <form :id="formId" class="space-y-4" @submit.prevent="save">
        <p v-if="section" class="text-p-base text-ink-gray-7">{{ __('In the {0} column.', [section.title]) }}</p>

        <FormControl
          v-if="!isEdit"
          v-model="source"
          type="select"
          :label="__('Link source')"
          :options="SOURCE_OPTIONS"
          :description="__('Pick a page to fill the label and address in for you.')"
        />

        <Combobox
          v-if="source === 'page'"
          v-model="page"
          :options="pageOptions"
          :label="__('Page')"
          :placeholder="__('Search pages')"
        />

        <FormControl v-model="label" :label="__('Label')" required :placeholder="__('Shipping & returns')" />

        <FormControl
          v-model="url"
          :label="__('URL')"
          required
          placeholder="/en/products"
          :description="__('Where this link sends shoppers.')"
        />
      </form>
    </template>

    <template #actions>
      <Button
        class="w-full"
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :loading="saving"
        :label="isEdit ? __('Save') : __('Add')"
      />
    </template>
  </Dialog>
</template>
