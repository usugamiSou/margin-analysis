from enum import Enum, unique, auto
import pandas as pd
from base import Exchange, PositionType, FutureVariety


@unique
class StrategyType(Enum):
    # Future + Future
    FutureLockPosition = auto()    # 期货对锁
    CalendarSpread = auto()    # 期货跨期
    InterCommoditySpread = auto()    # 期货跨品种
    # Option + Option
    BullCallSpread = auto()    # 牛市看涨价差
    BearCallSpread = auto()    # 熊市看涨价差
    BullPutSpread = auto()    # 牛市看跌价差
    BearPutSpread = auto()    # 熊市看跌价差
    Straddle = auto()    # 跨式
    Strangle = auto()    # 宽跨式
    OptionLockPosition = auto()    # 期权对锁
    AutoHedging = auto()    # 期权自动对冲
    # Future + Option
    CoveredCall = auto()    # 看涨期权空头 + 期货多头
    CoveredPut = auto()    # 看跌期权空头 + 期货空头
    ProtectiveCall = auto()    # 看涨期权多头 + 期货空头
    ProtectivePut = auto()    # 看跌期权多头 + 期货多头
    # Invalid
    Invalid = auto()


class StrategyAnalyzer:
    """分析两手持仓可构成的组合策略, 并计算其组合保证金"""
    def __init__(self, pos1: pd.Series, pos2: pd.Series, is_close: bool):
        self.pos1 = pos1
        self.pos2 = pos2
        self.is_close = is_close
        self.exchange = pos1['exchange']
        self.strategy = StrategyType.Invalid
        self.margin = pos1['margin'] + pos2['margin']
        self.margin_saving = 0

    def _update_margin(self, margin_strategy: float) -> None:
        self.margin_saving = self.margin - margin_strategy
        self.margin = margin_strategy

    @classmethod
    def create_analyzer(cls, pos1: pd.Series, pos2: pd.Series,
                        is_close: bool) -> 'StrategyAnalyzer':
        if pos1['type'] == PositionType.Future and pos2['type'] == PositionType.Future:
            return FuturesStrategyAnalyzer(pos1, pos2, is_close)
        elif pos1['type'] == PositionType.Option and pos2['type'] == PositionType.Option:
            return OptionsStrategyAnalyzer(pos1, pos2, is_close)
        else:
            return FutureOptionStrategyAnalyzer(pos1, pos2, is_close)


class FuturesStrategyAnalyzer(StrategyAnalyzer):
    def analyze(self) -> dict:
        criteria_public = (
            self.pos1['long_short'] != self.pos2['long_short']
        )
        if criteria_public:
            analysis_funcs = [
                self._is_future_lock_position(),
                self._is_calender_spread(),
                self._is_inter_commodity_spread()
            ]
            for analysis_func in analysis_funcs:
               if analysis_func:
                    break
        return {
            'strategy': self.strategy,
            'margin': self.margin,
            'margin_saving': self.margin_saving
        }

    def _is_future_lock_position(self) -> bool:
        """期货对锁"""
        criteria = (
            self.exchange in (Exchange.CZCE, Exchange.DCE, Exchange.GFEX) and
            self.pos1['code_original'] == self.pos2['code_original']
        )
        if criteria:
            self.strategy = StrategyType.FutureLockPosition
            margin_strategy = max(self.pos1['margin'], self.pos2['margin'])
            self._update_margin(margin_strategy)
        return criteria

    def _is_calender_spread(self) -> bool:
        """期货跨期"""
        criteria = (
            self.exchange in (Exchange.CZCE, Exchange.DCE, Exchange.GFEX) and
            self.pos1['variety'] == self.pos2['variety'] and
            self.pos1['code_original'] != self.pos2['code_original']
        )
        if criteria:
            self.strategy = StrategyType.CalendarSpread
            margin_strategy = max(self.pos1['margin'], self.pos2['margin'])
            self._update_margin(margin_strategy)
        return criteria

    def _is_inter_commodity_spread(self) -> bool:
        """期货跨品种"""
        criteria = (
            self.exchange in (Exchange.CZCE, Exchange.DCE) and
            self.pos1['variety'] != self.pos2['variety'] and
            FutureVariety.is_commodity_pair(self.pos1['variety'], self.pos2['variety'])
        )
        if criteria:
            self.strategy = StrategyType.InterCommoditySpread
            margin_strategy = max(self.pos1['margin'], self.pos2['margin'])
            self._upate_margin(margin_strategy)
        return criteria


