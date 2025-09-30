import numpy as np
import pandas as pd
from base import PositionType, Exchange


class MarginCalculator:
    def __init__(self, pos: pd.Series, margin_ratio_df: pd.DataFrame):
        for key, value in pos.dropna().items():
            setattr(self, key, value)
        self.margin_ratio = margin_ratio_df['MarginRatio'].get(self.variety)

    def calc(self, price=None):
        if self.type == PositionType.Future:
            return self.calc_future()
        elif self.type == PositionType.Option:
            return self.calc_option()

    def calc_future(self, price=None):
        if price is not None:
            self.close_price = price
        return self.close_price * self.multiplier * self.margin_ratio

    def calc_option(self, price=None):
        if self.long_short == 'long':
            return 0
        if price is not None:
            self.udl_price = price
        if self.exchange in {Exchange.SSE, Exchange.SZSE}:
            if self.call_put == 'call':
                otm = max(self.strike_price - self.udl_price, 0)
                return self.multiplier * (self.close_price + max(
                    0.12 * self.udl_price - otm,
                    0.07 * self.udl_price))
            else:
                otm = max(self.udl_price - self.strike_price, 0)
                return self.multiplier * min(
                    self.close_price + max(
                        0.12 * self.udl_price - otm,
                        0.07 * self.strike_price),
                    self.strike_price)

        elif self.exchange == Exchange.CFFEX:
            min_safety_factor = 0.5
            if self.call_put == 'call':
                otm = max(self.strike_price - self.udl_price, 0)
                return self.multiplier * (self.close_price + max(
                    self.udl_price * self.margin_ratio - otm,
                    min_safety_factor * self.udl_price * self.margin_ratio))
            else:
                otm = max(self.udl_price - self.strike_price, 0)
                return self.multiplier * (self.close_price + max(
                    self.udl_price * self.margin_ratio - otm,
                    min_safety_factor * self.strike_price * self.margin_ratio))

        else:
            future_margin = self.udl_price * self.margin_ratio
            if self.call_put == 'call':
                otm = max(self.strike_price - self.udl_price, 0)
            else:
                otm = max(self.udl_price - self.strike_price, 0)
            return self.multiplier * (
                self.close_price + future_margin - 0.5 * min(otm, future_margin))
