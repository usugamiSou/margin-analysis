import numpy as np
import pandas as pd
from base import PositionType
from margin_calculator import MarginCalculator


class MarginStressTest:
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 margin_ratio: pd.DataFrame,
                 cov: pd.DataFrame,
                 supplement: pd.DataFrame,
                 target_risk_ratio: float = 0.95):
        self.holding = holding
        self.margin_account = margin_account
        self.margin_ratio = margin_ratio
        self.supplement = supplement
        self.target_risk_ratio = target_risk_ratio

        self.holding['variety_temp'] = self.holding.apply(
            lambda x: x['option_mark_code'] if x['type'] == PositionType.Option else x['variety'],
            axis=1)
        varieties = self.holding['variety_temp'].unique()
        self.varieties = varieties
        self.variety_idx_map = {variety: idx for idx, variety in enumerate(varieties)}
        self.cov = cov.loc[varieties, varieties].values.astype(float)


class MarginStressVaR(MarginStressTest):
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 margin_ratio: pd.DataFrame,
                 cov: pd.DataFrame,
                 supplement: pd.DataFrame,
                 target_risk_ratio: float = 0.95):
        super().__init__(holding, margin_account, margin_ratio, cov, supplement, target_risk_ratio)
        self.p = 90    # VaR 分位数
        self.dt = 1 / 252
        self.n_step = 2

    def _get_cov_cholesky(self):
        n_variety = len(self.varieties)
        vol_vec = np.diag(self.cov)
        corr_matrix = (np.triu(self.cov) + np.triu(self.cov).T
                       - 2*np.diag(np.diag(self.cov)) + np.eye(n_variety))
        cov_matrix = corr_matrix * np.outer(vol_vec, vol_vec)
        L = np.linalg.cholesky(cov_matrix)
        return L, vol_vec

    def gen_path(self, n_path: int, seed: int | None = None):
        L, vol_vec = self._get_cov_cholesky()
        n_variety = len(vol_vec)
        r_path = np.empty((self.n_step, n_variety, n_path))
        if seed:
            np.random.seed(seed)
        Z = np.random.standard_normal((self.n_step, n_variety, n_path))
        # TODO: for etf and index, r-q!=0
        log_r_path = -0.5 * vol_vec[None, :, None]**2 * self.dt + L @ Z * np.sqrt(self.dt)
        log_r_path = log_r_path.cumsum(axis=0)
        r_path = np.exp(log_r_path)
        return r_path

    def calc_path(self, r_path):
        n_step, n_variety, n_path = r_path.shape
        pnl = np.zeros((n_step, n_path))
        margin = np.zeros((n_step, n_path))
        for _, pos in self.holding_separated.iterrows():
            pos = pos.copy()
            quantity = pos['quantity']
            quantity_dir = quantity * {'long': 1, 'short': -1}.get(pos['long_short'])
            variety = pos['variety_temp']
            idx = self.variety_idx_map[variety]
            r = r_path[:, idx, :]
            margin_calculator = MarginCalculator(pos, self.margin_ratio)
            if pos['type'] == PositionType.Future:
                price = r * pos['close_price']
                pnl += (price - pos['close_price']) * quantity_dir
                calc_margin_vec = np.vectorize(margin_calculator.calc_future)
                margin_pos = calc_margin_vec(price)
                margin += margin_pos * pos['quantity']
            elif pos['type'] == PositionType.Option:
                s = r * pos['udl_price']
                '''
                Delta、Gamma近似估计期权价格的变化
                    params: delta, gamma
                也可以通过实现定价公式来计算 (欧式、美式)
                    params: r, q, sigma, T
                '''
                pos['delta'] = 0.5
                pos['gamma'] = 0.02
                price = (pos['close_price'] + (s - pos['udl_price']) * pos['delta']
                         + 0.5 * (s - pos['udl_price'])**2 * pos['gamma'])
                pnl += (price - pos['close_price']) * quantity_dir
                calc_margin_vec = np.vectorize(margin_calculator.calc_option)
                margin_pos = calc_margin_vec(s, price)
                margin += margin_pos * quantity
        return pnl, margin

    def run(self):
        columns = ['account'] + [f'T+{i}' for i in range(self.n_step)] + ['increasement']
        out_df = pd.DataFrame(columns=columns)
        r_path = self.gen_path(n_path=100000)
        for account, account_info in self.margin_account.iterrows():
            equity = account_info['equity']
            holding_account = self.holding[self.holding['account'] == account]
            holding_account.reset_index(drop=True, inplace=True)
            if holding_account.empty:
                continue
            total_margin = holding_account.apply(
                lambda x: x['quantity'] * x['margin'], axis=1).sum()
            remaining = max(total_margin - equity, 0)
            self.holding_separated = holding_account.copy()
            supplement = self.supplement.loc[account]
            
            pnl, margin = self.calc_path(r_path)
            equity += pnl + supplement.values.cumsum()[:, None]
            risk_ratio = margin / equity
            risk_ratio_VaR = np.percentile(risk_ratio, self.p, axis=1)
            out_df.loc[len(out_df)] = [account, *risk_ratio_VaR, remaining]
        out_df.dropna(inplace=True)
        out_df.set_index('account', inplace=True)
        return out_df


