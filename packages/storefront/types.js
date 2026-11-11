/**
 * A charge in cart, checkout or order results.
 * Included taxes set included to true. Other taxes and plugin fees omit it.
 * An omitted included flag means the amount is added to the price.
 * @typedef {Object} Charge
 * @property {string} description
 * @property {number} amount
 * @property {boolean} [included]
 */

/**
 * Optional fields of a priced cart. Both appear only when the cart has inclusive tax.
 * @typedef {Object} PricedCartTaxFields
 * @property {number} [items_total] Goods total before order discounts, including inclusive tax.
 * @property {Charge[]} [taxes] Tax rows; included amounts are already part of the price.
 */

export {};
