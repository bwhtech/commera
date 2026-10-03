// All of frappe-ui is shared: extensions import any name, no list to maintain.
// Measured on the real Commera dashboard, this costs 15 kB gzip on first load
// over no sharing, and a curated list would save only 2 kB of it, because the
// dashboard already uses most of frappe-ui. (This toy host uses little of it,
// so here the cost looks far larger; see README.)
export * from 'frappe-ui'
