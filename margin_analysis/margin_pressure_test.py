import numpy as np
import pandas as pd
from base import PositionType
from margin_calculator import MarginCalculator


class MarginMonitor:
    def __init__(self, cal_date: str, params_file: str,
                 account_file: str, holding_file: str):
        self.target_risk_ratio = 0.95
        self.p = 90    # VaR percentile
        self.dt = 1 / 252
        self.n_step = 2
        self.cal_date = cal_date
        self.margin_ratio, self.supplement, self.cov = self._load_params(params_file)
        self.margin_account = self._load_accounts(account_file)
        self.holding = self._load_holdings(holding_file)
        self.holding_separated = self.holding

    def _load_params(self, params_file: str):
        margin_ratio = pd.read_excel(params_file, sheet_name='marginRatio').set_index('Variety')
        supplement = pd.read_excel(params_file, sheet_name='supplement').set_index('AccountName')
        cov = pd.read_excel(params_file, sheet_name='cov').set_index('Variety')
        return margin_ratio, supplement, cov

    def _load_account(self, account_file: str):
        margin_account = pd.read_excel(account_file).dropna()
        margin_account = margin_account[['资产单元名称', '账户权益']]
        margin_account.rename(columns={'资产单元名称': 'account', '账户权益': 'equity'}, inplace=True)
        margin_account['RiskRatioTarget'] = self.target_risk_ratio
        margin_account.set_index('account')
        return margin_account

    def _load_holding(self, holding_file: str):
        holding = pd.read_csv(holding_file, encoding='GB2312')
        return holding

    def _get_cov_cholesky(self):
        varieties = self.holding_separated['variety'].unique()
        n_variety = len(varieties)
        temp = self.cov.loc[varieties, varieties]
        temp = temp.values.astype(float)
        vol_vec = np.diag(temp)
        corr_matrix = (np.triu(temp) + np.triu(temp).T
                       - 2*np.diag(np.diag(temp)) + np.eye(n_variety))
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
        r_path = -0.5 * vol_vec[None, :, None]**2 * self.dt + L @ Z * np.sqrt(self.dt)
        return r_path

    def calc_path(self, r_path):
        n_step, n_variety, n_path = r_path.shape
        pnl = np.zeros((n_step, n_path))
        margin = np.zeros((n_step, n_path))
        variety_idx_map = {variety: idx for idx, variety in enumerate(self.cov.columns)}
        for _, pos in self.holding_separated.iterrows():
            pos = pos.copy()
            quantity_dir = pos['quantity'] * pos['long_short'].map({'long': 1, 'short': -1})
            price = np.full(n_path, fill_value=pos['pv'])
            variety = pos['variety']
            idx = variety_idx_map[variety]
            r = r_path[:, idx, :]
            if pos['type'] == PositionType.Future:
                for step in range(n_step):
                    price *= np.exp(r[step, :])
                    pnl[step, :] += (price - pos['pv']) * quantity_dir
                    margin_pos = MarginCalculator.calc_margin_change(pos, price)    # TODO: MarginCalculator
                    margin += margin_pos * pos['quantity']
            elif pos['type'] == PositionType.Option:
                s = np.full(n_path, fill_value=pos['s'])
                for step in range(n_step):
                    s *= np.exp(r[step, :])
                    price = self.BSM(pos, s)    # TODO: self.BSM()
                    pnl[step, :] += (price - pos['pv']) * quantity_dir
                    margin_pos = MarginCalculator.calc_margin_change(pos, price)    # TODO: MarginCalculator
                    margin += margin_pos * pos['quantity']
        return pnl, margin

    def BSM(pos, s):
        return pos['pv'] * s / pos['s']    # TODO


    def run(self):
        out_df = pd.DataFrame()
        for account, account_info in self.margin_account.iterrows():
            equity_temp = account_info['Equity']
            risk_target = account_info['RiskRatioTarget']
            holding_account = self.holding[self.holding['AccountName'] == account]
            holding_account.reset_index(drop=True, inplace=True)
            if pd.isempty(holding_account):
                continue
            self.holding_separated = holding_account.copy()
            supplement = self.supplement.loc[account]
            r_path = self.gen_path(n_path=10000, seed=20)
            pnl, margin = self.calc_path(r_path)
            equity = equity_temp + pnl + supplement.values.cumsum()    # TODO: check
            risk_ratio = margin / equity
            risk_ratio_var = []
            for step in range(self.n_step):
                var = np.percentile(risk_ratio[:, step], self.p)
                risk_ratio_var.append(var)
            risk_ratio_var_df = pd.DataFrame(risk_ratio_var,
                                             columns=[f'T+{i}' for i in range(step)])    # TODO: check
            risk_ratio_var_df['AccountName'] = account
            out_df = out_df.append(risk_ratio_var_df)
        out_df = out_df.dropna()
