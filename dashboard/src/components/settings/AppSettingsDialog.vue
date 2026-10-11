<script setup>
import { computed, watch } from 'vue'
import {
  Button,
  Icon,
  SettingsBody,
  SettingsContent,
  SettingsDialog,
  SettingsNavGroup,
  SettingsNavItem,
  SettingsPanel,
  SettingsSidebar,
} from 'frappe-ui'
import AdvancedSettings from './AdvancedSettings.vue'
import AppearancePicker from './AppearancePicker.vue'
import AppsSettings from './AppsSettings.vue'
import CashOnDeliverySettings from './CashOnDeliverySettings.vue'
import CheckoutSettings from './CheckoutSettings.vue'
import DeliveryOptionsPanel from './DeliveryOptionsPanel.vue'
import PluginSettingsPanel from './PluginSettingsPanel.vue'
import EmailSettings from './EmailSettings.vue'
import GeneralSettings from './GeneralSettings.vue'
import PluginsSettings from './PluginsSettings.vue'
import IntegrationTabPanel from './IntegrationTabPanel.vue'
import LocationsSettings from './LocationsSettings.vue'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import { paymentIntegrations, shippingIntegrations } from '../../data/integrations'
import { pickupLocations } from '../../data/pickupLocations'
import { pluginSettingsTabs } from '../../ia/plugins'
import { settings } from '../../ia/settings'
import { useIsMobile } from '../../utils/useIsMobile'

// The counts beside the sidebar entries are the server's answer, not a local tally, so
// they cannot claim a provider is live when the site says otherwise.
const connectedCount = paymentIntegrations.connectedCount
const shippingConnected = shippingIntegrations.connectedCount

const pluginTabs = pluginSettingsTabs()

// On a phone the dialog is a full-screen list of sections, then one section at a time.
const isMobile = useIsMobile()
const tab = computed({
  get: () => (isMobile.value ? settings.pickedTab : settings.tab),
  set: (value) => (settings.tab = value),
})

function goBack() {
  if (settings.pickedTab) settings.tab = ''
  else settings.open = false
}

// Both load when the dialog opens, not when their tab is shown: an unread registry counts
// zero, which reads as "nothing is connected".
watch(
  () => settings.open,
  (isOpen) => {
    if (!isOpen) return
    paymentIntegrations.loadOnce()
    shippingIntegrations.loadOnce()
    pickupLocations.loadOnce()
  },
  { immediate: true },
)
</script>

