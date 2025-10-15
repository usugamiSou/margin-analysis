from typing import Optional
import numpy as np
import pandas as pd
from base import PositionType
from margin_utils import MarginCalculator, calc_larger_side_margin_vec


class MarginStressTest:
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 target_risk_ratio: float = 0.95):
        self.holding = holding
        self.margin_account = margin_account
        self.target_risk_ratio = target_risk_ratio

    @staticmethod
    def calc_pnl_margin_r(pos: pd.Series, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """计算单笔持仓在一系列标的收益率下的盈亏和保证金"""
        quantity = pos['quantity']
        quantity_dir = quantity * {'long': 1, 'short': -1}.get(pos['long_short'])
        margin_calculator = MarginCalculator(pos)
        if pos['type'] == PositionType.Future:
            price = pos['close_price'] * (1 + r)
            pnl = (price - pos['close_price']) * quantity_dir
            margin = MarginCalculator(pos).calc_future_vec(price) * quantity
        elif pos['type'] == PositionType.Option:
            s = pos['udl_price'] * (1 + r)
            price = (pos['close_price'] + (s - pos['udl_price']) * pos['delta']
                        + 0.5 * (s - pos['udl_price'])**2 * pos['gamma'])    # delta-gamma近似
            pnl = (price - pos['close_price']) * quantity_dir
            calc_margin_vec = np.vectorize(margin_calculator.calc_option)
            margin = MarginCalculator(pos).calc_option_vec(s, price) * quantity
        return pnl, margin


class MarginStressVaR(MarginStressTest):
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 supplement: pd.DataFrame,
                 cov: pd.DataFrame,
                 mu: pd.DataFrame,
                 target_risk_ratio: float = 0.95,
                 VaR_percentile: int = 90,
                 dt: float = 1 / 252,
                 n_step: int = 2):
        super().__init__(holding, margin_account, target_risk_ratio)
        self.supplement = supplement
        udls = self.holding['udl'].unique()
        self.udl_idx_map = {udl: idx for idx, udl in enumerate(udls)}
        # cov: 上三角阵
        #    - 对角线: 波动率
        #    - 非对角线: 相关系数
        cov = cov.fillna(cov.T)
        self.cov = cov.loc[udls, udls].values.astype(float)
        self.mu = mu['mu'].reindex(udls, fill_value=0).values.astype(float)
        self.VaR_percentile = VaR_percentile
        self.dt = dt
        self.n_step = n_step

    def _get_cov_cholesky(self) -> tuple[np.ndarray, np.ndarray]:
        """Cholesky分解协方差矩阵, 返回L矩阵和波动率向量"""
        n_udl = len(self.cov)
        vol_vec = np.diag(self.cov)
        corr = self.cov - np.diag(np.diag(self.cov)) + np.eye(n_udl)
        cov_matrix = corr * np.outer(vol_vec, vol_vec)
        L = np.linalg.cholesky(cov_matrix)
        return L, vol_vec

    def gen_path(self, n_path: int = 10000, seed: Optional[int] = None) -> np.ndarray:
        """生成标的收益率路径, shape: (n_step, n_udl, n_path)"""
        L, vol_vec = self._get_cov_cholesky()
        n_udl = len(vol_vec)
        r_path = np.empty((self.n_step, n_udl, n_path))
        if seed is not None:
            np.random.seed(seed)
        Z = np.random.standard_normal((self.n_step, n_udl, n_path))
        log_r_path = ((self.mu[None, :, None] - 0.5 * vol_vec[None, :, None]**2) * self.dt
                      + L @ Z * np.sqrt(self.dt))
        log_r_path = log_r_path.cumsum(axis=0)
        r_path = np.exp(log_r_path) - 1
        return r_path

    def _calc_path(self, r_path: np.ndarray, holding_account: pd.DataFrame
                   ) -> tuple[np.ndarray, np.ndarray]:
        """计算单个持仓账户在各标的收益率路径下的持仓盈亏与保证金, shape: (n_step, n_path)"""
        pnls_pos, margins_pos = zip(*holding_account.apply(
            lambda pos: self.calc_pnl_margin_r(
                pos, r_path[:, self.udl_idx_map[pos['udl']], :]), axis=1))
        pnl = np.sum(pnls_pos, axis=0)
        margins_pos = np.array(margins_pos)
        margin = calc_larger_side_margin_vec(holding_account, margins_pos)
        return pnl, margin

    def calc_risk_ratio_VaR(self, r_path: np.ndarray, holding_account: pd.DataFrame,
                             supplement: pd.Series, equity: float | int) -> np.ndarray:
        """计算单个持仓账户通过模拟得到的风险度VaR, shape: (n_step,)"""
        pnl, margin = self._calc_path(r_path, holding_account)
        equity = np.full_like(pnl, fill_value=equity)
        equity += pnl + supplement.values.cumsum()[:, None]
        risk_ratio = margin / equity
        risk_ratio_VaR = np.percentile(risk_ratio, self.VaR_percentile, axis=1)
        return risk_ratio_VaR

    def run(self, n_path: int = 10000, seed: Optional[int] = None) -> pd.DataFrame:
        """通过模拟, 计算各持仓账户的风险度VaR"""
        columns = ['Account'] + [f'T+{i}' for i in range(self.n_step)] + ['Increasement']
        VaR_df = pd.DataFrame(columns=columns)
        r_path = self._gen_path(n_path, seed)
        for account, account_info in self.margin_account.iterrows():
            equity = account_info['equity']
            holding_account = self.holding[self.holding['account'] == account].copy()
            holding_account.reset_index(drop=True, inplace=True)
            if holding_account.empty:
                continue
            remaining = max(sum(holding_account['total_margin']) - equity, 0)
            supplement = self.supplement.loc[account]
            risk_ratio_VaR = self._calc_risk_ratio_VaR(r_path, holding_account, supplement, equity)
            VaR_df.loc[len(VaR_df)] = [account, *risk_ratio_VaR, remaining]
        VaR_df.dropna(inplace=True)
        VaR_df.set_index('Account', inplace=True)
        return VaR_df


