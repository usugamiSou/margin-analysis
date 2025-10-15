import os
import numpy as np
import pandas as pd
from data_utils import DataLoader, HoldingDataProcessor
from margin_optimizer import MarginOptimizer
from margin_stress_test import MarginStressTestCombined


root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_path = os.path.join(root_path, 'data')
input_path = os.path.join(data_path, 'input')
output_path = os.path.join(data_path, 'output')
temp_path = os.path.join(data_path, 'temp')


def main():
    holding_excel = os.path.join(input_path, 'kdb_pos.xlsx')
    options_data_csv = os.path.join(input_path, 'option_quote.csv')
    futures_data_csv = os.path.join(input_path, 'future_quote.csv')
    margin_account_excel = os.path.join(input_path, 'margin_account.xlsx')
    params_excel = os.path.join(input_path, 'marginCfg.xlsx')
    holding = DataLoader.load_holding(holding_excel)
    options_data = DataLoader.load_market_data(options_data_csv, encoding='GB2312')
    futures_data = DataLoader.load_market_data(futures_data_csv, encoding='GB2312')
    margin_account = DataLoader.load_account(margin_account_excel)
    margin_ratio_df, supplement, cov, mu = DataLoader.load_params(params_excel)

    processed_holding = HoldingDataProcessor(
        holding, margin_ratio_df,
        stock_futures_data=futures_data,
        stock_options_data=options_data).process()
    processed_holding.to_csv(os.path.join(temp_path, 'processed_holding.csv'),
                             index=False, encoding='GB2312')

    optimizer = MarginOptimizer(processed_holding, is_close=False)
    optimum = optimizer.run(include_zero_quantities=False)
    print('Margin optimization completed.')
    optimization_csv = os.path.join(temp_path, 'optimal_holding.csv')
    optimum.to_csv(optimization_csv, index=False)
    print(f'The optimal holding has been saved to {optimization_csv}.')

    scenarios_r = np.arange(-0.05, 0.051, 0.01)
    stress_test = MarginStressTestCombined(
        processed_holding, margin_account, supplement, cov, mu, scenarios_r
    )
    VaR, pivot_risk_ratio, pivot_supplement = stress_test.run(n_path=100000, seed=20)
    print('Margin stress test completed.')

    output = os.path.join(output_path, 'margin_analysis.xlsx')
    with pd.ExcelWriter(output) as writer:
        holding.to_excel(writer, sheet_name='实际持仓', index=False)
        optimum.to_excel(writer, sheet_name='持仓组合优化', index=False)
        VaR.to_excel(writer, sheet_name='风险度VaR')
        pivot_risk_ratio.to_excel(writer, sheet_name='特定情景风险度')
        pivot_supplement.to_excel(writer, sheet_name='特定情景入金')
    print(f'All results have been saved to {output}.')


if __name__ == '__main__':
    main()
