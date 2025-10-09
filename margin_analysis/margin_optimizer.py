import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint
from base import Exchange, PositionType
from strategy import *


class MarginOptimizer:
    def __init__(self, holding: pd.DataFrame, is_close: bool):
        self.holding = holding
        self.holding_separated = self.holding
        self.is_close = is_close

    def _analyze_strategy(self, anchor_pos: pd.Series, pos: pd.Series) -> dict:
        """分析两手持仓可构成的组合策略, 并计算其组合保证金"""
        analysis = {
            'type': None,
            'margin': None,
            'margin_saving': None,
        }
        analyzer = StrategyAnalyzerFactory.create(anchor_pos, pos, self.is_close)
        strategy = analyzer.analyze()
        if strategy:
            analysis.update({
                'type': strategy.type,
                'margin': strategy.margin,
                'margin_saving': strategy.margin_saving,
            })
        return analysis

    def _find_available_strategies(self) -> pd.DataFrame:
        """寻找某个账号持仓的所有可行组合策略"""
        self.holding_separated = self.holding_separated[
            self.holding_separated['type'].isin((PositionType.Future, PositionType.Option))
            ].reset_index(drop=True)
        avail_strats = pd.DataFrame(columns=['code_dir', 'type', 'margin', 'margin_saving'])

        for i, anchor_pos in self.holding_separated.iterrows():
            if i == len(self.holding_separated) - 1:
                break
            temp = self.holding_separated[i+1:].copy()
            temp[['type', 'margin', 'margin_saving']] = temp.apply(
                lambda pos: pd.Series(self._analyze_strategy(anchor_pos, pos).values()), axis=1
            )
            temp.dropna(subset=['type'], inplace=True)
            temp = temp[temp['margin_saving'] > 0].copy()
            if temp.empty:
                continue
            temp['code_dir'] = temp['code_dir'].apply(lambda x: (anchor_pos['code_dir'], x))
            temp = temp[['code_dir', 'type', 'margin', 'margin_saving']]
            dfs_to_concate = [df for df in [avail_strats, temp] if not df.empty]
            avail_strats = pd.concat(dfs_to_concate, ignore_index=True)
        return avail_strats

    def _optimize(self) -> pd.DataFrame:
        """单个账号持仓的组合保证金优化"""
        avail_strats = self._find_available_strategies()
        if avail_strats.empty:
            return self.holding_separated[['code_dir', 'type', 'quantity', 'margin']].copy()

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
        for j, (pos1, pos2) in enumerate(avail_strats['code_dir']):
            i1 = self.holding_separated.index[self.holding_separated['code_dir'] == pos1][0]
            i2 = self.holding_separated.index[self.holding_separated['code_dir'] == pos2][0]
            A[i1, j] = 1
            A[i2, j] = 1
        constraints = LinearConstraint(A, lb, ub)
        integrality = np.ones_like(c)
        res = milp(c=-c, constraints=constraints, integrality=integrality)

        if res.success:
            selected_strats = avail_strats[['code_dir', 'type', 'margin']].copy()
            selected_strats['quantity'] = res.x
            selected_strats = selected_strats[selected_strats['quantity'] > 0].reset_index(drop=True)
            remaining_pos = self.holding_separated[['code_dir', 'type', 'margin']].copy()
            remaining_pos['quantity'] = ub - A @ res.x
            remaining_pos = remaining_pos[remaining_pos['quantity'] > 0].reset_index(drop=True)
            dfs_to_concate = [df for df in [remaining_pos, selected_strats] if not df.empty]
            return pd.concat(dfs_to_concate, ignore_index=True)
        else:
            raise ValueError('Optimization failed.')

    def _process_CFE(self) -> pd.DataFrame:
        """处理中金所账号持仓 - 单向大边保证金 (期货对锁、跨期、跨品种)"""
        holding_futures = self.holding_separated[self.holding_separated['type'] == PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures['total_margin'] = holding_futures.apply(
                    lambda x: x['quantity'] * x['margin'], axis=1)
            larger_side = holding_futures.groupby('long_short')['total_margin'].sum().idxmax()
            self.holding_separated.loc[(
                (self.holding_separated['type'] == PositionType.Future) &
                (self.holding_separated['long_short'] != larger_side)
            ), 'margin'] = 0
        return self.holding_separated[['code_dir', 'type', 'quantity', 'margin']].copy()

    def _process_SHFE(self) -> pd.DataFrame:
        """处理上期所账号持仓 - 单向大边保证金 (期货对锁、跨期)"""
        holding_futures = self.holding_separated[self.holding_separated['type'] == PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures['total_margin'] = holding_futures.apply(
                    lambda x: x['quantity'] * x['margin'], axis=1)
            for variety, holding_variety in holding_futures.groupby('variety'):
                    larger_side = holding_variety.groupby('long_short')['total_margin'].sum().idxmax()
                    self.holding_separated.loc[(
                        (self.holding_separated['type'] == PositionType.Future) &
                        (self.holding_separated['variety'] == variety) &
                        (self.holding_separated['long_short'] != larger_side)
                    ), 'margin'] = 0
        return self.holding_separated[['code_dir', 'type', 'quantity', 'margin']].copy()

    def _process_each_account(self, exchange: str) -> pd.DataFrame:
        """按交易所处理单个账号持仓"""
        if exchange == Exchange.CFFEX:
            return self._process_CFE()
        elif exchange == Exchange.SHFE:
            return self._process_SHFE()
        else:
            return self._optimize()
    
    def run(self) -> pd.DataFrame:
        """对所有账号持仓进行保证金优化"""
        dfs_to_concate = []
        groups = self.holding.groupby(['exchange', 'account'])
        for (exchange, account), holding_account in groups:
            self.holding_separated = holding_account.copy()
            self.holding_separated.reset_index(drop=True, inplace=True)
            optimization_result = self._process_each_account(exchange)
            optimization_result['exchange'] = exchange
            optimization_result['account'] = account
            optimization_result = optimization_result[[
                'exchange', 'account', 'code_dir', 'type', 'quantity', 'margin']]
            dfs_to_concate.append(optimization_result)
        return pd.concat(dfs_to_concate, ignore_index=True)