class MarginScenarioAnalysis(MarginStressTest):
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 scenarios_r: np.ndarray,
                 target_risk_ratio: float = 0.95):
        super().__init__(holding, margin_account, target_risk_ratio)
        self.scenarios_r = scenarios_r

    def _calc_udl_return_scenarios(self, holding_account: pd.DataFrame
                                   ) -> tuple[np.ndarray, np.ndarray]:
        """计算单个持仓账户在一系列标的收益率情景下的持仓盈亏与保证金"""
        pnls_pos, margins_pos = zip(*holding_account.apply(
            lambda pos: self.calc_pnl_margin_r(pos, self.scenarios_r), axis=1))
        pnl = np.sum(pnls_pos, axis=0)
        margins_pos = np.array(margins_pos)
        margin = calc_larger_side_margin_vec(holding_account, margins_pos)
        return pnl, margin

    def calc_risk_ratio_supplement(self, holding_account: pd.DataFrame,
                                    equity: float | int) -> tuple[np.ndarray, np.ndarray]:
        """计算单个持仓账户在一系列标的收益率情景下的风险度与入金"""
        pnl, margin = self._calc_udl_return_scenarios(holding_account)
        equity = np.full_like(pnl, fill_value=equity)
        equity += pnl
        risk_ratio = margin / equity
        supplement = np.maximum(margin/self.target_risk_ratio - equity, 0)
        return risk_ratio, supplement

    def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """在一系列标的收益率情景下, 分析各持仓账户的风险度与入金"""
        temp_dfs = []
        for account, account_info in self.margin_account.iterrows():
            equity = account_info['equity']
            holding_account = self.holding[self.holding['account'] == account].copy()
            holding_account.reset_index(drop=True, inplace=True)
            if holding_account.empty:
                continue
            risk_ratio, supplement = self._calc_risk_ratio_supplement(holding_account, equity)
            temp_dfs.append(pd.DataFrame({
                'Account': account,
                'r': self.scenarios_r,
                'RiskRatio': risk_ratio,
                'Supplement': supplement
            }))
        scenario_df = pd.concat(temp_dfs, ignore_index=True)
        pivot_risk_ratio = scenario_df.pivot(index='Account', columns='r', values='RiskRatio')
        pivot_supplement = scenario_df.pivot(index='Account', columns='r', values='Supplement')
        return pivot_risk_ratio, pivot_supplement


class MarginStressTestCombined(MarginStressTest):
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 supplement: pd.DataFrame,
                 cov: pd.DataFrame,
                 mu: pd.DataFrame,
                 scenarios_r: np.ndarray,
                 target_risk_ratio: float = 0.95,
                 VaR_percentile: int = 90,
                 dt: float = 1 / 252,
                 n_step: int = 2):
        super().__init__(holding, margin_account, target_risk_ratio)
        self.msv = MarginStressVaR(
            holding, margin_account, supplement, cov, mu,
            target_risk_ratio, VaR_percentile, dt, n_step
        )
        self.msa = MarginScenarioAnalysis(
            holding, margin_account, scenarios_r, target_risk_ratio
        )

    def run(self, n_path: int = 10000, seed: Optional[int] = None
            ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """计算各持仓账户的风险度VaR, 以及在一系列情景下的风险度与入金"""
        columns = ['Account'] + [f'T+{i}' for i in range(self.msv.n_step)] + ['Increasement']
        VaR_df = pd.DataFrame(columns=columns)
        temp_dfs = []
        r_path = self.msv.gen_path(n_path, seed)

        for account, account_info in self.margin_account.iterrows():
            equity = account_info['equity']
            holding_account = self.holding[self.holding['account'] == account].copy()
            holding_account.reset_index(drop=True, inplace=True)
            if holding_account.empty:
                continue
            # VaR
            remaining = max(sum(holding_account['total_margin']) - equity, 0)
            supplement = self.msv.supplement.loc[account]
            risk_ratio_VaR = self.msv.calc_risk_ratio_VaR(r_path, holding_account, supplement, equity)
            VaR_df.loc[len(VaR_df)] = [account, *risk_ratio_VaR, remaining]
            # Scenario
            risk_ratio, supplement = self.msa.calc_risk_ratio_supplement(holding_account, equity)
            temp_dfs.append(pd.DataFrame({
                'Account': account,
                'r': self.msa.scenarios_r,
                'RiskRatio': risk_ratio,
                'Supplement': supplement
            }))
        VaR_df.dropna(inplace=True)
        VaR_df.set_index('Account', inplace=True)
        scenario_df = pd.concat(temp_dfs, ignore_index=True)
        pivot_risk_ratio = scenario_df.pivot(index='Account', columns='r', values='RiskRatio')
        pivot_supplement = scenario_df.pivot(index='Account', columns='r', values='Supplement')
        return VaR_df, pivot_risk_ratio, pivot_supplement
