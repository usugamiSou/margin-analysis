import numpy as np
import pandas as pd
from base import PositionType, FutureVariety, Exchange


class MarginCalculator:
    def __init__(self, pos: pd.Series, margin_ratio_df: pd.DataFrame):
        for key, value in pos.dropna().items():
            setattr(self, key, value)
        variety = self.variety.name
        if variety not in ('ETF', 'Index'):
            self.margin_ratio = margin_ratio_df.loc[variety, 'MarginRatio']

    def calc(self):
        if self.type == PositionType.Future:
            return self.calc_future()
        elif self.type == PositionType.Option:
            return self.calc_option()

    def calc_future(self, pv=None):
        # self.pv = self.pv if pv is None else pv
        return self.pv * self.contract_unit * self.margin_ratio

    def calc_option(self, s=None):
        if self.long_short == 'long':
            return 0
        # self.s = self.s if s is None else s
        if self.exchange in (Exchange.SH, Exchange.SZ):
            if self.call_put == 'call':
                otm = max(self.strike_price - self.s, 0)
                return (self.pv + max(0.12 * self.s - otm, 0.07 * self.s)) * self.multiplier
            else:
                otm = max(self.s - self.strike_price, 0)
                return min(self.pv + max(0.12 * self.s - otm, 0.07 * self.strike_price),
                           self.strike_price) * self.multiplier
        elif self.exchange == Exchange.CFE:
            pass
        else:
            future_margin = self.s * self.contract_unit * self.margin_ratio
            if self.call_put == 'call':
                otm = max(self.strike_price - self.s, 0) * self.contract_unit
            else:
                otm = max(self.s - self.strike_price, 0) * self.contract_unit
            return (self.pv * self.contract_unit + future_margin - 0.5 * min(otm, future_margin))