class OptionsStrategyAnalyzer(StrategyAnalyzer):
    def analyze(self) -> dict:
        criteria_public = (
            self.pos1['option_mark_code'] == self.pos2['option_mark_code'] and
            self.pos1['last_tradedate'] == self.pos2['last_tradedate'] and
            'short' in (self.pos1['long_short'], self.pos2['long_short'])
        )
        if criteria_public:
            if self.pos1['long_short'] == 'short' and self.pos2['long_short'] == 'long':
                self.pos1, self.pos2 = self.pos2, self.pos1
            elif (
                self.pos1['long_short'] == self.pos2['long_short'] and
                self.pos1['call_put'] == 'call' and
                self.pos2['call_put'] == 'put'
            ):
                self.pos1, self.pos2 = self.pos2, self.pos1
            analysis_funcs = [
                self._is_bull_call_spread(),
                self._is_bear_call_spread(),
                self._is_bull_put_spread(),
                self._is_bear_put_spread(),
                self._is_strangle(),
                self._is_option_lock_position()
            ]
            for analysis_func in analysis_funcs:
                if analysis_func:
                    break
        return {
            'strategy': self.strategy,
            'margin': self.margin,
            'margin_saving': self.margin_saving
        }

    def _is_bull_call_spread(self) -> bool:
        """牛市看涨价差"""
        criteria = (
            self.exchange in (Exchange.SH, Exchange.SZ, Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] != self.pos2['long_short'] and
            self.pos1['call_put'] == 'call' and
            self.pos2['call_put'] == 'call' and
            self.pos1['strike_price'] - self.pos2['strike_price'] < -1e-6
        )
        if criteria:
            self.strategy = StrategyType.BullCallSpread
            if self.exchange in (Exchange.SH, Exchange.SZ):
                margin_strategy = 0
            else:
                margin_strategy = self.pos2['margin'] * 0.2
            self._update_margin(margin_strategy)

    def _is_bear_call_spread(self) -> bool:
        """熊市看涨价差"""
        criteria = (
            self.exchange in (Exchange.SH, Exchange.SZ, Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] != self.pos2['long_short'] and
            self.pos1['call_put'] == 'call' and
            self.pos2['call_put'] == 'call' and
            self.pos1['strike_price'] - self.pos2['strike_price'] > 1e-6
        )
        if criteria:
            self.strategy = StrategyType.BearCallSpread
            if self.exchange in (Exchange.SH, Exchange.SZ):
                margin_strategy = ((self.pos1['strike_price'] - self.pos2['strike_price'])
                                   * self.pos1['multiplier'])
            else:
                margin_strategy = min(
                        (self.pos1['strike_price'] - self.pos2['strike_price']) * self.pos1['contract_unit'],
                        self.pos2['margin']
                    )
            self._update_margin(margin_strategy)
        return criteria

    def _is_bull_put_spread(self) -> bool:
        """牛市看跌价差"""
        criteria = (
            self.exchange in (Exchange.SH, Exchange.SZ, Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] != self.pos2['long_short'] and
            self.pos1['call_put'] == 'put' and
            self.pos2['call_put'] == 'put' and
            self.pos1['strike_price'] - self.pos2['strike_price'] < -1e-6
        )
        if criteria:
            self.strategy = StrategyType.BullPutSpread
            if self.exchange in (Exchange.SH, Exchange.SZ):
                margin_strategy = ((self.pos2['strike_price'] - self.pos1['strike_price'])
                                   * self.pos2['multiplier'])
            else:
                margin_strategy = min(
                    (self.pos2['strike_price'] - self.pos1['strike_price']) * self.pos2['contract_unit'],
                    self.pos2['margin']
                )
            self._update_margin(margin_strategy)
        return criteria

    def _is_bear_put_spread(self) -> bool:
        """熊市看跌价差"""
        criteria = (
            self.exchange in (Exchange.SH, Exchange.SZ, Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] != self.pos2['long_short'] and
            self.pos1['call_put'] == 'put' and
            self.pos2['call_put'] == 'put' and
            self.pos1['strike_price'] - self.pos2['strike_price'] > 1e-6
        )
        if criteria:
            self.strategy = StrategyType.BearPutSpread
            if self.exchange in (Exchange.SH, Exchange.SZ):
                margin_strategy = 0
            else:
                margin_strategy = self.pos2['margin'] * 0.2
            self._update_margin(margin_strategy)
        return criteria

    def _is_strangle(self) -> bool:
        """跨式、宽跨式"""
        criteria = (
            self.exchange in (Exchange.SH, Exchange.SZ, Exchange.CZCE, Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] == self.pos2['long_short'] and
            self.pos1['call_put'] != self.pos2['call_put'] and
            self.pos1['strike_price'] - self.pos2['strike_price'] < 1e-6
        )
        if criteria:
            if self.pos1['strike_price'] - self.pos2['strike_price'] > -1e-6:    # 跨式
                self.strategy = StrategyType.Straddle
            else:    # 宽跨式
                self.strategy = StrategyType.Strangle
            margin_strategy = self._calc_margin_strangle()
            self._update_margin(margin_strategy)
        return criteria

    def _is_option_lock_position(self) -> bool:
        """期权对锁、自动对冲"""
        criteria = (
            self.exchange in (Exchange.SH, Exchange.SZ, Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] != self.pos2['long_short'] and
            self.pos1['call_put'] == self.pos2['call_put'] and
            abs(self.pos1['strike_price'] - self.pos2['strike_price']) < 1e-6
        )
        if criteria:
            if self.exchange in (Exchange.SH, Exchange.SZ):
                if self.is_close:    # 期权自动对冲
                    self.strategy = StrategyType.AutoHedging
                    margin_strategy = 0
                    self._update_margin(margin_strategy)

                    # 上交所、深交所盘后自动对冲, 不属于持仓策略, 在优化过程中添加惩罚项以降低优先级
                    penalty = 10
                    self.margin_saving -= penalty

            else:    # 期权对锁
                self.strategy = StrategyType.OptionLockPosition
                margin_strategy = self.pos2['margin'] * 0.2
                self._update_margin(margin_strategy)
        return criteria

    def _calc_margin_strangle(self) -> float:
        """计算跨式、宽跨式组合保证金"""
        if self.pos1['margin'] - self.pos2['margin'] < -1e-6:
            pos_higher, pos_lower = self.pos2, self.pos1
        elif self.pos1['margin'] - self.pos2['margin'] > 1e-6:
            pos_higher, pos_lower = self.pos1, self.pos2
        else:
            if self.pos1['pv'] - self.pos2['pv'] < 1e-6:
                pos_higher, pos_lower = self.pos2, self.pos1
            else:
                pos_higher, pos_lower = self.pos1, self.pos2
        if self.exchange in (Exchange.SH, Exchange.SZ):
            return pos_higher['margin'] + pos_lower['pv'] * pos_lower['multiplier']
        else:
            return pos_higher['margin'] + pos_lower['pv'] * pos_lower['contract_unit']


