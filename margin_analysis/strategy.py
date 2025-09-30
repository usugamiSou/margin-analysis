from abc import ABC, abstractmethod
from functools import cached_property
import pandas as pd
from base import Exchange, PositionType, Variety


class Strategy(ABC):
    """组合策略基类"""
    def __init__(self, pos1: pd.Series, pos2: pd.Series):
        self._pos1, self._pos2 = self.modify_positions(pos1, pos2)

    @staticmethod
    @abstractmethod
    def modify_positions(pos1: pd.Series, pos2: pd.Series) -> tuple[pd.Series, pd.Series]:
        """调整两笔持仓头寸的顺序"""
        pass

    @staticmethod
    @abstractmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        """两笔持仓头寸是否能构成该组合策略"""
        pass

    @property
    def pos1(self) -> str:
        """第一笔持仓头寸"""
        return self._pos1['code_dir']

    @property
    def pos2(self) -> str:
        """第二笔持仓头寸"""
        return self._pos2['code_dir']

    @property
    def type(self) -> str:
        """组合策略类型"""
        return self.__class__.__name__

    @cached_property
    @abstractmethod
    def margin(self) -> float:
        """组合保证金"""
        pass

    @cached_property
    def margin_saving(self) -> float:
        """组合所节省的保证金"""
        return self._pos1['margin'] + self._pos2['margin'] - self.margin


class FuturesStrategy(Strategy):
    """期货组合基类"""
    @staticmethod
    def modify_positions(pos1: pd.Series, pos2: pd.Series) -> tuple[pd.Series, pd.Series]:
        return pos1, pos2


class OptionsStrategy(Strategy):
    """期权组合基类"""
    @staticmethod
    def modify_positions(pos1: pd.Series, pos2: pd.Series) -> tuple[pd.Series, pd.Series]:
        if (
            pos1['long_short'] == 'short' and
            pos2['long_short'] == 'long'
        ):
            return pos2, pos1    # 若一多一空, 则保证后者为空
        elif (
            pos1['long_short'] == pos2['long_short'] and
            pos1['call_put'] == 'call' and
            pos2['call_put'] == 'put'
        ):
            return pos2, pos1    # 空头一看涨一看跌, 保证后者为看涨
        else:
            return pos1, pos2


class FutureOptionStrategy(Strategy):
    """期货期权组合基类"""
    @staticmethod
    def modify_positions(pos1: pd.Series, pos2: pd.Series) -> tuple[pd.Series, pd.Series]:
        if pos1['type'] == PositionType.Option:
            return pos2, pos1    # 保证pos1为期货, pos2为期权
        else:
            return pos1, pos2


