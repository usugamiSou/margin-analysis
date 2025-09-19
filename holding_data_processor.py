import pandas as pd
import re


class HoldingDataProcessor:
    @staticmethod
    def determine_position_type(code):
        code, exchange = code.split('.')
        match exchange:
            case 'CCFX' | 'CFE':
                if re.match(r'^(IF|IC|IM|IH)[0-9]{4}$', code):
                    return 'future'
                elif re.match(r'^(IO|MO|HO)[0-9]{4}-(C|P)-[0-9]+$', code):
                    return 'option'
            case 'XSHG' | 'SH':
                if re.match(r'^[0-9]{8}$', code):
                    return 'option'
                elif re.match(r'^[0-9]{6}$', code):
                    return 'stock'
            case 'XSHE' | 'SZ':
                pass
            case 'XSGE' | 'SHFE':
                pass
            case 'XDCE' | 'DCE':
                pass
            case 'XZCE' | 'CZCE':
                pass
            case 'GFEX':
                pass
            case _:
                raise ValueError(f'Unsupported exchange: {exchange}')

    @staticmethod
    def preprocess_holding(holding, futures_data, options_data):
        holding.rename(columns={'代码':'code_original'}, inplace=True)
        holding['exchange'] = holding['code_original'].apply(lambda x: x.split('.')[-1])
        holding['type'] = holding['code_original'].apply(
            lambda x: HoldingDataProcessor.determine_position_type(x))

        holding_long = holding[holding['多头持仓']>0].drop(columns=['空头持仓'])
        holding_long['long_short'] = 'long'
        holding_long.rename(columns={'多头持仓':'quantity'}, inplace=True)
        holding_long['code'] = holding_long['code_original'] + '.L'
        holding_short = holding[holding['空头持仓']<0].drop(columns=['多头持仓'])
        holding_short['long_short'] = 'short'
        holding_short.rename(columns={'空头持仓':'quantity'}, inplace=True)
        holding_short['quantity'] *= -1
        holding_short['code'] = holding_long['code_original'] + '.S'
        holding = pd.concat([holding_long, holding_short], ignore_index=True)

        holding_futures = holding[holding['type']=='future'].copy()
        # holding_futures = HoldingDataProcessor.process_holding_futures(
        #     holding_futures, futures_data)
        holding_futures['margin'] = 100000    # TODO
        holding_options = holding.loc[holding['type']=='option'].copy()
        holding_options = HoldingDataProcessor.process_holding_options(
            holding_options, options_data)
        holding = pd.concat([holding_futures, holding_options], ignore_index=True)

        return holding

    @staticmethod
    def process_holding_options(holding_options, options_data):
        options_data = options_data[['option_code', 'strike_price', 'call_put', 'last_tradedate',
                                     'multiplier', 's', 'udl', 'margin']]
        holding_options = pd.merge(holding_options, options_data,
                                   left_on=['code_original'], right_on=['option_code'], how='left')
        holding_options['margin'] *= holding_options['long_short'].map({'long': 0, 'short': 1})
        return holding_options
