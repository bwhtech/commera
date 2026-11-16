# Order progress stepper: how real platforms show it

Short survey for the Commera stepper (Confirmed, Packed, Shipped, Delivered). Where a source did not describe the visual, the row says what is known from the live product and is marked "observed".

| Platform | Where | Direction | Steps | Labels / dates | Mobile behaviour |
|---|---|---|---|---|---|
| Amazon | Order page and shipment emails | Horizontal bar, one continuous track | 4 (Shipped, On the way, Out for delivery, Delivered) | Labels only under the bar; the date is a large status headline above it ("Arriving Thursday") | Same bar; labels are single words so they do not wrap |
| Shopify | Order status page; notification emails | Page: horizontal markers with a check per done step. Emails: no stepper, a status heading and a button | 4 (Confirmed, On its way, Out for delivery, Delivered) | Label plus one short date under done steps | Page collapses to the current step text on small screens (observed) |
| Apple | Order status page and order emails | One status line plus a thin progress bar | 4 (Processing, Preparing to ship, Shipped, Delivered) | Only the current status is named; delivery window shown beside it | Same; there is nothing to wrap |
| Flipkart | App and site order tracking | Vertical timeline, dots joined by a line that fills as the order moves | 4 (Ordered and approved, Packed, Shipped, Delivery) | Label plus date on each row | Vertical by design, so it fits any width |
| Myntra | App order details | Vertical timeline in the detail view, a one-line status in the order list | 4 | Label plus date | Vertical (observed) |
| Nike | Shipping email | No stepper; tracking link and status at the top | 0 | Status text and carrier | Plain text, no layout risk |
| Zara, H&M | Shipping emails | No stepper found; status text and tracking button (observed) | 0 | Status text | Plain text |
| Hims (Email Love / Really Good Emails collections), AfterShip, Zembula templates | Shipping and delivery emails | Horizontal segmented bar, green for done | 3 to 4 | Short labels only | Labels are one word, the bar scales |

## What this says

- Nobody puts a second line (a hint or date) under every step of a horizontal bar. Horizontal trackers keep one-word labels; the date moves into a status line above.
- When each step needs a date, the platforms switch to a vertical timeline (Flipkart, Myntra).
- Several big brands (Nike, Zara, H&M, Shopify notification emails) skip the stepper in email and lead with one status sentence.

## Options derived

1. Amazon-style: status headline, continuous bar, labels only.
2. Apple-style: one status line, thin bar, no step labels.
3. Shopify-style: check markers joined by a line, label plus one short date.
4. Flipkart-style: vertical timeline, label and date on one row.
5. Hims-style: segmented bar (the current design) with labels only and the date moved above.
6. Nike-style: no stepper, a status line only.

## Sources

- Shopify order status page: https://help.shopify.com/en/manual/orders/status-tracking/order-status-overview
- Shopify order status extension target: https://shopify.dev/docs/api/customer-account-ui-extensions/2025-10/targets/order-status
- Amazon progress tracker stages: https://buywithprime.amazon.com/knowledge-center/shipment-tracking
- Amazon Shipping tracking: https://shipping.amazon.com/insights-and-news/how-to-track-your-package
- Apple order statuses: https://parcelsapp.com/en/carriers/apple-store , https://www.digitalcitizen.life/how-to-track-apple-product-shipments/
- Flipkart tracking timeline: https://stories.flipkart.com/track-flipkart-order
- Myntra tracking: https://candid.technology/track-myntra-order/
- Nike shipping email: https://www.nike.com/help/a/order-tracking , https://www.mailcharts.com/email-examples/shipping-confirmation
- Nike receipt (Baymard): https://baymard.com/checkout-usability/benchmark/step-type/receipt/19821-nike
- Progress bars in email (Hims, AfterShip, Zembula): https://emaillove.com/?p=19273 , https://support.aftership.com/en/articles/15441727-enable-shipment-progress-bar-in-email-notifications , https://www.zembula.com/?p=1235
- Email examples roundups: https://mailbakery.com/shipping-confirmation-email-examples/ , https://www.litmus.com/blog/the-best-order-confirmation-emails-have-arrived