class FutureLockPosition(FuturesStrategy):
    """期货对锁组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['code'] and
            pos1['long_short'] != pos2['long_short'] and
            exchange in {Exchange.CZCE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return max(self._pos1['margin'], self._pos2['margin'])


class CalendarSpread(FuturesStrategy):
    """期货跨期组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['variety'] == pos2['variety'] and
            pos1['code'] != pos2['code'] and
            pos1['long_short'] != pos2['long_short'] and
            exchange in {Exchange.CZCE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return max(self._pos1['margin'], self._pos2['margin'])


class InterCommoditySpread(FuturesStrategy):
    """期货跨品种组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            Variety.is_commodity_pair(pos1['variety'], pos2['variety'], exchange) and
            pos1['long_short'] != pos2['long_short'] and
            exchange in {Exchange.CZCE, Exchange.DCE}
        )

    @cached_property
    def margin(self) -> float:
        return max(self._pos1['margin'], self._pos2['margin'])


class BullCallSpread(OptionsStrategy):
    """牛市看涨价差组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['option_mark_code'] == pos2['option_mark_code'] and
            pos1['last_tradedate'] == pos2['last_tradedate'] and
            pos1['long_short'] != pos2['long_short'] and    # pos1 多, pos2 空
            pos1['call_put'] == 'call' and
            pos2['call_put'] == 'call' and
            pos1['strike_price'] - pos2['strike_price'] < -1e-6 and
            exchange in {Exchange.SSE, Exchange.SZSE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        if self._pos1['exchange'] in {Exchange.SSE, Exchange.SZSE}:
            return 0.0
        else:
            return self._pos2['margin'] * 0.2


class BearCallSpread(OptionsStrategy):
    """熊市看涨价差组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['option_mark_code'] == pos2['option_mark_code'] and
            pos1['last_tradedate'] == pos2['last_tradedate'] and
            pos1['long_short'] != pos2['long_short'] and    # pos1 多, pos2 空
            pos1['call_put'] == 'call' and
            pos2['call_put'] == 'call' and
            pos1['strike_price'] - pos2['strike_price'] > 1e-6 and
            exchange in {Exchange.SSE, Exchange.SZSE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return (self._pos1['strike_price'] - self._pos2['strike_price']) * self._pos1['multiplier']


class BullPutSpread(OptionsStrategy):
    """牛市看跌价差组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['option_mark_code'] == pos2['option_mark_code'] and
            pos1['last_tradedate'] == pos2['last_tradedate'] and
            pos1['long_short'] != pos2['long_short'] and    # pos1 多, pos2 空
            pos1['call_put'] == 'put' and
            pos2['call_put'] == 'put' and
            pos1['strike_price'] - pos2['strike_price'] < -1e-6 and
            exchange in {Exchange.SSE, Exchange.SZSE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return (self._pos2['strike_price'] - self._pos1['strike_price']) * self._pos2['multiplier']


class BearPutSpread(OptionsStrategy):
    """熊市看跌价差组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['option_mark_code'] == pos2['option_mark_code'] and
            pos1['last_tradedate'] == pos2['last_tradedate'] and
            pos1['long_short'] != pos2['long_short'] and    # pos1 多, pos2 空
            pos1['call_put'] == 'put' and
            pos2['call_put'] == 'put' and
            pos1['strike_price'] - pos2['strike_price'] > 1e-6 and
            exchange in {Exchange.SSE, Exchange.SZSE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        if self._pos1['exchange'] in {Exchange.SSE, Exchange.SZSE}:
            return 0.0
        else:
            return self._pos2['margin'] * 0.2


class Straddle(OptionsStrategy):
    """跨式组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['option_mark_code'] == pos2['option_mark_code'] and
            pos1['last_tradedate'] == pos2['last_tradedate'] and
            pos1['long_short'] == 'short' and
            pos2['long_short'] == 'short' and
            pos1['call_put'] != pos2['call_put'] and    # pos1 看跌, pos2 看涨
            abs(pos1['strike_price'] - pos2['strike_price']) < 1e-6 and
            exchange in {Exchange.SSE, Exchange.SZSE, Exchange.CZCE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return self.calc_margin(self._pos1, self._pos2)

    @staticmethod
    def calc_margin(pos1: pd.Series, pos2: pd.Series) -> float:
        if pos1['margin'] - pos2['margin'] > 1e-6:
            pos_higher, pos_lower = pos1, pos2
        elif pos1['margin'] - pos2['margin'] < -1e-6:
            pos_higher, pos_lower = pos2, pos1
        else:
            if pos1['close_price'] - pos2['close_price'] > 1e-6:
                pos_higher, pos_lower = pos1, pos2
            else:
                pos_higher, pos_lower = pos2, pos1
        return pos_higher['margin'] + pos_lower['close_price'] * pos_lower['multiplier']


class Strangle(OptionsStrategy):
    """宽跨式组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['option_mark_code'] == pos2['option_mark_code'] and
            pos1['last_tradedate'] == pos2['last_tradedate'] and
            pos1['long_short'] == 'short' and
            pos2['long_short'] == 'short' and
            pos1['call_put'] != pos2['call_put'] and    # pos1 看跌, pos2 看涨
            pos1['strike_price'] - pos2['strike_price'] < -1e-6 and
            exchange in {Exchange.SSE, Exchange.SZSE, Exchange.CZCE, Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return Straddle.calc_margin(self._pos1, self._pos2)


class OptionLockPosition(OptionsStrategy):
    """期权对锁组合"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['code'] and
            pos1['long_short'] != pos2['long_short'] and
            exchange in {Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return self._pos2['margin'] * 0.2


class AutoHedging(OptionsStrategy):
    """期权自动对冲"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['code'] and
            pos1['long_short'] != pos2['long_short'] and
            exchange in {Exchange.SSE, Exchange.SZSE} and
            is_close
        )

    @cached_property
    def margin(self) -> float:
        return 0.0


class CoveredCall(FutureOptionStrategy):
    """备兑看涨组合 (看涨期权空头 + 期货多头)"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['option_mark_code'] and
            pos1['long_short'] == 'long' and
            pos2['long_short'] == 'short' and
            pos2['call_put'] == 'call' and
            exchange in {Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return self._pos1['margin'] + self._pos2['close_price'] * self._pos2['multiplier']


class CoveredPut(FutureOptionStrategy):
    """备兑看跌组合 (看跌期权空头 + 期货空头)"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['option_mark_code'] and
            pos1['long_short'] == 'short' and
            pos2['long_short'] == 'short' and
            pos2['call_put'] == 'put' and
            exchange in {Exchange.DCE, Exchange.GFEX}
        )

    @cached_property
    def margin(self) -> float:
        return self._pos1['margin'] + self._pos2['close_price'] * self._pos2['multiplier']


class ProtectiveCall(FutureOptionStrategy):
    """保护性看涨组合 (看涨期权多头 + 期货空头)"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['option_mark_code'] and
            pos1['long_short'] == 'short' and
            pos2['long_short'] == 'long' and
            pos2['call_put'] == 'call' and
            exchange == Exchange.DCE
        )

    @cached_property
    def margin(self) -> float:
        return self._pos1['margin'] * 0.8


class ProtectivePut(FutureOptionStrategy):
    """保护性看跌组合 (看跌期权多头 + 期货多头)"""
    @staticmethod
    def is_valid(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> bool:
        exchange = pos1['exchange']
        return (
            pos1['code'] == pos2['option_mark_code'] and
            pos1['long_short'] == 'long' and
            pos2['long_short'] == 'long' and
            pos2['call_put'] == 'put' and
            exchange == Exchange.DCE
        )

    @cached_property
    def margin(self) -> float:
        return self._pos1['margin'] * 0.8


class StrategyAnalyzer(ABC):
    """组合策略分析器基类"""
    def __init__(self, pos1: pd.Series, pos2: pd.Series, is_close: bool):
        self.pos1 = pos1
        self.pos2 = pos2
        self.is_close = is_close

    @abstractmethod
    def analyze(self) -> Strategy | None:
        """分析两笔持仓头寸所能构成的组合策略"""
        pass


class FuturesStrategyAnalyzer(StrategyAnalyzer):
    """期货组合策略分析器"""
    def analyze(self) -> Strategy | None:
        self.pos1, self.pos2 = FuturesStrategy.modify_positions(self.pos1, self.pos2)
        for strategy in FuturesStrategy.__subclasses__():
            if strategy.is_valid(self.pos1, self.pos2, self.is_close):
                return strategy(self.pos1, self.pos2)
        return None


class OptionsStrategyAnalyzer(StrategyAnalyzer):
    """期权组合策略分析器"""
    def analyze(self) -> Strategy | None:
        self.pos1, self.pos2 = OptionsStrategy.modify_positions(self.pos1, self.pos2)
        for strategy in OptionsStrategy.__subclasses__():
            if strategy.is_valid(self.pos1, self.pos2, self.is_close):
                return strategy(self.pos1, self.pos2)
        return None


class FutureOptionStrategyAnalyzer(StrategyAnalyzer):
    """期货期权组合策略分析器"""
    def analyze(self) -> Strategy | None:
        self.pos1, self.pos2 = FutureOptionStrategy.modify_positions(self.pos1, self.pos2)
        for strategy in FutureOptionStrategy.__subclasses__():
            if strategy.is_valid(self.pos1, self.pos2, self.is_close):
                return strategy(self.pos1, self.pos2)
        return None


class StrategyAnalyzerFactory:
    """组合策略分析器工厂类"""
    @staticmethod
    def create(pos1: pd.Series, pos2: pd.Series, is_close: bool) -> StrategyAnalyzer:
        """根据两笔持仓头寸类型, 创建对应的组合策略分析器"""
        analyzer_map = {
            (PositionType.Future, PositionType.Future): FuturesStrategyAnalyzer,
            (PositionType.Option, PositionType.Option): OptionsStrategyAnalyzer,
            (PositionType.Future, PositionType.Option): FutureOptionStrategyAnalyzer,
            (PositionType.Option, PositionType.Future): FutureOptionStrategyAnalyzer,
        }
        if (pos1['type'], pos2['type']) in analyzer_map:
            analyzer = analyzer_map.get((pos1['type'], pos2['type']))
            return analyzer(pos1, pos2, is_close)
        else:
            raise ValueError('Invalid position types.')
