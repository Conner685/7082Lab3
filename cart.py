"""Business logic. Several design and correctness issues are intentional."""
from models import CartLine


class ShoppingCart:
    COUPONS = ('WELCOME10', 'STUDENT20', 'SAVE15', 'FREESHIP')

    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None

    @property
    def discounted_total(self):
        return self.total() if self.discount_code and self.lines else None

    def _valid_qty(self, quantity):
        return isinstance(quantity, int) and not isinstance(quantity, bool) and quantity > 0

    def add_item(self, sku, quantity):
        if not self._valid_qty(quantity):
            return False
        product = self.repository.get_product(sku)
        if not product:
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        new_qty = (existing.quantity if existing else 0) + quantity
        if new_qty > product.stock:
            return False
        if existing:
            existing.quantity = new_qty
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        if quantity is not None and not self._valid_qty(quantity):
            return False
        for line in self.lines:
            if line.sku == sku:
                if quantity is None or quantity >= line.quantity:
                    self.lines.remove(line)
                else:
                    line.quantity -= quantity
                if not self.lines:
                    self.discount_code = None
                return True
        return False

    def subtotal(self):
        return round(sum(line.unit_price * line.quantity for line in self.lines), 2)

    def total(self):
        sub = self.subtotal()
        if sub <= 0 or not self.discount_code:
            return sub
        if self.discount_code == 'WELCOME10':
            amount = sub * 0.9
        elif self.discount_code == 'STUDENT20':
            amount = sub * 0.8
        elif self.discount_code == 'SAVE15':
            amount = max(0.0, sub - 15.0)
        else:
            amount = sub
        return round(amount, 2)

    def apply_discount(self, code):
        if not self.lines or code not in self.COUPONS:
            return False
        self.discount_code = code
        return True

    def load(self):
        self.lines.clear()
        self.discount_code = None
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            product = self.repository.get_product(sku)
            if product and product.stock > 0 and self._valid_qty(quantity):
                self.add_item(sku, min(quantity, product.stock))

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
