import pandas as pd
from holding_data_processor import HoldingDataProcessor
from margin_optimizer import MarginOptimizer


if __name__ == '__main__':
    holding = pd.read_excel('data/input/kdb_pos.xlsx').dropna()
    future_data = pd.read_csv('data/input/future_quote.csv', encoding='GB2312').dropna()
    option_data = pd.read_csv('data/input/option_quote.csv', encoding='GB2312').dropna()
    option_data2 = pd.read_csv('data/input/option_quote2.csv', delimiter='	', encoding='GB2312').dropna()
    holding = HoldingDataProcessor.preprocess_holding(holding, future_data, [option_data, option_data2])
    holding.to_csv('data/output/processed_holding.csv', index=False, encoding='GB2312')
    optimizer = MarginOptimizer(holding, is_close=False)
    optimization_result = optimizer.run()
    print('Optimization Completed.')

    output_path = 'data/output/optimal_holding.csv'
    optimization_result.to_csv(output_path, index=False, encoding='GB2312')
    print(f'The optimal holding is saved to {output_path}.')
