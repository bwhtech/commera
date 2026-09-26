<script setup>
import { Badge, Button, Dropdown, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'

const router = useRouter()

// The dashboard's Theme screen today lists themes and a settings form; this
// is the list half, with "Customize" opening the section editor.
const themes = [
  { name: 'summer_theme', title: 'Summer', app: 'commera', live: true, from: '#f59e0b', to: '#ef4444', edited: '2 hours ago' },
  { name: 'shop_default_theme', title: 'Shop Default', app: 'commera', from: '#0ea5e9', to: '#6366f1', edited: 'Never customized' },
  { name: 'atelier_theme', title: 'Atelier', app: 'atelier_themes', from: '#111827', to: '#6b7280', edited: 'Never customized' },
]

const customize = (theme) => router.push(`/themes/${theme.name}/customize`)
</script>

<template>
  <div class="mx-auto max-w-4xl px-6 py-10">
    <h1 class="text-2xl font-semibold text-ink-gray-9">Theme</h1>
    <p class="mt-1 text-base text-ink-gray-6">Pick how your storefront looks, then customize its pages section by section.</p>

    <div class="mt-8 space-y-4">
      <div
        v-for="theme in themes"
        :key="theme.name"
        class="flex items-center gap-5 rounded-lg border border-outline-gray-2 p-4"
        :data-theme-card="theme.name"
      >
        <div class="h-20 w-32 shrink-0 rounded" :style="{ background: `linear-gradient(135deg, ${theme.from}, ${theme.to})` }" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-lg font-semibold text-ink-gray-9">{{ theme.title }}</span>
            <Badge v-if="theme.live" label="Live" theme="green" />
          </div>
          <p class="mt-1 text-sm text-ink-gray-6">From {{ theme.app }} · {{ theme.edited }}</p>
        </div>
        <Dropdown
          :options="[
            { label: 'Preview storefront', icon: 'lucide-external-link', onClick: () => toast.info('Opens the storefront with this theme') },
            ...(theme.live ? [] : [{ label: 'Make live', icon: 'lucide-rocket', onClick: () => toast.success(`${theme.title} is live`) }]),
          ]"
        >
          <Button icon="lucide-ellipsis" variant="ghost" label="More" />
        </Dropdown>
        <Button icon-left="lucide-settings-2" label="Customize" @click="customize(theme)" />
      </div>
    </div>
  </div>
</template>
