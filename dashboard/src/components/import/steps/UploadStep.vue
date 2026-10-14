<script setup>
import { ref } from 'vue'
import { Button, Spinner, toast, useFileUpload } from 'frappe-ui'
import { applyValidation, imp, validateImportAction } from '../../../data/importFlow'
import CoachTip from '../CoachTip.vue'

const { upload } = useFileUpload()

async function pick(event) {
  const file = event?.target?.files?.[0] ?? event?.dataTransfer?.files?.[0]
  if (!file) return

  imp.parsing = true
  imp.parsed = false
  imp.file = { name: file.name, size: `${Math.round(file.size / 1024)} KB` }

  try {
    // Private: a merchant's spreadsheet is working data, not a storefront asset.
    const uploaded = await upload(file, { private: true })
    imp.fileUrl = uploaded.file_url

    try {
      await validateImportAction.submit({ file_url: imp.fileUrl })
    } catch {
      imp.file = null
      imp.fileUrl = null
      return
    }

    applyValidation(validateImportAction.data)
    imp.parsed = true
    toast.success(`${imp.counts.total} rows read from ${file.name}`)
  } catch {
    toast.error(`Could not read ${file.name}`)
    imp.file = null
    imp.fileUrl = null
  } finally {
    imp.parsing = false
  }
}

function clear() {
  imp.file = null
  imp.fileUrl = null
  imp.parsed = false
  imp.headers = []
  imp.rows = []
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-xl text-ink-gray-9">Upload your product file</h2>
      <p class="mt-1.5 text-p-base text-ink-gray-6">
        CSV or Excel, built from
        <a
          class="text-ink-blue-4 underline"
          href="/api/method/commera.api.admin.imports.download_product_template"
        >
          our template
        </a>
        — column names can be anything, we work them out next.
      </p>
    </div>

    <div
      v-if="!imp.file"
      class="flex flex-col items-center justify-center rounded-5 border-2 border-dashed border-outline-gray-2 bg-surface-gray-1 px-6 py-14 text-center"
      @dragover.prevent
      @drop.prevent="pick"
    >
      <div class="flex size-11 items-center justify-center rounded-full bg-surface-base text-ink-gray-6 shadow-sm">
        <span class="lucide-upload size-5" aria-hidden="true" />
      </div>
      <p class="mt-3 text-base text-ink-gray-7">Drop your spreadsheet here</p>
      <p class="mt-1 text-sm text-ink-gray-5">or</p>
      <input type="file" accept=".csv,.xlsx" class="hidden" ref="fileInput" @change="pick" />
      <Button class="mt-2" variant="solid" theme="gray" label="Browse files" @click="$refs.fileInput.click()" />
      <div class="mt-5 flex items-center gap-4 text-sm text-ink-gray-5">
        <span>.csv</span>
        <span>.xlsx</span>
      </div>
    </div>

    <div v-else class="rounded-5 border border-outline-gray-1 p-4">
      <div class="flex items-center gap-3">
        <div class="flex size-9 items-center justify-center rounded-4 bg-surface-green-2 text-ink-green-7">
          <span class="lucide-file-spreadsheet size-4" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="truncate text-base-semibold text-ink-gray-8">{{ imp.file.name }}</div>
          <div class="mt-0.5 text-sm text-ink-gray-5">
            {{ imp.file.size }}
            <template v-if="imp.parsed"> · {{ imp.counts.total }} rows · {{ imp.headers.length }} columns</template>
          </div>
        </div>
        <Spinner v-if="imp.parsing" class="size-4" />
        <Button v-else variant="ghost" icon="lucide-x" label="Remove file" @click="clear" />
      </div>

      <p v-if="imp.parsing" class="mt-3 text-sm text-ink-gray-5">Reading rows and checking your columns…</p>

      <div v-if="imp.parsed" class="mt-4 overflow-x-auto rounded-4 border border-outline-gray-1">
        <table class="w-full min-w-[42rem] border-collapse text-left">
          <thead class="bg-surface-gray-1">
            <tr>
              <th v-for="h in imp.headers" :key="h" class="whitespace-nowrap px-3 py-2 text-sm font-normal text-ink-gray-5">
                {{ h }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-gray-1">
            <tr v-for="row in imp.rows.slice(0, 3)" :key="row.row">
              <td v-for="h in imp.headers" :key="h" class="truncate px-3 py-2 text-sm text-ink-gray-7">
                {{ row[imp.mapping[h]] ?? '' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="imp.parsed" class="mt-2 text-sm text-ink-gray-5">
        Showing the first 3 of {{ imp.counts.total }} rows.
      </p>
    </div>

    <CoachTip
      v-if="!imp.file"
      icon="lucide-download"
      title="Starting from scratch?"
      text="Download our template spreadsheet, fill it in, and drop it back here."
    />
    <CoachTip
      v-else-if="imp.parsed && imp.counts.errors"
      theme="orange"
      icon="lucide-triangle-alert"
      title="A few rows look odd"
      text="That is fine. We show you exactly which ones before anything is saved."
    />
  </div>
</template>

