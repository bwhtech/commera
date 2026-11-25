// A record's name is free text: an unencoded `/` splits it into extra route segments and a `?`
// starts a query string, so either lands on "nothing at this address".
export function productRoute(productName, variantName) {
  const path = `/products/${encodeURIComponent(productName)}`
  return variantName ? `${path}?variant=${encodeURIComponent(variantName)}` : path
}

export function customerRoute(customerName) {
  return `/customers/${encodeURIComponent(customerName)}`
}

export function orderRoute(orderName) {
  return `/orders/${encodeURIComponent(orderName)}`
}
