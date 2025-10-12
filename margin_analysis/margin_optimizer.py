from typing import Optional
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint
from base import Exchange, PositionType
from strategy import StrategyAnalyzerFactory


class MarginOptimizer:
    def __init__(self, holding: pd.DataFrame, is_close: bool):
        self.holding = holding
        self.is_close = is_close

    def _analyze_strategy(self, anchor_pos: pd.Series, pos: pd.Series
                          ) -> dict[str, Optional[str | float]]:
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

    def _find_available_strategies(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """寻找某个账号持仓的所有可行组合策略"""
        holding_account = holding_account[
            holding_account['type'].isin((PositionType.Future, PositionType.Option))
        ].copy().reset_index(drop=True)
        strats_dfs = []

        for i, anchor_pos in holding_account.iterrows():
            if i == len(holding_account) - 1:
                break
            temp = holding_account[i+1:].copy()
            temp[['type', 'margin', 'margin_saving']] = temp.apply(
                lambda pos: pd.Series(self._analyze_strategy(anchor_pos, pos).values()), axis=1
            )
            temp.dropna(subset=['type'], inplace=True)
            temp = temp[temp['margin_saving'] > 0].copy()
            if temp.empty:
                continue
            temp['code_dir'] = temp['code_dir'].apply(lambda x: (anchor_pos['code_dir'], x))
            temp = temp[['code_dir', 'type', 'margin', 'margin_saving']]
            strats_dfs.append(temp)
        avail_strats = pd.concat(strats_dfs, ignore_index=True)
        return avail_strats

    def _optimize(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """单个账号持仓的组合保证金优化"""
        avail_strats = self._find_available_strategies(holding_account)
        columns = ['code_dir', 'type', 'quantity', 'margin', 'total_margin']
        if avail_strats.empty:
            return holding_account[columns].copy()

        '''
        MILP:
            Decision Variables: x        # 每个组合的数量
            Objective: max c^T * x        # 最大化节省保证金
            Subject to: lb <= A * x <= ub        # 持仓数量约束
                        x : Non-negative integers
        '''
        c = avail_strats['margin_saving'].values
        ub = holding_account['quantity'].values
        lb = np.zeros_like(ub)
        A = np.zeros([len(holding_account), len(avail_strats)])
        for j, (pos1, pos2) in enumerate(avail_strats['code_dir']):
            i1 = holding_account.index[holding_account['code_dir'] == pos1][0]
            i2 = holding_account.index[holding_account['code_dir'] == pos2][0]
            A[i1, j] = 1
            A[i2, j] = 1
        constraints = LinearConstraint(A, lb, ub)
        integrality = np.ones_like(c)
        res = milp(c=-c, constraints=constraints, integrality=integrality)

        if res.success:
            selected_strats = avail_strats[['code_dir', 'type', 'margin']].copy()
            selected_strats['quantity'] = res.x
            selected_strats = selected_strats[selected_strats['quantity'] > 0].reset_index(drop=True)
            remaining = holding_account[['code_dir', 'type', 'margin']].copy()
            remaining['quantity'] = ub - A @ res.x
            dfs_to_concat = [df for df in [remaining, selected_strats] if not df.empty]
            optimum = pd.concat(dfs_to_concat, ignore_index=True)
            optimum['total_margin'] = optimum['margin'] * optimum['quantity']
            return optimum
        else:
            raise ValueError('Optimization failed.')

    def _process_CFE(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """处理中金所账号持仓 - 单向大边保证金 (期货对锁、跨期、跨品种)"""
        holding_account = holding_account.copy()
        holding_futures = holding_account[holding_account['type'] == PositionType.Future]
        if not holding_futures.empty:
            larger_side = holding_futures.groupby('long_short')['total_margin'].sum().idxmax()
            holding_account.loc[(
                (holding_account['type'] == PositionType.Future) &
                (holding_account['long_short'] != larger_side)
            ), ['margin', 'total_margin']] = 0
        columns = ['code_dir', 'type', 'quantity', 'margin', 'total_margin']
        return holding_account[columns]

    def _process_SHFE(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """处理上期所账号持仓 - 单向大边保证金 (期货对锁、跨期)"""
        holding_account = holding_account.copy()
        holding_futures = holding_account[holding_account['type'] == PositionType.Future]
        if not holding_futures.empty:
            for variety, holding_variety in holding_futures.groupby('variety'):
                larger_side = holding_variety.groupby('long_short')['total_margin'].sum().idxmax()
                holding_account.loc[(
                    (holding_account['type'] == PositionType.Future) &
                    (holding_account['variety'] == variety) &
                    (holding_account['long_short'] != larger_side)
                ), ['margin', 'total_margin']] = 0
        columns = ['code_dir', 'type', 'quantity', 'margin', 'total_margin']
        return holding_account[columns]

    def _process_each_account(self, holding_account: pd.DataFrame, exchange: str) -> pd.DataFrame:
        """按交易所处理单个账号持仓"""
        if exchange == Exchange.CFFEX:
            return self._process_CFE(holding_account)
        elif exchange == Exchange.SHFE:
            return self._process_SHFE(holding_account)
        else:
            return self._optimize(holding_account)

    def run(self, include_zero_quantities: bool = True) -> pd.DataFrame:
        """对各账号持仓进行保证金优化"""
        temp_dfs = []
        groups = self.holding.groupby(['exchange', 'account'])
        for (exchange, account), holding_account in groups:
            holding_account.reset_index(drop=True, inplace=True)
            optimum_account = self._process_each_account(holding_account, exchange).copy()
            optimum_account['exchange'] = exchange
            optimum_account['account'] = account
            temp_dfs.append(optimum_account)
        optimum = pd.concat(temp_dfs, ignore_index=True)
        if not include_zero_quantities:
            optimum = optimum[optimum['quantity'] > 0].reset_index(drop=True)
        columns = ['exchange', 'account', 'code_dir', 'type', 'quantity', 'margin', 'total_margin']
        optimum = optimum[columns]
        return optimum
