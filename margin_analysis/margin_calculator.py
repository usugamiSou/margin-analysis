import pandas as pd
from base import PositionType, Exchange


class MarginCalculator:
    def __init__(self, pos: pd.Series):
        for key, value in pos.dropna().items():
            setattr(self, key, value)

    def calc(self, **kwargs) -> float:
        if self.type == PositionType.Future:
            return self.calc_future(**kwargs)
        elif self.type == PositionType.Option:
            return self.calc_option(**kwargs)

    def calc_future(self, **kwargs) -> float:
        """
        计算期货持仓保证金

        Args:
            **kwargs: 可选参数, 用于更新持仓属性, 如 close_price
        Returns:
            float: 保证金金额
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self.close_price * self.multiplier * self.margin_ratio

    def calc_option(self, **kwargs) -> float:
        """
        计算期权持仓保证金

        Args:
            **kwargs: 可选参数, 用于更新持仓属性, 如 udl_price, close_price
        Returns:
            float: 保证金金额
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        if self.long_short == 'long':
            return 0.0

        if self.call_put == 'call':
            otm = max(self.strike_price - self.udl_price, 0)
        elif self.call_put == 'put':
            otm = max(self.udl_price - self.strike_price, 0)

        if self.exchange in {Exchange.SSE, Exchange.SZSE}:
            if self.call_put == 'call':
                return self.multiplier * (self.close_price + max(
                    0.12 * self.udl_price - otm,
                    0.07 * self.udl_price))
            elif self.call_put == 'put':
                return self.multiplier * min(
                    self.close_price + max(
                        0.12 * self.udl_price - otm,
                        0.07 * self.strike_price),
                    self.strike_price)

        elif self.exchange == Exchange.CFFEX:
            min_safety_factor = 0.5
            if self.call_put == 'call':
                return self.multiplier * (self.close_price + max(
                    self.udl_price * self.margin_ratio - otm,
                    min_safety_factor * self.udl_price * self.margin_ratio))
            elif self.call_put == 'put':
                return self.multiplier * (self.close_price + max(
                    self.udl_price * self.margin_ratio - otm,
                    min_safety_factor * self.strike_price * self.margin_ratio))

        else:
            udl_margin = self.udl_price * self.margin_ratio
            return self.multiplier * (
                self.close_price + udl_margin - 0.5 * min(otm, udl_margin))
