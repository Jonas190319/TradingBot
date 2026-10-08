import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def verify(account, **overrides):
    source = ast.parse(Path(__file__).with_name('main.py').read_text())
    function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_account')
    module = ast.Module(body=[function], type_ignores=[])
    settings = SimpleNamespace(expected_broker='Pepperstone', mt5_login=123,
                               mt5_server='Pepperstone-Demo', require_demo_account=True,
                               mt5_account_label='Pepperstone Demo')
    settings.__dict__.update(overrides)
    namespace = {'mt5': SimpleNamespace(account_info=lambda: account, ACCOUNT_TRADE_MODE_DEMO=0)}
    exec(compile(module, 'main.py', 'exec'), namespace)
    return namespace['verify_account'](settings)


def account(**overrides):
    values = dict(company='Pepperstone', server='Pepperstone-Demo', login=123, trade_mode=0)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_accepts_configured_pepperstone_demo():
    assert verify(account()).login == 123


def test_label_cannot_spoof_broker():
    with pytest.raises(RuntimeError, match='Broker safety'):
        verify(account(company='Other Broker', server='Other-Demo'))


def test_real_account_rejected_even_with_env_override():
    with pytest.raises(RuntimeError, match='Demo safety'):
        verify(account(trade_mode=2), require_demo_account=False)


def test_wrong_login_rejected():
    with pytest.raises(RuntimeError, match='login/server'):
        verify(account(login=456))


def test_empty_broker_rejected():
    with pytest.raises(RuntimeError, match='Broker safety'):
        verify(account(), expected_broker='')


def test_bridge_has_no_order_api():
    tree = ast.parse(Path(__file__).with_name('main.py').read_text())
    assert not any(isinstance(n, ast.Attribute) and n.attr in {'order_send', 'order_check'}
                   for n in ast.walk(tree))
