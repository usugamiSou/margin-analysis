import re
import pandas as pd
from base import Exchange, PositionType, FutureVariety
from margin_calculator import MarginCalculator


class HoldingDataProcessor:
    @staticmethod
    def preprocess_holding(holding: pd.DataFrame,
                           futures_data: pd.DataFrame | list[pd.DataFrame],
                           options_data: pd.DataFrame | list[pd.DataFrame]) -> pd.DataFrame:
        """
        预处理持仓数据, 拆分多空单独持仓, 整合市场数据

        :param holding: 持仓数据
        :param futures_data: 期货市场数据
        :param etf_options_data: ETF期权市场数据
        :param commodity_options_data: 商品期权市场数据
        :returns: 预处理后的持仓数据
        """
        holding.rename(columns={'代码': 'code_original'}, inplace=True)
        holding[['exchange', 'type', 'variety']] = holding['code_original'].apply(
            lambda x: pd.Series(HoldingDataProcessor._find_position_basic_info(x)))

        holding_long = holding[holding['多头持仓'] > 0].drop(columns=['空头持仓'])
        holding_long['long_short'] = 'long'
        holding_long.rename(columns={'多头持仓': 'quantity'}, inplace=True)
        holding_long['code'] = holding_long['code_original'] + '.L'
        holding_short = holding[holding['空头持仓'] < 0].drop(columns=['多头持仓'])
        holding_short['long_short'] = 'short'
        holding_short.rename(columns={'空头持仓': 'quantity'}, inplace=True)
        holding_short['quantity'] *= -1
        holding_short['code'] = holding_long['code_original'] + '.S'
        holding = pd.concat([holding_long, holding_short], ignore_index=True)

        holding_futures = holding[holding['type'] == PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures = HoldingDataProcessor._supplement_futures_data(
                holding_futures, futures_data)

        holding_options = holding[holding['type'] == PositionType.Option].copy()
        if not holding_options.empty:
            holding_options = HoldingDataProcessor._supplement_options_data(
                holding_options, options_data)

        holding = pd.concat([holding_futures, holding_options], ignore_index=True)
        return holding

    @staticmethod
    def _supplement_futures_data(holding_futures: pd.DataFrame,
                                 futures_data: pd.DataFrame | list[pd.DataFrame]) -> pd.DataFrame:
        """补充期货持仓的市场数据"""
        if isinstance(futures_data, pd.DataFrame):
            futures_data = [futures_data]
        futures_data = pd.concat(futures_data, ignore_index=True)
        if 'margin' not in futures_data.columns:
            futures_data['margin'] = 10000    # TODO: MarginCalculator
        holding_futures = pd.merge(holding_futures, futures_data,
                                   left_on=['code_original'], right_on=['future_code'], how='left')
        return holding_futures

    @staticmethod
    def _supplement_options_data(holding_options: pd.DataFrame,
                                 options_data: pd.DataFrame | list[pd.DataFrame]) -> pd.DataFrame:
        """补充期权持仓的市场数据"""
        if isinstance(options_data, pd.DataFrame):
            options_data = [options_data]
        options_data = pd.concat(options_data, ignore_index=True)
        if 'margin' not in options_data.columns:
            options_data['margin'] = 10000    # TODO: MarginCalculator
        holding_options = pd.merge(holding_options, options_data,
                                   left_on=['code_original'], right_on=['option_code'], how='left')
        holding_options['margin'] *= holding_options['long_short'].map({'long': 0, 'short': 1})

        return holding_options

    @staticmethod
    def _find_position_basic_info(code: str) -> dict:
        """根据持仓代码判断交易所和持仓类型"""
        code, exchange_code = code.split('.')

        match exchange_code:
            case 'CCFX' | 'CFE':
                exchange = Exchange.CFE
                match_future = re.match(r'^(IF|IC|IM|IH)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = FutureVariety(match_future.group(1))
                else:
                    match_option = re.match(r'^(IO|MO|HO)[0-9]{4}.+$', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = {
                            'IO': FutureVariety.IF,
                            'MO': FutureVariety.IM,
                            'HO': FutureVariety.IH
                        }.get(match_option.group(1))

            case 'XSHG' | 'SH':
                exchange = Exchange.SH
                match_option1 = re.match(r'^1[0-9]{7}$', code)
                match_option2 = re.match(r'^[0-9]{6}(C|P)[0-9]{4}M[0-9]+.$', code)
                if match_option1 or match_option2:
                    position_type = PositionType.Option
                    variety = FutureVariety.ETF

            case 'XSHE' | 'SZ':
                exchange = Exchange.SZ
                match_option1 = re.match(r'^9[0-9]{7}$', code)
                match_option2 = re.match(r'^[0-9]{6}(C|P)[0-9]{4}M[0-9]+.$', code)
                if match_option or match_option2:
                    position_type = PositionType.Option
                    variety = FutureVariety.ETF

            case 'XSGE' | 'SHFE':
                exchange = Exchange.SHFE
                match_future = re.match(r'^([A-Za-z]+)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = FutureVariety(match_future.group(1).upper())
                else:
                    match_option = re.match(r'^([A-Za-z]+])[0-9]{4}.+', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = FutureVariety(match_option.group(1).upper())

            case 'XZCE' | 'CZCE':
                exchange = Exchange.CZCE
                match_future = re.match(r'^([A-Za-z]+)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = FutureVariety(match_future.group(1).upper())
                else:
                    match_option = re.match(r'^([A-Za-z]+])[0-9]{4}.+', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = FutureVariety(match_option.group(1).upper())

            case 'XDCE' | 'DCE':
                exchange = Exchange.DCE
                match_future = re.match(r'^([A-Za-z]+)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = FutureVariety(match_future.group(1).upper())
                else:
                    match_option = re.match(r'^([A-Za-z]+])[0-9]{4}.+$', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = FutureVariety(match_option.group(1).upper())

            case 'GFEX':
                exchange = Exchange.GFEX
                match_future = re.match(r'^([A-Za-z]+)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = FutureVariety(match_future.group(1).upper())
                else:
                    match_option = re.match(r'^([A-Za-z]+])[0-9]{4}.+$', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = FutureVariety(match_option.group(1).upper())

            case _:
                raise ValueError('Invalid exchange code.')

        return {
            'exchange': exchange,
            'position_type': position_type,
            'variety': variety
        }
