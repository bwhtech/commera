<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Dropdown, FormControl, LoadingText, Switch, TextInput, dialog, toast } from 'frappe-ui'
import AppPageHeader from '../../components/AppPageHeader.vue'
import PageBody from '../../components/PageBody.vue'
import EmptyState from '../../components/EmptyState.vue'
import RichTextField from '../../components/RichTextField.vue'
import { usePages } from '../../data/pages'
import { errorMessage } from '../../data/errors'
import { longDate } from '../../data/format'

const route = useRoute()
const router = useRouter()
const { getPage, savePage, removePage } = usePages()

function blankPage() {
  return {
    name: '',
    route: '',
    published: true,
    content: '',
    // Not edited here any more, but still round-tripped through load and save so a page
    // that already carries Arabic content keeps it instead of being blanked on the next
    // save. The storefront still serves it (shop_web_page.py get_content).
    content_ar: '',
    meta_title: '',
    meta_description: '',
    og_image: '',
    noindex: false,
    url: '',
    modified: '',
  }
}

// The server speaks Check fields as 1/0 and leaves an untouched Data field null,
// either of which breaks a Switch or a `.trim()` on the way in.
function toForm(data) {
  const form = blankPage()
  for (const field of Object.keys(form)) {
    form[field] = typeof form[field] === 'boolean' ? Boolean(data[field]) : (data[field] ?? '')
  }
  return form
}

function openStorefront() {
  window.open(form.value.url, '_blank', 'noopener')
}

const form = ref(blankPage())
const loading = ref(false)
const loadError = ref(null)
const saving = ref(false)

// The doc name IS the title, so an unsaved page has no name yet.
const savedName = ref('')
const isNew = computed(() => !savedName.value)

// Shown while the route field is still blank: the server derives it from the title.
const previewUrl = computed(() => {
  const slug = form.value.route.trim() || slugify(form.value.name)
  return slug ? `/en/page/${slug}` : ''
})

function slugify(title) {
  return title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

function isBlankRichText(html) {
  return !html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
}

async function load(name) {
  if (!name) {
    form.value = blankPage()
    savedName.value = ''
    loadError.value = null
    return
  }

  loading.value = true
  try {
    const { data, error } = await getPage(name)
    loadError.value = error
    if (!data) return
    form.value = toForm(data)
    savedName.value = data.name
  } finally {
    loading.value = false
  }
}

onMounted(() => load(route.params.name))

watch(
  () => route.params.name,
  (name) => {
    // A create that just saved replaces the url with its own name — already loaded.
    if (name === savedName.value) return
    load(name)
  },
)

async function save() {
  const title = form.value.name.trim()
  if (!title) {
    toast.error('Give the page a title')
    return
  }
  if (isBlankRichText(form.value.content)) {
    toast.error('The page needs some content')
    return
  }

  saving.value = true
  try {
    const saved = await savePage({
      name: savedName.value || null,
      title,
      route: form.value.route.trim(),
      published: form.value.published ? 1 : 0,
      content: form.value.content,
      content_ar: form.value.content_ar,
      meta_title: form.value.meta_title,
      meta_description: form.value.meta_description,
      og_image: form.value.og_image,
      noindex: form.value.noindex ? 1 : 0,
    })
    if (!saved) return

    const wasNew = isNew.value
    form.value = toForm(saved)
    savedName.value = saved.name
    if (route.params.name !== saved.name) {
      router.replace(`/storefront/pages/${encodeURIComponent(saved.name)}`)
    }
    toast.success(wasNew ? 'Page created' : 'Saved')
  } finally {
    saving.value = false
  }
}

function remove() {
  dialog.danger({
    title: `Delete "${savedName.value}"?`,
    message: 'Shoppers following a link to this page will get a not-found instead.',
    confirmLabel: 'Delete page',
    onConfirm: async () => {
      if (!(await removePage(savedName.value))) return
      toast.success('Page deleted')
      router.replace('/storefront/pages')
    },
  })
}
</script>

<template>
  <AppPageHeader
    :title="isNew ? 'New page' : savedName"
    back-to="/storefront/pages"
    :breadcrumbs="[
      { label: 'Pages', route: '/storefront/pages' },
      { label: isNew ? 'New page' : savedName },
    ]"
  >
    <template #actions>
      <Dropdown
        v-if="!isNew"
        :options="[
          { label: 'View on storefront', icon: 'lucide-external-link', onClick: openStorefront },
          { label: 'Delete page', icon: 'lucide-trash-2', theme: 'red', onClick: remove },
        ]"
      >
        <Button icon="lucide-ellipsis" label="More actions" />
      </Dropdown>
      <Button label="Save" variant="solid" theme="gray" :loading="saving" @click="save" />
    </template>
  </AppPageHeader>

  <PageBody width="narrow">
    <LoadingText v-if="loading" />

    <EmptyState
      v-else-if="loadError"
      icon="lucide-triangle-alert"
      title="Could not load this page"
      :description="errorMessage(loadError)"
    />

    <div v-else class="space-y-11">
      <section class="space-y-4">
        <FormControl
          v-model="form.name"
          label="Title"
          required
          placeholder="Shipping & returns"
          description="Shoppers see this at the top of the page, and it names the page everywhere else."
        />

        <TextInput
          v-model="form.route"
          class="w-full"
          label="Address"
          placeholder="shipping-returns"
          :description="previewUrl ? `Lives at ${previewUrl}` : 'Left blank, it is built from the title.'"
        />

        <Switch
          v-model="form.published"
          size="sm"
          label="Published"
          description="An unpublished page is hidden from shoppers until you switch this on."
        />
      </section>

      <section>
        <h2 class="text-lg-semibold text-ink-gray-8">Content</h2>

        <div class="mt-4">
          <RichTextField
            v-model="form.content"
            min-height="min-h-64"
            placeholder="Write the page…"
          />
        </div>
      </section>

      <section>
        <h2 class="text-lg-semibold text-ink-gray-8">Search engine listing</h2>
        <p class="mt-1 text-p-sm text-ink-gray-5">How this page appears on Google and when shared.</p>

        <div class="mt-4 space-y-4">
          <FormControl
            v-model="form.meta_title"
            label="Meta title"
            description="Overrides the page title in search results. Left blank, the title above is used."
          />
          <FormControl
            v-model="form.meta_description"
            type="textarea"
            :rows="3"
            label="Meta description"
            description="Roughly 160 characters shows in search results."
          />
          <TextInput
            v-model="form.og_image"
            class="w-full"
            label="Share image"
            placeholder="/files/shipping.jpg"
            description="The image shown when the page is shared. Paste the address of an uploaded file."
          />

          <Switch
            v-model="form.noindex"
            size="sm"
            label="Hide from search engines"
            description="The page stays reachable by link, but Google is told not to list it."
          />
        </div>
      </section>

      <p v-if="form.modified" class="text-sm text-ink-gray-5">
        Last saved {{ longDate(form.modified) }}
      </p>
    </div>
  </PageBody>
</template>
