import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint
from base import Exchange, PositionType
from combination_strategies import StrategyType, StrategyAnalyzer


class MarginOptimizer:
    def __init__(self, holding: pd.DataFrame, is_close: bool):
        self.holding = holding
        self.holding_separated = self.holding
        self.is_close = is_close

    def _analyze_strategy(self, pos: pd.Series, pos_given: pd.Series) -> dict:
        """分析两手持仓可构成的组合策略, 并计算其组合保证金"""
        analyzer = StrategyAnalyzer.create_analyzer(pos, pos_given, self.is_close)
        return analyzer.analyze()

    def _find_available_strategies(self) -> pd.DataFrame:
        """寻找某个账号持仓的所有可行组合策略"""
        self.holding_separated = self.holding_separated[
            self.holding_separated['type'].isin((PositionType.Future, PositionType.Option))
            ].reset_index(drop=True)
        avail_strats = pd.DataFrame(columns=['code', 'type', 'margin', 'margin_saving'])

        for i, pos in self.holding_separated.iterrows():
            if i == len(self.holding_separated) - 1:
                break
            temp = self.holding_separated[i+1:].copy()
            temp[['type', 'margin', 'margin_saving']] = temp.apply(
                lambda x: pd.Series(self._analyze_strategy(x, pos)), axis=1)
            temp = temp[['code', 'type', 'margin', 'margin_saving']]
            temp = temp[temp['type'] is not StrategyType.Invalid]
            temp = temp[temp['margin_saving'] > 0]
            temp['code'] = temp['code'].apply(lambda x: (pos['code'], x))
            avail_strats = pd.concat([avail_strats, temp], ignore_index=True)
        return avail_strats

    def _optimize(self) -> pd.DataFrame:
        """单个账号持仓的组合保证金优化"""
        avail_strats = self._find_available_strategies()
        if avail_strats.empty:
            return self.holding_separated[['code', 'type', 'quantity', 'margin']].copy()

        '''
        MILP:
            Decision Variables: x        # 每个组合的数量
            Objective: max c^T * x        # 最大化节省保证金
            Subject to: lb <= A * x <= ub        # 持仓数量约束
                        x : Non-negative integers
        '''

        c = avail_strats['margin_saving'].values
        ub = self.holding_separated['quantity'].values
        lb = np.zeros_like(ub)
        A = np.zeros([len(self.holding_separated), len(avail_strats)])
        for j, (pos1, pos2) in enumerate(avail_strats['code']):
            i1 = self.holding_separated.index[self.holding_separated['code'] == pos1][0]
            i2 = self.holding_separated.index[self.holding_separated['code'] == pos2][0]
            A[i1, j] = 1
            A[i2, j] = 1
        constraints = LinearConstraint(A, lb, ub)
        integrality = np.ones_like(c)
        res = milp(c=-c, constraints=constraints, integrality=integrality)

        if res.success:
            selected_strats = pd.DataFrame({
                'code': avail_strats['code'],
                'type': avail_strats['type'],
                'quantity': res.x,
                'margin': avail_strats['margin']
            })
            selected_strats = selected_strats.loc[selected_strats['quantity'] > 0].reset_index(drop=True)
            remaining_pos = pd.DataFrame({
                'code': self.holding_separated['code'],
                'type': self.holding_separated['type'],
                'quantity': ub - A @ res.x,
                'margin': self.holding_separated['margin']
            })
            remaining_pos = remaining_pos.loc[remaining_pos['quantity'] > 0].reset_index(drop=True)
            return pd.concat([remaining_pos, selected_strats], ignore_index=True)
        else:
            raise ValueError("Optimization failed.")

    def _handle_CFE(self) -> pd.DataFrame:
        """中金所: 期货对锁、跨期、跨品种, 单向大边保证金"""
        holding_futures = self.holding_separated[self.holding_separated['type'] is PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures['total_margin'] = holding_futures.apply(
                    lambda x: x['quantity'] * x['margin'], axis=1)
            larger_side = holding_futures.groupby('long_short')['total_margin'].sum().idxmax()
            self.holding_separated.loc[(
                (self.holding_separated['type'] is PositionType.Future) &
                (self.holding_separated['long_short'] != larger_side)
        ), 'margin'] = 0
        return self.holding_separated[['code', 'type', 'quantity', 'margin']].copy()

    def _handle_SHFE(self) -> pd.DataFrame:
        """上期所: 期货对锁、跨期, 单向大边保证金"""
        holding_futures = self.holding_separated[self.holding_separated['type'] is PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures['total_margin'] = holding_futures.apply(
                    lambda x: x['quantity'] * x['margin'], axis=1)
            for variety, holding_variety in holding_futures.groupby('variety'):
                    larger_side = holding_variety.groupby('long_short')['total_margin'].sum().idxmax()
                    self.holding_separated.loc[(
                        (self.holding_separated['type'] is PositionType.Future) &
                        (self.holding_separated['variety'] is variety) &
                        (self.holding_separated['long_short'] != larger_side)
                    ), 'margin'] = 0
        return self.holding_separated[['code', 'type', 'quantity', 'margin']].copy()

    def _handle_each_account(self, exchange: Exchange) -> pd.DataFrame:
        if exchange is Exchange.CFE:
            return self._handle_CFE()
        elif exchange is Exchange.SHFE:
            return self._handle_SHFE()
        else:
            return self._optimize()
    
    def run(self) -> pd.DataFrame:
        """对所有账号持仓进行保证金优化"""
        dfs = []
        self.holding['exchange'] = self.holding['exchange'].apply(lambda x: x.name)
        groups = self.holding.groupby(['exchange', 'account'])
        for (exchange, account), holding_account in groups:
            exchange = Exchange[exchange]
            self.holding_separated = holding_account.copy()
            self.holding_separated['exchange'] = exchange
            self.holding_separated.reset_index(drop=True, inplace=True)
            optimization_result = self._handle_each_account(exchange)
            optimization_result['exchange'] = exchange.name
            optimization_result['account'] = account
            dfs.append(optimization_result)
        return pd.concat(dfs, ignore_index=True)
