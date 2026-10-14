<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Avatar, Badge, Button, Rating, Skeleton, Switch, Textarea, dayjs, toast } from 'frappe-ui'
import AppPageHeader from '../components/AppPageHeader.vue'
import PageBody from '../components/PageBody.vue'
import EmptyState from '../components/EmptyState.vue'
import { useAdminAction, useAdminRead } from '../data/api'
import { erpnextLink } from '../data/erpnext'
import { errorMessage } from '../data/errors'
import { productRoute } from '../ia/routes'

const route = useRoute()

const reviewRequest = useAdminRead('reviews.get_review', {
  params: () => ({ name: route.params.id }),
  refetch: true,
})

const review = computed(() => reviewRequest.data)

// A deleted review, a typo'd id and a permission refusal all settle the same
// way — a finished request holding no review — so the wording is chosen from
// whether the request also kept an error, the same split CustomerDetail uses.
const loadFailure = computed(() =>
  reviewRequest.error
    ? {
        icon: 'lucide-triangle-alert',
        title: 'Could not load this review',
        description: errorMessage(reviewRequest.error),
      }
    : {
        icon: 'lucide-search-x',
        title: 'Review not found',
        description: `No review matches ${route.params.id}. It may have been deleted.`,
      },
)

const publishAction = useAdminAction('reviews.set_published', { quiet: true })

// `reviewRequest.data` is a computed with no setter, so a fresh read comes
// from reloading the request rather than assigning the action's response
// onto it — the same reload-after-write shape Orders.vue's fulfilAction uses.
async function togglePublished() {
  const nextValue = !review.value.is_published
  try {
    await publishAction.submit({ name: review.value.name, published: nextValue })
  } catch (error) {
    toast.error(errorMessage(error))
    return
  }
  reviewRequest.reload()
}

const replyDraft = ref('')

// The draft only ever seeds from a freshly loaded/saved review, never
// overwrites what the merchant is mid-typing on a background refetch.
watch(
  () => review.value?.seller_reply,
  (sellerReply) => {
    if (!replyDraft.value) replyDraft.value = sellerReply ?? ''
  },
  { immediate: true },
)

const replyAction = useAdminAction('reviews.save_reply')

async function saveReply() {
  try {
    await replyAction.submit({ name: review.value.name, reply: replyDraft.value })
  } catch {
    return
  }
  toast.success('Reply posted')
  reviewRequest.reload()
}
</script>

<template>
  <template v-if="review">
    <AppPageHeader
      :title="review.review_title || 'Review'"
      back-to="/reviews"
      :breadcrumbs="[{ label: 'Reviews', route: '/reviews' }, { label: review.review_title || review.name }]"
    >
      <template #actions>
        <Switch :model-value="review.is_published" label="Published" @click.stop @update:model-value="togglePublished" />
      </template>
    </AppPageHeader>

    <PageBody width="narrow">
      <section class="rounded-5 border border-outline-gray-1 p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2.5">
            <Avatar :label="review.shopper.name" size="md" />
            <div>
              <p class="text-base text-ink-gray-8">{{ review.shopper.name }}</p>
              <p class="text-sm text-ink-gray-5">{{ review.shopper.email }}</p>
            </div>
          </div>
          <Badge v-if="review.verified_purchase" label="Verified purchase" theme="green" variant="subtle" />
        </div>

        <div class="mt-4 flex items-center gap-2">
          <Rating :model-value="review.rating" disabled size="sm" />
          <span class="text-sm text-ink-gray-5">{{ dayjs(review.creation).fromNow() }}</span>
        </div>

        <p v-if="review.review_title" class="mt-3 text-base-medium text-ink-gray-8">{{ review.review_title }}</p>
        <!-- Shopper-authored text, rendered as text — never as HTML. -->
        <p class="mt-1 whitespace-pre-wrap text-base text-ink-gray-7">{{ review.comment }}</p>

        <div class="mt-4 flex flex-wrap items-center gap-3 border-t border-outline-gray-1 pt-3 text-sm">
          <router-link
            v-if="review.product"
            :to="productRoute(review.product.item_style, review.variant)"
            class="inline-flex items-center gap-1 text-sm-medium text-ink-gray-8 hover:underline"
          >
            {{ review.product.name }}
            <span class="lucide-chevron-right size-3.5 text-ink-gray-5" aria-hidden="true" />
          </router-link>
          <a
            v-if="review.sales_order"
            :href="erpnextLink('Sales Order', review.sales_order)"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1 text-sm-medium text-ink-gray-8 hover:underline"
          >
            {{ review.sales_order }}
            <span class="lucide-external-link size-3.5 text-ink-gray-5" aria-hidden="true" />
          </a>
        </div>
      </section>

      <section class="mt-6">
        <h2 class="text-lg-semibold text-ink-gray-8">Seller reply</h2>
        <p v-if="review.replied_on" class="mt-1 text-sm text-ink-gray-5">
          Last replied {{ dayjs(review.replied_on).fromNow() }} by {{ review.replied_by }}
        </p>
        <Textarea
          v-model="replyDraft"
          class="mt-2"
          placeholder="Write a reply the shopper and other buyers will see under this review…"
          :rows="4"
        />
        <Button
          class="mt-2"
          :label="review.seller_reply ? 'Update reply' : 'Post reply'"
          :loading="replyAction.loading"
          :disabled="!replyDraft.trim()"
          @click="saveReply"
        />
      </section>
    </PageBody>
  </template>

  <template v-else-if="reviewRequest.loading">
    <AppPageHeader :title="route.params.id" back-to="/reviews" :breadcrumbs="[{ label: 'Reviews', route: '/reviews' }, { label: route.params.id }]" />
    <PageBody width="narrow">
      <div class="rounded-5 border border-outline-gray-1 p-4">
        <div class="flex items-center gap-2.5">
          <Skeleton class="size-9 rounded-full" />
          <div class="space-y-2">
            <Skeleton class="h-4 w-32 rounded-4" />
            <Skeleton class="h-3.5 w-44 rounded-4" />
          </div>
        </div>
        <Skeleton class="mt-4 h-4 w-24 rounded-4" />
        <Skeleton class="mt-3 h-4 w-full rounded-4" />
        <Skeleton class="mt-2 h-4 w-2/3 rounded-4" />
      </div>
    </PageBody>
  </template>

  <!-- The request has settled with nothing to show. Without this branch a bad id
       or a refusal falls through every branch above and paints an empty screen. -->
  <template v-else>
    <AppPageHeader :title="route.params.id" back-to="/reviews" :breadcrumbs="[{ label: 'Reviews', route: '/reviews' }, { label: route.params.id }]" />
    <PageBody width="narrow">
      <EmptyState :icon="loadFailure.icon" :title="loadFailure.title" :description="loadFailure.description">
        <Button label="Back to reviews" variant="subtle" theme="gray" route="/reviews" />
      </EmptyState>
    </PageBody>
  </template>
</template>