<template>
  <SettingsDialog v-model:open="settings.open" v-model:tab="tab" :unmount-on-hide="false">
    <template #title>Commera settings</template>

    <header class="flex h-12 shrink-0 items-center gap-1 border-b border-outline-gray-1 px-2 sm:hidden">
      <Button
        variant="ghost"
        size="lg"
        icon="lucide-chevron-left"
        :aria-label="settings.pickedTab ? 'Back' : 'Close'"
        @click="goBack"
      />
      <h2 aria-hidden="true" class="text-lg-semibold text-ink-gray-8">Settings</h2>
    </header>

    <SettingsSidebar
      class="max-sm:max-h-none max-sm:flex-1 max-sm:border-b-0 max-sm:[&_[role=tab]]:h-10"
      :class="{ 'max-sm:hidden': settings.pickedTab }"
    >
      <SettingsNavGroup>
        <SettingsNavItem value="general">
          <template #prefix><span class="lucide-store size-4" aria-hidden="true" /></template>
          General
        </SettingsNavItem>
        <SettingsNavItem value="appearance">
          <template #prefix><span class="lucide-sun-moon size-4" aria-hidden="true" /></template>
          Appearance
        </SettingsNavItem>
        <SettingsNavItem value="emails">
          <template #prefix><span class="lucide-mail size-4" aria-hidden="true" /></template>
          Emails
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup label="Checkout">
        <SettingsNavItem value="payments">
          <template #prefix><span class="lucide-credit-card size-4" aria-hidden="true" /></template>
          Payments
          <template #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ connectedCount }}</span>
          </template>
        </SettingsNavItem>
        <SettingsNavItem value="shipping">
          <template #prefix><span class="lucide-truck size-4" aria-hidden="true" /></template>
          Shipping
          <template #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ shippingConnected }}</span>
          </template>
        </SettingsNavItem>
        <SettingsNavItem value="locations">
          <template #prefix><span class="lucide-map-pin size-4" aria-hidden="true" /></template>
          Pickup locations
          <!-- Nothing while pickup is off: a count there would suggest shoppers can collect today. -->
          <template v-if="pickupLocations.pickupEnabled.value" #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ pickupLocations.activeCount.value }}</span>
          </template>
        </SettingsNavItem>
        <SettingsNavItem value="checkout">
          <template #prefix><span class="lucide-shopping-cart size-4" aria-hidden="true" /></template>
          General
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup label="Connections">
        <SettingsNavItem value="apps">
          <template #prefix><span class="lucide-chart-line size-4" aria-hidden="true" /></template>
          Analytics
        </SettingsNavItem>
        <SettingsNavItem value="plugins">
          <template #prefix><span class="lucide-blocks size-4" aria-hidden="true" /></template>
          Plugins
        </SettingsNavItem>
        <SettingsNavItem value="advanced">
          <template #prefix><span class="lucide-sliders-horizontal size-4" aria-hidden="true" /></template>
          Advanced
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup v-if="pluginTabs.length" label="Installed plugins">
        <SettingsNavItem v-for="tab in pluginTabs" :key="tab.value" :value="tab.value">
          <template #prefix><Icon :name="tab.icon" class="size-4" /></template>
          {{ tab.label }}
        </SettingsNavItem>
      </SettingsNavGroup>
    </SettingsSidebar>

    <!-- min-w-0 on the column and every panel: frappe-ui gives them `flex-1` with no
         min-width, so below ~780px the right-hand controls are clipped clean off. -->
    <SettingsContent class="commera-settings min-w-0" :class="{ 'max-sm:hidden': !settings.pickedTab }">
      <SettingsPanel value="general" class="min-w-0">
        <GeneralSettings :active="settings.open && settings.tab === 'general'" />
      </SettingsPanel>

      <SettingsPanel value="emails" class="min-w-0">
        <EmailSettings :active="settings.open && settings.tab === 'emails'" />
      </SettingsPanel>

      <SettingsPanel value="locations" class="min-w-0">
        <LocationsSettings :active="settings.open && settings.tab === 'locations'" />
      </SettingsPanel>

      <SettingsPanel value="checkout" class="min-w-0">
        <CheckoutSettings :active="settings.open && settings.tab === 'checkout'" />
      </SettingsPanel>

      <SettingsPanel value="appearance" class="min-w-0">
        <!-- The blank line keeps this tab's header level with the others. -->
        <SettingsPanelHeader>
          <div class="flex min-w-0 flex-col gap-1">
            <h2 class="text-lg font-semibold text-ink-gray-8">Appearance</h2>
            <p class="text-base" aria-hidden="true">&nbsp;</p>
          </div>
        </SettingsPanelHeader>
        <SettingsBody v-scroll-fade>
          <AppearancePicker />
        </SettingsBody>
      </SettingsPanel>

      <SettingsPanel value="payments" class="min-w-0">
        <IntegrationTabPanel
          :store="paymentIntegrations"
          :active="settings.tab === 'payments'"
          title="Payments"
          description="Turn on as many providers as you like. Each keeps its own keys."
        >
          <CashOnDeliverySettings :active="settings.open && settings.tab === 'payments'" />
        </IntegrationTabPanel>
      </SettingsPanel>

      <SettingsPanel value="shipping" class="min-w-0">
        <IntegrationTabPanel
          v-slot="{ takeover, setTakeover }"
          :store="shippingIntegrations"
          :active="settings.tab === 'shipping'"
          title="Shipping"
          description="Carriers this store books with. Each quotes its own rates at checkout."
        >
          <DeliveryOptionsPanel
            :configuring="takeover"
            :active="settings.open && settings.tab === 'shipping'"
            @update:configuring="setTakeover"
          />
        </IntegrationTabPanel>
      </SettingsPanel>

      <SettingsPanel value="apps" class="min-w-0">
        <AppsSettings :active="settings.open && settings.tab === 'apps'" />
      </SettingsPanel>

      <SettingsPanel value="plugins" class="min-w-0">
        <PluginsSettings :active="settings.open && settings.tab === 'plugins'" />
      </SettingsPanel>

      <SettingsPanel v-for="tab in pluginTabs" :key="tab.value" :value="tab.value" class="min-w-0">
        <PluginSettingsPanel :entry="tab.entry" :active="settings.open && settings.tab === tab.value" />
      </SettingsPanel>

      <SettingsPanel value="advanced" class="min-w-0">
        <AdvancedSettings :active="settings.open && settings.tab === 'advanced'" />
      </SettingsPanel>
    </SettingsContent>
  </SettingsDialog>
</template>

<style>
/* frappe-ui's Dialog keeps its card gutter on a phone, which pushes the full-screen settings
   past the viewport, and its panels keep their desktop insets. Its wrapper is min-h-screen
   (100vh), which on a real phone is taller than the visible 100dvh while the address bar
   shows, so the centred dialog gets a gap above and below. Headless Chrome hides this. */
@media (max-width: 639.98px) {
  .dialog-scroll-container > div:has(.commera-settings) {
    min-height: 100dvh;
    justify-content: flex-start;
    padding: 0;
  }

  .dialog-content:has(.commera-settings) {
    margin: 0;
    border-radius: 0;
  }

  /* frappe-ui's SettingsRow is always side by side; a row with a full-size control stacks,
     like buzz's settings, so the label keeps the width. */
  .commera-settings .gap-8.py-3\.5:has(.sm\:w-72, .sm\:w-40) {
    flex-direction: column;
    align-items: stretch;
    gap: 0.5rem;
  }

  /* SettingsHeader's actions never shrink, so three of them crush the title; wrap them under it. */
  .commera-settings .items-start.justify-between.gap-4 {
    flex-wrap: wrap;
  }

  .commera-settings .items-start.justify-between.gap-4 > .min-w-0.flex-col {
    flex: 1 1 12rem;
  }

  .commera-settings .items-start.justify-between.gap-4 > .shrink-0 {
    flex-wrap: wrap;
  }

  .commera-settings .px-\[4\.4rem\] {
    padding-inline: 1rem;
  }

  .commera-settings .px-\[4\.4rem\].pt-10 {
    padding-top: 1.25rem;
  }
}
</style>
