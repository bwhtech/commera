<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import {
  forgetWelcomeSeen,
  hasSeenWelcome,
  markWelcomeSeen,
  reopenSetup,
  setupDismissed,
  useSetupSteps,
} from '../../ia/firstRun'
import { useIsMobile } from '../../utils/useIsMobile'
import SetupPanel from './SetupPanel.vue'
import WelcomeGreeting from './WelcomeGreeting.vue'

const route = useRoute()

const { steps, settingUp } = useSetupSteps()

// A fixed 20rem panel is the whole screen at phone width, and the sidebar banner
// cannot stand in: AppShell is swapped for MobileLayout below `sm`.
const isMobile = useIsMobile()
const showPanel = computed(() => settingUp.value && !setupDismissed.value && !isMobile.value)

const forced = 'replay' in route.query

const greetingDone = ref(forced ? false : hasSeenWelcome())

const handedOver = ref(greetingDone.value)

// Remounting is what replays the draw, so the key carries a counter.
const replayCount = ref(0)

function finishGreeting() {
  markWelcomeSeen()
  greetingDone.value = true
}

function replay() {
  forgetWelcomeSeen()
  reopenSetup()
  greetingDone.value = false
  handedOver.value = false
  replayCount.value += 1
}
</script>

<template>
  <WelcomeGreeting
    v-if="showPanel && !greetingDone"
    :key="`greeting-${replayCount}`"
    @exiting="handedOver = true"
    @dismiss="finishGreeting"
  />
  <SetupPanel v-if="showPanel && handedOver" :key="`panel-${replayCount}`" :steps="steps" />

  <!-- Rides on `?done=`, so it is never on a real load. -->
  <div
    v-if="settingUp && greetingDone && !isMobile"
    class="fixed bottom-5 left-[15rem] z-[60] flex items-center gap-2"
  >
    <Button icon-left="lucide-rotate-ccw" label="Replay" class="shadow-lg" @click="replay" />
  </div>
</template>
