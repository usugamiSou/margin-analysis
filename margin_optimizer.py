import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from scipy.optimize import milp, LinearConstraint


class MarginOptimizerBase(ABC):
    @abstractmethod
    def _combine(self, pos, pos_given):
        pass

    @abstractmethod
    def _find_available_combinations(self):
        pass

    @abstractmethod
    def _optimize(self, avail_combs):
        pass

    @abstractmethod
    def run(self):
        pass

    @classmethod
    def create_optimizer(cls, holding, exchange, is_close):
        match exchange:
            case 'XSHG' | 'SH':
                return MarginOptimizerOptions(holding, is_close)
            case 'XSHE' | 'SZ':
                return MarginOptimizerOptions(holding, is_close)
            case 'CCFX' | 'CFE':
                return MarginOptimizerFutures(holding, allow_intercommodity=True)
            case 'XSGE' | 'SHFE':
                return MarginOptimizerFutures(holding, allow_intercommodity=False)
            case 'XDCE' | 'DCE':
                pass
            case 'XZCE' | 'CZCE':
                pass
            case _:
                raise ValueError(f'Unsupported exchange: {exchange}.')


class MarginOptimizerFutures(MarginOptimizerBase):
    def __init__(self, holding, allow_intercommodity):
        self.holding = holding
        self.allow_intercommodity = allow_intercommodity

    def _combine(self, pos, pos_given):
        pass

    def _find_available_combinations(self):
        pass

    def _optimize(self):
        holding_futures = self.holding[self.holding['type']=='future'].copy()
        if holding_futures.empty:
            return

        holding_futures['total_margin'] = holding_futures.apply(
                lambda x: x['quantity'] * x['margin'], axis=1)
        if self.allow_intercommodity:
            larger_side = holding_futures.groupby('long_short')['total_margin'].sum().idxmax()
            self.holding.loc[
                (self.holding['type']=='future') &
                (self.holding['long_short']!=larger_side),
                'margin'] = 0
        else:
            for variety, holding_variety in holding_futures.groupby('variety'):
                larger_side = holding_variety.groupby('long_short')['total_margin'].sum().idxmax()
                self.holding.loc[
                    (self.holding['type']=='future') &
                    (self.holding['variety']==variety) &
                    (self.holding['long_short']!=larger_side),
                    'margin'] = 0

    def run(self):
        self._optimize()
        self.holding = self.holding[['code', 'type', 'quantity', 'margin']]


