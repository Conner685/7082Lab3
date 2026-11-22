import pytest
from setup_db import initialize
from repository import StoreRepository
from cart import ShoppingCart
from checkout import CheckoutService
from payments import FakePaymentGateway


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / 'test.db'
    initialize(str(db))
    return StoreRepository(str(db))


def test_add_item_rejects_invalid_quantities_and_unknown_sku(repo):
    cart = ShoppingCart('u1', repo)
    assert not cart.add_item('USB-01', 0)
    assert not cart.add_item('USB-01', -2)
    assert not cart.add_item('USB-01', 1.5)
    assert not cart.add_item('USB-01', True)
    assert not cart.add_item('BAD-SKU', 1)
    assert cart.lines == []


def test_add_item_enforces_cumulative_stock_limit(repo):
    cart = ShoppingCart('u1', repo)
    assert cart.add_item('LAP-01', 3)
    assert not cart.add_item('LAP-01', 3)
    assert cart.add_item('LAP-01', 2)
    assert cart.lines[0].quantity == 5


def test_remove_item_partial_full_and_invalid(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 4)
    assert not cart.remove_item('MOU-01', 0)
    assert not cart.remove_item('MOU-01', -1)
    assert not cart.remove_item('BAD-SKU', 1)
    assert cart.remove_item('MOU-01', 1)
    assert cart.lines[0].quantity == 3
    assert cart.remove_item('MOU-01')
    assert cart.lines == []


def test_discounts_do_not_stack_and_clamp_at_zero(repo):
    cart = ShoppingCart('u1', repo)
    assert not cart.apply_discount('WELCOME10')

    cart.add_item('MOU-01', 2)
    assert cart.subtotal() == 59.90
    assert cart.apply_discount('WELCOME10')
    assert cart.total() == 53.91
    assert cart.apply_discount('WELCOME10')
    assert cart.total() == 53.91
    assert cart.apply_discount('STUDENT20')
    assert cart.total() == 47.92

    cart.remove_item('MOU-01')
    cart.add_item('USB-01', 1)
    assert cart.apply_discount('SAVE15')
    assert cart.total() == 0.0


def test_cart_edits_recalculate_discounted_total(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('USB-01', 2)
    cart.apply_discount('WELCOME10')
    assert cart.total() == 17.98

    cart.add_item('USB-01', 1)
    assert cart.total() == 26.97

    cart.remove_item('USB-01')
    assert cart.total() == 0.0
    assert cart.discount_code is None


def test_saved_cart_idempotent_load_and_stock_clamping(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('LAP-01', 4)
    cart.save()

    repo.update_stock('LAP-01', 3)
    reloaded = ShoppingCart('u1', repo)
    reloaded.load()
    reloaded.load()
    assert len(reloaded.lines) == 1
    assert reloaded.lines[0].quantity == 2


def test_repository_parameterized_queries_and_user_isolation(repo):
    assert repo.get_product("' OR '1'='1") is None
    assert repo.get_saved_cart("' OR '1'='1") == []

    repo.save_order('alice', 50.0, 'paid', 'req-1')
    repo.save_order('bob', 75.0, 'paid', 'req-2')
    assert len(repo.list_orders('alice')) == 1
    assert repo.list_orders('alice')[0][1] == 'alice'


def test_repository_prevents_negative_stock(repo):
    with pytest.raises(ValueError):
        repo.update_stock('LAP-01', 6)
    assert repo.get_product('LAP-01').stock == 5


def test_checkout_empty_cart(repo):
    cart = ShoppingCart('u1', repo)
    gateway = FakePaymentGateway(should_approve=True)
    result = CheckoutService(repo, gateway).checkout(cart, 'TOK', 'req-1')
    assert result.status == 'empty'
    assert result.order_id is None
    assert gateway.calls == []


def test_checkout_paid_updates_stock_and_clears_cart(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 2)
    cart.save()
    gateway = FakePaymentGateway(should_approve=True)

    result = CheckoutService(repo, gateway).checkout(cart, 'TOK', 'req-1')
    assert result.status == 'paid'
    assert result.total == 59.90
    assert repo.get_product('MOU-01').stock == 18
    assert cart.lines == []
    assert repo.get_saved_cart('u1') == []


def test_checkout_declined_and_payment_error_keep_stock_and_cart(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('LAP-01', 1)
    cart.save()

    declined = CheckoutService(repo, FakePaymentGateway(should_approve=False)).checkout(cart, 'TOK', 'req-1')
    assert declined.status == 'declined'
    assert repo.get_product('LAP-01').stock == 5
    assert len(cart.lines) == 1
    assert repo.get_saved_cart('u1') == [('LAP-01', 1)]

    class BrokenGateway:
        def charge(self, amount, payment_token):
            raise RuntimeError('timeout')

    errored = CheckoutService(repo, BrokenGateway()).checkout(cart, 'TOK', 'req-2')
    assert errored.status == 'payment_error'
    assert repo.get_product('LAP-01').stock == 5
    assert len(cart.lines) == 1


def test_checkout_out_of_stock_aborts_before_charge(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 1)
    cart.add_item('LAP-01', 4)
    repo.update_stock('LAP-01', 2)

    gateway = FakePaymentGateway(should_approve=True)
    result = CheckoutService(repo, gateway).checkout(cart, 'TOK', 'req-1')
    assert result.status == 'out_of_stock'
    assert gateway.calls == []
    assert repo.get_product('MOU-01').stock == 20
    assert repo.get_product('LAP-01').stock == 3


def test_checkout_duplicate_request_id_is_idempotent(repo):
    cart = ShoppingCart('u1', repo)
    cart.add_item('MOU-01', 1)
    gateway = FakePaymentGateway(should_approve=True)
    service = CheckoutService(repo, gateway)

    first = service.checkout(cart, 'TOK', 'req-dup')
    cart.add_item('MOU-01', 1)
    second = service.checkout(cart, 'TOK', 'req-dup')

    assert first.status == 'paid'
    assert second == first
    assert len(gateway.calls) == 1
    assert repo.get_product('MOU-01').stock == 19