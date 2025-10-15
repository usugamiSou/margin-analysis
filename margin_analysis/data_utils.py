import re
from typing import Optional
import pandas as pd
from base import Exchange, PositionType
from margin_utils import MarginCalculator, process_larger_side_margin


class DataLoader:
    @staticmethod
    def load_params(params_excel: str
                    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        margin_ratio_df = pd.read_excel(params_excel, sheet_name='marginRatio').set_index('Variety')
        supplement = pd.read_excel(params_excel, sheet_name='supplement').set_index('Account')
        cov = pd.read_excel(params_excel, sheet_name='cov').set_index('Underlying')
        mu = pd.read_excel(params_excel, sheet_name='mu').set_index('Underlying')
        return margin_ratio_df, supplement, cov, mu

    @staticmethod
    def load_account(account_excel: str) -> pd.DataFrame:
        margin_account = pd.read_excel(account_excel).dropna()
        margin_account = margin_account[['持仓帐号', '权益']]
        margin_account.rename(columns={'持仓帐号': 'account', '权益': 'equity'}, inplace=True)
        margin_account.set_index('account', inplace=True)
        return margin_account

    @staticmethod
    def load_holding(holding_excel: str) -> pd.DataFrame:
        holding = pd.read_excel(holding_excel).dropna()
        holding.sort_values(by=['持仓帐号', '代码'], ignore_index=True, inplace=True)
        return holding

    @staticmethod
    def load_market_data(market_data_csv: str, encoding: Optional[str] = None) -> pd.DataFrame:
        market_data = pd.read_csv(market_data_csv, encoding=encoding).dropna()
        return market_data


class HoldingDataProcessor:
    def __init__(self, holding: pd.DataFrame,
                 margin_ratio_df: pd.DataFrame,
                 stock_futures_data: Optional[pd.DataFrame] = None,
                 stock_options_data: Optional[pd.DataFrame] = None,
                 commodity_futures_data: Optional[pd.DataFrame] = None,
                 commodity_options_data: Optional[pd.DataFrame] = None):
        self.holding = holding.copy()
        self.margin_ratio_df = margin_ratio_df
        self.stock_futures_data = stock_futures_data
        self.stock_options_data = stock_options_data
        self.commodity_futures_data = commodity_futures_data
        self.commodity_options_data = commodity_options_data

    def process(self) -> pd.DataFrame:
        """处理持仓数据: 补充市场数据, 拆分多空方向持仓, 计算保证金"""
        self.holding.rename(columns={'代码': 'code', '持仓帐号': 'account'}, inplace=True)
        self.holding[['exchange', 'type', 'variety']] = self.holding['code'].apply(
            lambda code: pd.Series(parse_position_code(code)))

        # 补充市场数据
        holding_futures = self.holding[self.holding['type'] == PositionType.Future].copy()
        holding_options = self.holding[self.holding['type'] == PositionType.Option].copy()
        if not holding_futures.empty:
            holding_futures = self._merge_futures_data(holding_futures)
        if not holding_options.empty:
            holding_options = self._merge_options_data(holding_options)
        dfs_to_concat = [df for df in [holding_futures, holding_options] if not df.empty]
        holding = pd.concat(dfs_to_concat, ignore_index=True)

        # 拆分多空方向持仓
        holding_long = holding[holding['多头持仓'] > 0].drop(columns=['空头持仓'])
        holding_long['long_short'] = 'long'
        holding_long.rename(columns={'多头持仓': 'quantity'}, inplace=True)
        holding_long['code_dir'] = holding_long['code'] + '.L'
        holding_short = holding[holding['空头持仓'] < 0].drop(columns=['多头持仓'])
        holding_short['long_short'] = 'short'
        holding_short.rename(columns={'空头持仓': 'quantity'}, inplace=True)
        holding_short['quantity'] *= -1
        holding_short['code_dir'] = holding_short['code'] + '.S'
        dfs_to_concat = [df for df in [holding_long, holding_short] if not df.empty]
        holding = pd.concat(dfs_to_concat, ignore_index=True)

        # 计算保证金
        self.margin_ratio_df.rename(columns={'MarginRatio': 'margin_ratio'}, inplace=True)
        holding = pd.merge(holding, self.margin_ratio_df,
                           left_on='variety', right_index=True, how='left')
        holding['margin'] = holding.apply(
            lambda pos: MarginCalculator(pos).calc(), axis=1)
        holding['total_margin'] = holding['margin'] * holding['quantity']

        # 处理中金所、上期所单个账号持仓的单向大边保证金
        dfs = []
        for _, holding_account in holding.groupby('account'):
            dfs.append(process_larger_side_margin(holding_account))
        holding = pd.concat(dfs, ignore_index=True)
        return holding

    def _merge_futures_data(self, holding_futures: pd.DataFrame) -> pd.DataFrame:
        """补充期货持仓的市场数据"""
        columns = ['future_code', 'last_tradedate', 'multiplier', 'close_price']
        if self.stock_futures_data is None:
            self.stock_futures_data = pd.DataFrame(columns=columns)
        else:
            self.stock_futures_data = self.stock_futures_data[columns]
        if self.commodity_futures_data is None:
            self.commodity_futures_data = pd.DataFrame(columns=columns)
        else:
            self.commodity_futures_data.rename(columns={'contract_unit': 'multiplier'},
                                               inplace=True)
            self.commodity_futures_data = self.commodity_futures_data[columns]
        dfs_to_concat = [df for df in [self.stock_futures_data, self.commodity_futures_data]
                         if not df.empty]
        futures_data = pd.concat(dfs_to_concat, ignore_index=True)
        futures_data.rename(columns={'future_code': 'code'}, inplace=True)
        holding_futures = pd.merge(holding_futures, futures_data, on='code', how='left')
        holding_futures['udl'] = holding_futures['variety']
        return holding_futures

    def _merge_options_data(self, holding_options: pd.DataFrame) -> pd.DataFrame:
        """补充期权持仓的市场数据"""
        columns = ['option_code', 'option_mark_code', 'last_tradedate', 'call_put',
                   'strike_price', 'multiplier', 'close_price', 'udl_price',
                   'delta', 'gamma']
        if self.stock_options_data is None:
            self.stock_options_data = pd.DataFrame(columns=columns)
        else:
            self.stock_options_data = self.stock_options_data[columns]
        if self.commodity_options_data is None:
            self.commodity_options_data = pd.DataFrame(columns=columns)
        else:
            self.commodity_options_data.rename(columns={'contract_unit': 'multiplier'},
                                               inplace=True)
            self.commodity_options_data = self.commodity_options_data[columns]
        dfs_to_concat = [df for df in [self.stock_options_data, self.commodity_options_data]
                         if not df.empty]
        options_data = pd.concat(dfs_to_concat, ignore_index=True)
        options_data.rename(columns={'option_code': 'code', 'option_mark_code': 'udl'},
                            inplace=True)
        holding_options = pd.merge(holding_options, options_data, on='code', how='left')
        return holding_options


def parse_position_code(code: str) -> dict[str, str]:
    """
    解析持仓代码, 提取交易所、持仓类型和品种信息

    Args:
        code (str): 持仓代码

    Returns:
        dict: 包含交易所代码、持仓类型、品种信息的字典
    """
    try:
        code, exchange_code = code.split('.')
    except ValueError:
        raise ValueError(f'无法解析代码: {code}')

    exchange = Exchange.from_code(exchange_code)
    position_type = None
    variety = None

    if exchange == Exchange.CFFEX:
        match_future = re.match(r'^(IF|IC|IM|IH)[0-9]{4}$', code)
        if match_future:
            position_type = PositionType.Future
            variety = match_future.group(1)
        else:
            match_option = re.match(r'^(IO|MO|HO)[0-9]{4}.', code)
            if match_option:
                position_type = PositionType.Option
                variety = match_option.group(1)
    elif exchange in {Exchange.SSE, Exchange.SZSE}:
        match_option1 = re.match(r'^[0-9]{8}$', code)
        match_option2 = re.match(r'^[0-9]{6}(C|P|-C-|-P-).', code)
        if match_option1 or match_option2:
            position_type = PositionType.Option
            variety = 'ETF'
    elif exchange in {Exchange.SHFE, Exchange.CZCE, Exchange.DCE, Exchange.GFEX}:
        match_future = re.match(r'^([A-Za-z]+)[0-9]{4}$', code)
        if match_future:
            position_type = PositionType.Future
            variety = match_future.group(1).upper()
        else:
            match_option = re.match(r'^([A-Za-z]+)[0-9]{4}(C|P|-C-|-P-).', code)
            if match_option:
                position_type = PositionType.Option
                variety = match_option.group(1).upper()

    if position_type is None or variety is None:
        raise ValueError(f'无法解析代码: {code}.{exchange_code}')

    return {
        'exchange': exchange,
        'type': position_type,
        'variety': variety
    }
