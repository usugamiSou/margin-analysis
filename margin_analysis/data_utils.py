import re
import pandas as pd
from base import Exchange, PositionType
from margin_calculator import MarginCalculator


class DataLoader:
    @staticmethod
    def load_params(params_excel: str):
        margin_ratio = pd.read_excel(params_excel, sheet_name='marginRatio').set_index('Variety')
        supplement = pd.read_excel(params_excel, sheet_name='supplement').set_index('AccountName')
        cov = pd.read_excel(params_excel, sheet_name='cov').set_index('Variety')
        return margin_ratio, supplement, cov
    
    @staticmethod
    def load_account(account_excel: str):
        margin_account = pd.read_excel(account_excel).dropna()
        margin_account = margin_account[['资产单元名称', '账户权益']]
        margin_account.rename(columns={'资产单元名称': 'account', '账户权益': 'equity'}, inplace=True)
        return margin_account
    
    @staticmethod
    def load_holding(holding_excel: str):
        holding = pd.read_excel(holding_excel).dropna()
        return holding
    
    @staticmethod
    def load_market_data(market_data_csv: str):
        market_data = pd.read_csv(market_data_csv, encoding='GB2312').dropna()
        return market_data


class HoldingDataProcessor:
    def __init__(self, holding: pd.DataFrame,
                 stock_futures_data: pd.DataFrame | None,
                 stock_options_data: pd.DataFrame | None,
                 commodity_futures_data: pd.DataFrame | None,
                 commodity_options_data: pd.DataFrame | None,
                 margin_ratio: pd.DataFrame):
        self.holding = holding
        self.stock_futures_data = stock_futures_data
        self.stock_options_data = stock_options_data
        self.commodity_futures_data = commodity_futures_data
        self.commodity_options_data = commodity_options_data
        self.margin_ratio = margin_ratio

    def process(self) -> pd.DataFrame:
        """处理持仓数据: 拆分多空单独持仓, 整合市场数据, 计算保证金"""
        self.holding.rename(columns={'代码': 'code', '持仓帐号': 'account'}, inplace=True)
        self.holding[['exchange', 'type', 'variety']] = self.holding['code'].apply(
            lambda x: pd.Series(HoldingDataProcessor.find_position_basic_info(x)))

        holding_futures = self.holding[self.holding['type'] == PositionType.Future].copy()
        holding_options = self.holding[self.holding['type'] == PositionType.Option].copy()
        if not holding_futures.empty:
            holding_futures = self._merge_futures_data(holding_futures)
        if not holding_options.empty:
            holding_options = self._merge_options_data(holding_options)
        holding = pd.concat([holding_futures, holding_options], ignore_index=True)

        holding_long = holding[holding['多头持仓'] > 0].drop(columns=['空头持仓'])
        holding_long['long_short'] = 'long'
        holding_long.rename(columns={'多头持仓': 'quantity'}, inplace=True)
        holding_long['code_dir'] = holding_long['code'] + '.L'
        holding_short = holding[holding['空头持仓'] < 0].drop(columns=['多头持仓'])
        holding_short['long_short'] = 'short'
        holding_short.rename(columns={'空头持仓': 'quantity'}, inplace=True)
        holding_short['quantity'] *= -1
        holding_short['code_dir'] = holding_short['code'] + '.S'
        holding = pd.concat([holding_long, holding_short], ignore_index=True)

        holding['margin'] = holding.apply(
            lambda x: MarginCalculator(x, self.margin_ratio).calc(), axis=1)
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
        dfs = [df for df in [self.stock_futures_data, self.commodity_futures_data]
               if not df.empty]
        futures_data = pd.concat(dfs, ignore_index=True)
        futures_data.rename(columns={'future_code': 'code'}, inplace=True)
        holding_futures = pd.merge(holding_futures, futures_data, on='code', how='left')
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
        dfs = [df for df in (self.stock_options_data, self.commodity_options_data)
               if not df.empty]
        options_data = pd.concat(dfs, ignore_index=True)
        options_data.rename(columns={'option_code': 'code'}, inplace=True)
        holding_options = pd.merge(holding_options, options_data, on='code', how='left')
        return holding_options

    @staticmethod
    def find_position_basic_info(code: str) -> dict:
        """根据持仓代码判断交易所和持仓类型"""
        code, exchange_code = code.split('.')
        exchange = Exchange.from_code(exchange_code)

        match exchange:
            case Exchange.CFFEX:
                match_future = re.match(r'^(IF|IC|IM|IH)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = match_future.group(1)
                else:
                    match_option = re.match(r'^(IO|MO|HO)[0-9]{4}.', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = match_option.group(1)

            case Exchange.SSE | Exchange.SZSE:
                match_option1 = re.match(r'^[0-9]{8}$', code)
                match_option2 = re.match(r'^[0-9]{6}(C|P|-C-|-P-).', code)
                if match_option1 or match_option2:
                    position_type = PositionType.Option
                    variety = 'ETF'

            case Exchange.SHFE | Exchange.CZCE | Exchange.DCE | Exchange.GFEX:
                match_future = re.match(r'^([A-Za-z]+)[0-9]{4}$', code)
                if match_future:
                    position_type = PositionType.Future
                    variety = match_future.group(1).upper()
                else:
                    match_option = re.match(r'^([A-Za-z]+)[0-9]{4}(C|P|-C-|-P-).', code)
                    if match_option:
                        position_type = PositionType.Option
                        variety = match_option.group(1).upper()

        return {
            'exchange': exchange,
            'position_type': position_type,
            'variety': variety
        }
