Defects Found and Fixed
test
1. SQL injection in repository.py (get_product and get_saved_cart)
Where: StoreRepository.get_product and StoreRepository.get_saved_cart built SQL strings using f-strings.
Risk: Arbitrary SQL injection and query errors on quotes.
Fix: Switched both queries to parameterized ? placeholders.

2. Missing user_id filter in repository.py (list_orders)
Where: StoreRepository.list_orders ignored its user_id argument.
Risk: Returned orders belonging to every user in the database.
Fix: Added WHERE user_id = ? to the SELECT query.

3. Negative stock allowed and non-atomic checkout updates in repository.py and setup_db.py
Where: StoreRepository.update_stock reduced stock without checking remaining inventory, and checkout ran separate connections.
Risk: Stock could drop below zero, and partial updates could remain after a failure.
Fix: Added WHERE sku = ? AND stock >= ?, database CHECK constraints, and a single atomic complete_paid_checkout transaction.

4. Unvalidated quantities in cart.py (add_item and remove_item)
Where: ShoppingCart.add_item and ShoppingCart.remove_item accepted zero, negative, float, or boolean quantities.
Risk: Negative quantities in add_item reduced stock or corrupted totals, and negative quantities in remove_item increased line quantities.
Fix: Added _valid_qty to enforce positive integers in both methods.

5. Cumulative stock check missing on repeated add_item calls in cart.py
Where: ShoppingCart.add_item only checked product.stock < quantity instead of existing.quantity + quantity.
Risk: Calling add_item multiple times allowed cart quantities to exceed available stock.
Fix: Validated combined existing + added quantity against product.stock.

6. Stale discounted_total after cart edits in cart.py
Where: ShoppingCart.apply_discount stored a static discounted_total that never updated when items were added or removed.
Risk: Removing all items still left a positive total, and adding items ignored the active discount.
Fix: Computed discounts dynamically from current subtotal() and discount_code inside total(), and cleared discount_code when the cart becomes empty.

7. Discount stacking and negative totals in cart.py
Where: ShoppingCart.apply_discount calculated discounts from total() rather than subtotal() and allowed SAVE15 to go below zero.
Risk: Re-applying coupons compounded discounts, and SAVE15 on items under $15 created a negative charge.
Fix: Calculated discounts from subtotal(), rejected coupons on empty carts, clamped SAVE15 at 0.0, and rounded totals to 2 decimal places.

8. Duplicate quantities when reloading saved carts in cart.py
Where: ShoppingCart.load appended saved rows onto existing self.lines without clearing first.
Risk: Calling load() more than once doubled item quantities, and stale saved quantities could exceed current stock.
Fix: Cleared self.lines and discount_code before loading and clamped restored quantities to current product stock.

9. Stock deducted before payment and missing pre-charge stock verification in checkout.py
Where: CheckoutService.checkout decremented stock before calling payment_gateway.charge() and never re-checked inventory.
Risk: Declined or failed payments permanently reduced inventory, and out-of-stock items could still be charged.
Fix: Checked stock before charging and moved stock deduction into a post-payment atomic transaction.

10. Cart cleared on failed payments, raw payment tokens printed, and duplicate request_ids charged twice in checkout.py
Where: CheckoutService.checkout cleared the cart regardless of payment status, printed payment_token to stdout, and did not deduplicate request_id.
Risk: Users lost their cart on declined payments, tokens leaked in logs, and retried requests double-charged customers.
Fix: Removed token printing, preserved the cart when status != 'paid', validated token/request_id, and enforced idempotency on paid (user_id, request_id) pairs.