class MarginScenarioAnalysis(MarginStressTest):
    def __init__(self, holding: pd.DataFrame,
                 margin_account: pd.DataFrame,
                 margin_ratio: pd.DataFrame,
                 cov: pd.DataFrame,
                 supplement: pd.DataFrame,
                 udl_return_scenarios: np.ndarray,
                 target_risk_ratio: float = 0.95):
        super().__init__(holding, margin_account, margin_ratio, cov, supplement, target_risk_ratio)
        self.udl_return_scenarios = udl_return_scenarios

    def calc_udl_return_scenario(self, udl_return):
        pnl = 0
        margin = 0
        for _, pos in self.holding_separated.iterrows():
            pos = pos.copy()
            quantity = pos['quantity']
            quantity_dir = quantity * {'long': 1, 'short': -1}.get(pos['long_short'])
            if pos['type'] == PositionType.Future:
                price = pos['close_price'] * (1 + udl_return)
                pnl += (price - pos['close_price']) * quantity_dir
                margin_calculator = MarginCalculator(pos, self.margin_ratio)
                margin_pos = margin_calculator.calc_future(price)
                margin += margin_pos * pos['quantity']
            elif pos['type'] == PositionType.Option:
                s = pos['udl_price'] * (1 + udl_return)
                pos['delta'] = 0.5
                pos['gamma'] = 0.02
                price = (pos['close_price'] + (s - pos['udl_price']) * pos['delta']
                         + 0.5 * (s - pos['udl_price'])**2 * pos['gamma'])
                pnl += (price - pos['close_price']) * quantity_dir
                margin_calculator = MarginCalculator(pos, self.margin_ratio)
                margin_pos = margin_calculator.calc_option(s, price)
                margin += margin_pos * quantity
        return pnl, margin

    def run(self):
        columns = ['account', 'udl_return', 'risk_ratio', 'supplement']
        out_df = pd.DataFrame(columns=columns)
        for account, account_info in self.margin_account.iterrows():
            equity = account_info['equity']
            holding_account = self.holding[self.holding['account'] == account]
            holding_account.reset_index(drop=True, inplace=True)
            if holding_account.empty:
                continue
            self.holding_separated = holding_account.copy()

            for udl_return in self.udl_return_scenarios:
                pnl, margin = self.calc_udl_return_scenario(udl_return)
                equity += pnl
                risk_ratio = margin / equity
                supplement = max(margin / self.target_risk_ratio - equity, 0)
                out_df.loc[len(out_df)] = [account, udl_return, risk_ratio, supplement]
        out_df.dropna(inplace=True)
        pivot_risk_ratio = out_df.pivot_table(index='account', columns='udl_return', values='risk_ratio')
        pivot_supplement = out_df.pivot_table(index='account', columns='udl_return', values='supplement')
        return pivot_risk_ratio, pivot_supplement
