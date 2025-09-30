import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint
from base import Exchange, PositionType
from combination_strategies import StrategyType, StrategyAnalyzer


class MarginOptimizer:
    def __init__(self, holding: pd.DataFrame, is_close: bool):
        self.holding = holding
        self.is_close = is_close

    def _analyze_strategy(self, pos: pd.Series, pos_given: pd.Series) -> dict:
        """分析两手持仓可构成的组合策略, 并计算其组合保证金"""
        analyzer = StrategyAnalyzer.create_analyzer(pos, pos_given, self.is_close)
        return analyzer.analyze()

    def _find_available_strategies(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """寻找某个账号持仓的所有可行组合策略"""
        holding_account = holding_account[
            holding_account['type'].isin((PositionType.Future, PositionType.Option))
            ].reset_index(drop=True)
        avail_strats = pd.DataFrame(columns=['code', 'type', 'margin', 'margin_saving'])

        for n_row, pos in holding_account.iterrows():
            if n_row == len(holding_account) - 1:
                break
            pos_to_analyze = holding_account[n_row+1:].copy()
            pos_to_analyze[['type', 'margin', 'margin_saving']] = pos_to_analyze.apply(
                lambda x: pd.Series(self._analyze_strategy(x, pos)), axis=1)
            pos_to_analyze = pos_to_analyze[['code', 'type', 'margin', 'margin_saving']]
            pos_to_analyze = pos_to_analyze[pos_to_analyze['type'] != StrategyType.Invalid]
            pos_to_analyze = pos_to_analyze[pos_to_analyze['margin_saving'] > 0]
            pos_to_analyze['code'] = pos_to_analyze['code'].apply(
                lambda x: (pos['code'], x))
            avail_strats = pd.concat([avail_strats, pos_to_analyze], ignore_index=True)
        return avail_strats

    def _optimize(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """单个账号持仓的保证金优化"""
        avail_strats = self._find_available_strategies(holding_account)
        if avail_strats.empty:
            return holding_account[['code', 'type', 'quantity', 'margin']].copy()

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
        for j, (pos1, pos2) in enumerate(avail_strats['code']):
            i1 = holding_account.index[holding_account['code'] == pos1][0]
            i2 = holding_account.index[holding_account['code'] == pos2][0]
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
                'code': holding_account['code'],
                'type': holding_account['type'],
                'quantity': ub - A @ res.x,
                'margin': holding_account['margin']
            })
            remaining_pos = remaining_pos.loc[remaining_pos['quantity'] > 0].reset_index(drop=True)
            return pd.concat([remaining_pos, selected_strats], ignore_index=True)
        else:
            raise ValueError("Optimization failed.")

    def _handle_CFE(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """中国金融期货交易所: 期货对锁、跨期、跨品种，单向大边保证金"""
        holding_futures = holding_account[holding_account['type'] == PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures['total_margin'] = holding_futures.apply(
                    lambda x: x['quantity'] * x['margin'], axis=1)
            larger_side = holding_futures.groupby('long_short')['total_margin'].sum().idxmax()
            holding_account.loc[(
                (holding_account['type'] == PositionType.Future) &
                (holding_account['long_short'] != larger_side)
        ), 'margin'] = 0
        return holding_account[['code', 'type', 'quantity', 'margin']].copy()

    def _handle_SHFE(self, holding_account: pd.DataFrame) -> pd.DataFrame:
        """上海期货交易所: 期货对锁、跨期，单向大边保证金"""
        holding_futures = holding_account[holding_account['type'] == PositionType.Future].copy()
        if not holding_futures.empty:
            holding_futures['total_margin'] = holding_futures.apply(
                    lambda x: x['quantity'] * x['margin'], axis=1)
            for variety, holding_variety in holding_futures.groupby('variety'):
                    larger_side = holding_variety.groupby('long_short')['total_margin'].sum().idxmax()
                    holding_account.loc[(
                        (holding_account['type'] == PositionType.Future) &
                        (holding_account['variety'] == variety) &
                        (holding_account['long_short'] != larger_side)
                    ), 'margin'] = 0
        return holding_account[['code', 'type', 'quantity', 'margin']].copy()

    def _handle_each_account(self, holding_account: pd.DataFrame, exchange: Exchange) -> pd.DataFrame:
        if exchange == Exchange.CFE:
            return self._handle_CFE(holding_account)
        elif exchange == Exchange.SHFE:
            return self._handle_SHFE(holding_account)
        else:
            return self._optimize(holding_account)
    
    def run(self) -> pd.DataFrame:
        """对所有账号持仓进行保证金优化"""
        dfs = []
        self.holding['exchange'] = self.holding['exchange'].apply(lambda x: x.value)
        groups = self.holding.groupby(['exchange', '持仓帐号'])
        for (exchange, account), holding_account in groups:
            exchange = Exchange(exchange)
            print(f'Optimizing holding on account {account}.{exchange.name}...')
            holding_account['exchange'] = exchange
            holding_account = holding_account.reset_index(drop=True)
            optimization_result = self._handle_each_account(holding_account, exchange)
            optimization_result['exchange'] = exchange
            optimization_result['account'] = account
            dfs.append(optimization_result)
        return pd.concat(dfs, ignore_index=True)
