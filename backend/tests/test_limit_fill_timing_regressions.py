"""Regression tests for engine OHLC same-entry-candle limit fill chronology.

Can run with `python -m unittest discover -s tests -p test_limit_fill_timing_regressions.py`
when installed in backend/tests; no external pytest needed.
"""
from __future__ import annotations
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class TestLimitFillTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        engine = root / 'app/backtesting/engine.py'
        cls.text = engine.read_text(encoding='utf-8')
        cls.iof = (root / 'app/backtesting/strategies/iof01_displacement_ledger_v1.py').read_text(encoding='utf-8')
        tree = ast.parse(cls.text)
        method = next(node for obj in tree.body if isinstance(obj, ast.ClassDef) and obj.name == 'BacktestEngine'
                      for node in obj.body if isinstance(node, (ast.FunctionDef,ast.AsyncFunctionDef)) and node.name == '_intrabar_exit')
        module = ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),method],type_ignores=[])
        ast.fix_missing_locations(module)
        ns = {}
        exec(compile(module, str(engine), 'exec'), ns)
        cls.fn = ns['_intrabar_exit']

    def verify(self, direction, o,h,l,c,stop,target,inside=True,policy='stop_first'):
        pos = SimpleNamespace(direction=direction, stop_loss=stop, take_profit=target)
        bar = {'open':o,'high':h,'low':l,'close':c}
        fake_engine = SimpleNamespace(config=SimpleNamespace(same_bar_policy=policy))
        return type(self).fn(fake_engine,pos,bar,entry_filled_intrabar=inside)

    def test_regression_26r_long_not_awarded_open_before_fill(self):
        # At 22:40 candle opens high, subsequently drops into buy limit.
        # It may never revisit that opening price after entry.
        self.assertIsNone(self.verify('long',3968.445,3968.50,3960.89,3961.0,3960.605,3961.745))

    def test_long_same_bar_profit_requires_close_confirmation(self):
        out=self.verify('long',3968.445,3968.50,3960.89,3961.80,3960.605,3961.745)
        self.assertEqual(out,(3961.745,'target_entry_bar_close_confirmed',False))

    def test_long_entry_bar_stop_overrides_pre_entry_target(self):
        out=self.verify('long',3968.445,3968.50,3960.55,3961.80,3960.605,3961.745)
        self.assertEqual(out,(3960.605,'stop_entry_bar',True))

    def test_short_open_below_target_before_entry_is_not_profit(self):
        self.assertIsNone(self.verify('short',3900,3910,3899,3907,3910.2,3905))

    def test_short_close_confirmed_after_entry(self):
        self.assertEqual(self.verify('short',3900,3910,3899,3904,3910.2,3905),
                         (3905.,'target_entry_bar_close_confirmed',False))

    def test_short_stop_entry_bar(self):
        self.assertEqual(self.verify('short',3900,3911,3899,3904,3910.2,3905),
                         (3910.2,'stop_entry_bar',True))

    def test_carried_long_gap_still_gets_open_price(self):
        self.assertEqual(self.verify('long',3968.445,3970,3967,3969,3960.605,3961.745,inside=False),
                         (3968.445,'target_gap',False))

    def test_carried_short_gap_still_gets_open_price(self):
        self.assertEqual(self.verify('short',3898.,3902.,3896.,3899.,3910.,3905.,inside=False),
                         (3898.,'target_gap',False))

    def test_carried_same_bar_stop_first_policy_unchanged(self):
        self.assertEqual(self.verify('long',3907,3915,3899,3909,3900,3910,inside=False),
                         (3900.,'stop_same_bar',True))

    def test_new_entry_only_tracks_if_limit_crosses_after_open(self):
        self.assertIn('intrabar_limit_fills.add(symbol)', self.text)
        self.assertIn('entry_filled_intrabar=symbol in intrabar_limit_fills', self.text)
        self.assertIn('signal.order_type == "limit"', self.text)
        self.assertIn('outcome.metadata["engine_intrabar_limit_fill_bar"]', self.text)

    def test_iof_management_ignores_unconfirmed_entry_bar_wick(self):
        self.assertIn('entered_inside_this_bar', self.iof)
        self.assertIn('favorable = float(bar["close"])', self.iof)


if __name__ == '__main__':
    unittest.main()