class FutureOptionStrategyAnalyzer(StrategyAnalyzer):
    def analyze(self) -> dict:
        if self.pos1['type'] == PositionType.Option and self.pos2['type'] == PositionType.Future:
            self.pos1, self.pos2 = self.pos2, self.pos1
        criteria_public = (
            self.pos2['option_mark_code'] == self.pos1['code_original']
        )
        if criteria_public:
            analysis_funcs = [
                self._is_covered_call(),
                self._is_covered_put(),
                self._is_protective_call(),
                self._is_protective_put(),
            ]
            for analysis_func in analysis_funcs:
                if analysis_func:
                    break
        return {
            'strategy': self.strategy,
            'margin': self.margin,
            'margin_saving': self.margin_saving
        }

    def _is_covered_call(self) -> bool:
        """看涨期权空头 + 期货多头"""
        criteria = (
            self.exchange in (Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] == 'long' and
            self.pos2['long_short'] == 'short' and
            self.pos2['call_put'] == 'call'
        )
        if criteria:
            self.strategy = StrategyType.CoveredCall
            margin_strategy = self.pos1['margin'] + self.pos2['pv'] * self.pos2['contract_unit']
            self._update_margin(margin_strategy)
        return criteria

    def _is_covered_put(self) -> bool:
        """看跌期权空头 + 期货空头"""
        criteria = (
            self.exchange in (Exchange.DCE, Exchange.GFEX) and
            self.pos1['long_short'] == 'short' and
            self.pos2['long_short'] == 'short' and
            self.pos2['call_put'] == 'put'
        )
        if criteria:
            self.strategy = StrategyType.CoveredPut
            margin_strategy = self.pos1['margin'] + self.pos2['pv'] * self.pos2['contract_unit']
            self._update_margin(margin_strategy)
        return criteria

    def _is_protective_call(self) -> bool:
        """看涨期权多头 + 期货空头"""
        criteria = (
            self.exchange == Exchange.DCE and
            self.pos1['long_short'] == 'short' and
            self.pos2['long_short'] == 'long' and
            self.pos2['call_put'] == 'call'
        )
        if criteria:
            self.strategy = StrategyType.ProtectiveCall
            margin_strategy = self.pos1['margin'] * 0.8
            self._update_margin(margin_strategy)
        return criteria

    def _is_protective_put(self) -> bool:
        """看跌期权多头 + 期货多头"""
        criteria = (
            self.exchange == Exchange.DCE and
            self.pos1['long_short'] == 'long' and
            self.pos2['long_short'] == 'long' and
            self.pos2['call_put'] == 'put'
        )
        if criteria:
            self.strategy = StrategyType.ProtectivePut
            margin_strategy = self.pos1['margin'] * 0.8
            self._update_margin(margin_strategy)
        return criteria
