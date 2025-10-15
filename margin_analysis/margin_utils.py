import numpy as np
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

    def calc_future_vec(self, close_price_vec: np.ndarray) -> np.ndarray:
        """
        给定期货价格情形, 计算期货持仓保证金 (支持向量化计算)

        Args:
            close_price (ndarray): 期货价格情形, shape: (*scenarios_dim)

        Returns:
            ndarray: 各情形下的保证金金额, shape: (*scenarios_dim)
        """
        calc_vec = np.vectorize(lambda p: self.calc_future(close_price=p))
        return calc_vec(close_price_vec)

    def calc_option_vec(self, udl_price_vec: np.ndarray,
                        close_price_vec: np.ndarray) -> np.ndarray:
        """
        给定标的价格与期权价格情形, 计算期权持仓保证金 (支持向量化计算)

        Args:
            udl_price_vec (ndarray): 标的价格情形, shape: (*scenarios_dim)
            close_price_vec (ndarray): 期权价格情形, shape: (*scenarios_dim)

        Returns:
            ndarray: 各情形下的保证金金额, shape: (*scenarios_dim)
        """
        calc_vec = np.vectorize(lambda s, p: self.calc_option(udl_price=s, close_price=p))
        return calc_vec(udl_price_vec, close_price_vec)


def process_larger_side_margin(holding_account: pd.DataFrame) -> pd.DataFrame:
    """处理中金所、上期所单个账号持仓的单向大边保证金"""
    exchange = holding_account['exchange'].iloc[0]
    if exchange not in {Exchange.CFFEX, Exchange.SHFE}:
        return holding_account

    holding_futures = holding_account[holding_account['type'] == PositionType.Future]
    if holding_futures.empty:
        return holding_account

    if exchange == Exchange.CFFEX:
        # CFFEX: 期货对锁、跨期、跨品种
        larger_side = holding_futures.groupby('long_short')['total_margin'].sum().idxmax()
        mask = (
            (holding_account['type'] == PositionType.Future) &
            (holding_account['long_short'] != larger_side)
        )
        holding_account.loc[mask, ['margin', 'total_margin']] = 0
    else:
        # SHFE: 期货对锁、跨期
        for variety, holding_variety in holding_futures.groupby('variety'):
            larger_side = holding_variety.groupby('long_short')['total_margin'].sum().idxmax()
            mask = (
                (holding_account['type'] == PositionType.Future) &
                (holding_account['variety'] == variety) &
                (holding_account['long_short'] != larger_side)
            )
            holding_account.loc[mask, ['margin', 'total_margin']] = 0
    return holding_account


def calc_larger_side_margin_vec(holding_account: pd.DataFrame,
                                margins: np.ndarray) -> np.ndarray:
    """
    给定一系列头寸保证金情形, 考虑单向大边保证金, 计算账号持仓总保证金 (支持向量化计算)

    Args:
        holding_account (DataFrame): 单个账号的持仓数据
        margins (ndarray): 头寸保证金情形, shape: (n_pos, *scenarios_dim)

    Returns:
        ndarray: 账号持仓总保证金, shape: (*scenarios_dim)
    """
    total_margin = margins.sum(axis=0)
    exchange = holding_account['exchange'].iloc[0]
    if exchange not in {Exchange.CFFEX, Exchange.SHFE}:
        return total_margin

    is_future = (holding_account['type'] == PositionType.Future)
    if not is_future.any():
        return total_margin

    holding_futures = holding_account[is_future]
    margins_futures = margins[is_future.values]
    if exchange == Exchange.CFFEX:
        # CFFEX: 期货对锁、跨期、跨品种
        is_long = (holding_futures['long_short'] == 'long')
        margin_long = margins_futures[is_long.values].sum(axis=0)
        margin_short = margins_futures[~is_long.values].sum(axis=0)
        smaller_side_margin = np.minimum(margin_long, margin_short)
    else:
        # SHFE: 期货对锁、跨期
        smaller_side_margin = np.zeros_like(total_margin)
        for variety in holding_futures['variety'].unique():
            is_variety = (holding_futures['variety'] == variety)
            holding_variety = holding_futures[is_variety]
            margins_variety = margins_futures[is_variety.values]
            is_long = (holding_variety['long_short'] == 'long')
            margin_long = margins_variety[is_long.values].sum(axis=0)
            margin_short = margins_variety[~is_long.values].sum(axis=0)
            smaller_side_margin += np.minimum(margin_long, margin_short)
    return total_margin - smaller_side_margin