class MarginOptimizerOptions(MarginOptimizerBase):
    def __init__(self, holding, is_close):
        self.holding = holding
        self.is_close = is_close

    def _combine(self, pos: pd.Series, pos_given: pd.Series) -> dict:
        """
        将两手期权持仓进行组合, 并计算组合的保证金及所节省的保证金

        :param pos: 一手持仓
        :param pos_given: 给定的一手空头持仓
        :type pos: pd.Series
        :type pos_given: pd.Series
        :returns: 组合类型, 组合保证金, 保证金节省
        :rtype: dict
        """

        margin_original = pos['margin'] + pos_given['margin']
        
        if pos_given['call_put'] == 'call':
            if pos['long_short'] == 'long' and pos['call_put'] == 'call':
                if pos['strike_price'] - pos_given['strike_price'] < -1e-6:  # 牛市看涨价差
                    margin_combination = 0
                    return {
                        'type': 'CNSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    }

                elif pos['strike_price'] - pos_given['strike_price'] > 1e-6:  # 熊市看涨价差
                    margin_combination = (pos['strike_price'] - pos_given['strike_price']) * pos['multiplier']
                    return {
                        'type': 'CXSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    }

                else:  # 自动对冲
                    margin_combination = 0
                    return {
                        'type': 'AutoHedge',
                        'margin': margin_combination,
                        'margin_saving': max(margin_original - margin_combination - 1, 0)  # 自动对冲惩罚项
                    }

            elif pos['long_short'] == 'short' and pos['call_put'] == 'put':
                if abs(pos['strike_price'] - pos_given['strike_price']) < 1e-6:  # 跨式
                    if pos['margin'] < pos_given['margin']:
                        margin_combination = pos_given['margin'] + pos['s'] * pos['multiplier']
                    else:
                        margin_combination = pos['margin'] + pos_given['s'] * pos_given['multiplier']
                    return {
                        'type': 'KS',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    }

                elif pos['strike_price'] < pos_given['strike_price']:  # 宽跨式
                    if pos['margin'] < pos_given['margin']:
                        margin_combination = pos_given['margin'] + pos['s'] * pos['multiplier']
                    else:
                        margin_combination = pos['margin'] + pos_given['s'] * pos_given['multiplier']
                    return {
                        'type': 'KKS',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    }

        elif pos_given['call_put'] == 'put':
            if pos['long_short'] == 'long' and pos['call_put'] == 'put':
                if pos['strike_price'] - pos_given['strike_price'] < -1e-6:  # 牛市看跌价差
                    margin_combination = (pos_given['strike_price'] - pos['strike_price']) * pos['multiplier']
                    return {
                        'type': 'PNSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    }

                elif pos['strike_price'] - pos_given['strike_price'] > 1e-6:  # 熊市看跌价差
                    margin_combination = 0
                    return {
                        'type': 'PXSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    }

                else:  # 自动对冲
                    margin_combination = 0
                    return {
                        'type': 'AutoHedge',
                        'margin': margin_combination,
                        'margin_saving': max(margin_original - margin_combination - 1, 0)  # 自动对冲惩罚项
                    }

        return {
            'type': 'Invalid',
            'margin': margin_original,
            'margin_saving': 0
        }

    def _find_available_combinations(self):
        """
        查找持仓中可以组合的期权对, 计算保证金节省

        :returns: 可行的期权组合
        :rtype: pd.DataFrame
        """

        avail_combs = pd.DataFrame(columns=['code', 'type', 'margin', 'margin_saving'])
        holding_options = self.holding[self.holding['type']=='option'].copy()
        if holding_options.empty:
            return avail_combs
        
        for _, holding_udl in self.holding.groupby(['udl', 'last_tradedate']):
            for _, pos in holding_udl[holding_udl['long_short']=='short'].iterrows():
                holding_udl[['type', 'margin', 'margin_saving']] = holding_udl.apply(
                    lambda x: pd.Series(self._combine(x, pos).values()), axis=1)
                pos_to_combine = holding_udl[holding_udl['type']!='Invalid']
                pos_to_combine = pos_to_combine[pos_to_combine['margin_saving']>0]
                pos_to_combine = pos_to_combine[['code', 'type', 'margin', 'margin_saving']]
                pos_to_combine['code'] = pos_to_combine['code'].apply(
                    lambda x: (pos['code'], x))
                avail_combs = pd.concat([avail_combs, pos_to_combine], ignore_index=True)
        return avail_combs

    def _optimize(self, avail_combs, allow_autohedge=None):
        """
        优化期权组合以最大化保证金节省

        :param avail_combs: 可行的期权组合
        :type avail_combs: pd.DataFrame
        :param allow_autohedge: 是否允许自动对冲, defaults to False
        :type allow_autohedge: bool, optional
        :returns: 剩余持仓和选择的组合
        :rtype: (pd.DataFrame, pd.DataFrame)
        """

        if allow_autohedge is None:
            allow_autohedge = self.is_close
        if not allow_autohedge:
            avail_combs = avail_combs[avail_combs['type']!='AutoHedge'].reset_index(drop=True)
        if avail_combs.empty:
            self.holding = self.holding[['code', 'type', 'quantity', 'margin']]
            return

        c = avail_combs['margin_saving'].values
        ub = self.holding['quantity'].values
        lb = np.zeros_like(ub)
        A = np.zeros([len(self.holding), len(avail_combs)])
        for j, pos in enumerate(avail_combs['code']):
            pos1, pos2 = pos
            i1 = self.holding.index[self.holding['code']==pos1][0]
            i2 = self.holding.index[self.holding['code']==pos2][0]
            A[i1, j] = 1
            A[i2, j] = 1
        constraints = LinearConstraint(A, lb, ub)
        integrality = np.ones_like(c)
        res = milp(c=-c, constraints=constraints, integrality=integrality)
        if res.success:
            selected_combs = pd.DataFrame({
                'code': avail_combs['code'],
                'type': avail_combs['type'],
                'quantity': res.x,
                'margin': avail_combs['margin']
            })
            selected_combs = selected_combs.loc[selected_combs['quantity']>0].reset_index(drop=True)
            remaining_pos = pd.DataFrame({
                'code': self.holding['code'],
                'type': self.holding['type'],
                'quantity': ub - A @ res.x,
                'margin': self.holding['margin']
            })
            remaining_pos = remaining_pos.loc[remaining_pos['quantity']>0].reset_index(drop=True)
            self.holding = pd.concat([remaining_pos, selected_combs], ignore_index=True)
        else:
            raise ValueError("Optimization failed.")

    def run(self):
        avail_combs = self._find_available_combinations()
        self._optimize(avail_combs)


class MarginOptimizerFuturesOptions(MarginOptimizerBase):
    def __init__(self, holding, is_close):
        self.holding = holding
        self.is_close = is_close
    
    def _combine(self, pos, pos_given):
        if pos_given['type'] == 'future':
            pass
    
    def _combine_futures(self, pos, pos_given):
        margin_original = pos['margin'] + pos_given['margin']
        combination_result = {
            'type': 'Invalid',
            'margin': margin_original,
            'margin_saving': 0
        }

        if pos['long_short'] == 'short':
            return combination_result
        
        if pos['code_original'] == pos_given['code_original']:  # 期货对锁
            margin_combination = max(pos['margin'], pos_given['margin'])
            combination_result = ({
                'type': 'FutureLockPosition',
                'margin': margin_combination,
                'margin_saving': margin_original - margin_combination
            })

        elif pos['variety'] == pos_given['variety']:  # 期货跨期
            margin_combination = max(pos['margin'], pos_given['margin'])
            combination_result = ({
                'type': 'CalendarSpread',
                'margin': margin_combination,
                'margin_saving': margin_original - margin_combination
            })

        # elif pos['variety'].group == pos['variety'].group:  # 期货跨品种
        #     margin_combination = max(pos['margin'], pos_given['margin'])
        #     combination_result = ({
        #         'type': 'IntercommoditySpread',
        #         'margin': margin_combination,
        #         'margin_saving': margin_original - margin_combination
        #     })


    def _combine_options(self, pos: pd.Series, pos_given: pd.Series) -> dict:
        """
        将两手期权持仓进行组合, 并计算组合的保证金及所节省的保证金

        :param pos: 一手持仓
        :param pos_given: 给定的一手空头持仓
        :type pos: pd.Series
        :type pos_given: pd.Series
        :returns: 组合类型, 组合保证金, 保证金节省
        :rtype: dict
        """

        margin_original = pos['margin'] + pos_given['margin']
        combination_result = {
            'type': 'Invalid',
            'margin': margin_original,
            'margin_saving': 0
        }
        
        if pos_given['call_put'] == 'call':
            if pos['long_short'] == 'long' and pos['call_put'] == 'call':
                if pos['strike_price'] - pos_given['strike_price'] < -1e-6:  # 牛市看涨价差
                    margin_combination = pos_given['margin'] * 0.2
                    combination_result.update({
                        'type': 'CNSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })
                
                elif pos['strike_price'] - pos_given['strike_price'] > 1e-6:  # 熊市看涨价差
                    margin_combination = min(
                        (pos['strike_price'] - pos_given['strike_price']) * pos['multiplier'],
                        pos_given['margin']
                    )
                    combination_result.update({
                        'type': 'CXSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })
                
                else:  # 期权对锁
                    margin_combination = pos_given['margin'] * 0.2
                    combination_result.update({
                        'type': 'OptionLockPosition',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })
                
            elif pos['long_short'] == 'short' and pos['call_put'] == 'put':
                if abs(pos['strike_price'] - pos_given['strike_price']) < 1e-6:  # 跨式
                    if pos['margin'] < pos_given['margin']:
                        margin_combination = pos_given['margin'] + pos['s'] * pos['multiplier']
                    else:
                        margin_combination = pos['margin'] + pos_given['s'] * pos_given['multiplier']
                    combination_result.update({
                        'type': 'KS',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })

                elif pos['strike_price'] < pos_given['strike_price']:  # 宽跨式
                    if pos['margin'] < pos_given['margin']:
                        margin_combination = pos_given['margin'] + pos['s'] * pos['multiplier']
                    else:
                        margin_combination = pos['margin'] + pos_given['s'] * pos_given['multiplier']
                    combination_result.update({
                        'type': 'KKS',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })
        
        elif pos_given['call_put'] == 'put':
            if pos['long_short'] == 'long' and pos['call_put'] == 'put':
                if pos['strike_price'] - pos_given['strike_price'] < -1e-6:  # 牛市看跌价差
                    margin_combination = min(
                        (pos_given['strike_price'] - pos['strike_price']) * pos['multiplier'],
                        pos_given['margin']
                    )
                    combination_result.update({
                        'type': 'PNSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })

                elif pos['strike_price'] - pos_given['strike_price'] > 1e-6:  # 熊市看跌价差
                    margin_combination = pos_given['margin'] * 0.2
                    combination_result.update({
                        'type': 'PXSJC',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })

                else:  # 期权对锁
                    margin_combination = pos_given['margin'] * 0.2
                    combination_result.update({
                        'type': 'OptionLockPosition',
                        'margin': margin_combination,
                        'margin_saving': margin_original - margin_combination
                    })

        return combination_result

    def _find_available_combinations(self):
        pass

    def _optimize(self):
        pass

    def run(self):
        pass


class MarginOptimizer():
    def __init__ (self, holding, is_close=False):
        self.holding = holding
        self.is_close = is_close
    
    def run(self):
        dfs = []
        groups = self.holding.groupby(['exchange', '持仓帐号'])
        for (exchange, account), holding_exchange_account in groups:
            holding_exchange_account = holding_exchange_account.reset_index(drop=True)
            optimizer = MarginOptimizerBase.create_optimizer(holding_exchange_account, exchange, self.is_close)
            optimizer.run()
            optimization_result = optimizer.holding
            optimization_result['exchange'] = exchange
            optimization_result['account'] = account
            dfs.append(optimization_result)
        pd.concat(dfs, ignore_index=True).to_csv(f'margin_optimization.csv', index=False, encoding='GB2312')


if __name__ == '__main__':

    from holding_data_processor import HoldingDataProcessor

    holding = pd.read_excel('kdb_pos.xlsx').dropna()
    options_data = pd.read_csv('option_quote.csv', encoding='GB2312').dropna()
    holding = HoldingDataProcessor.preprocess_holding(holding)
    
    optimizer = MarginOptimizer(holding, is_close=True)
    optimizer.run()
    print('Completed.')
