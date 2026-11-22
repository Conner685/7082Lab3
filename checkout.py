"""Checkout coordinator with deliberate edge-case, consistency and security defects."""
import sqlite3
from models import OrderResult


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    def checkout(self, cart, payment_token, request_id):
        if not cart.lines:
            return OrderResult(None, 'empty', 0.0)

        amount = cart.total()
        if not isinstance(payment_token, str) or not payment_token.strip():
            return OrderResult(None, 'invalid_payment', amount)
        if not isinstance(request_id, str) or not request_id.strip():
            return OrderResult(None, 'invalid_request', amount)

        req_id = request_id.strip()
        existing = self.repository.get_paid_order(cart.user_id, req_id)
        if existing:
            return OrderResult(existing[0], existing[1], existing[2])

        for line in cart.lines:
            product = self.repository.get_product(line.sku)
            if line.quantity <= 0 or not product or product.stock < line.quantity:
                return OrderResult(None, 'out_of_stock', amount)

        try:
            response = self.payment_gateway.charge(amount, payment_token)
            status = 'paid' if response and response.get('approved') else 'declined'
        except Exception:
            status = 'payment_error'

        if status != 'paid':
            order_id = self.repository.save_order(cart.user_id, amount, status, req_id)
            return OrderResult(order_id, status, amount)

        try:
            order_id = self.repository.complete_paid_checkout(
                cart.user_id, cart.lines, amount, req_id
            )
        except sqlite3.IntegrityError:
            existing = self.repository.get_paid_order(cart.user_id, req_id)
            if existing:
                return OrderResult(existing[0], existing[1], existing[2])
            raise
        except ValueError:
            return OrderResult(None, 'out_of_stock', amount)

        cart.lines.clear()
        cart.discount_code = None
        return OrderResult(order_id, 'paid', amount)
