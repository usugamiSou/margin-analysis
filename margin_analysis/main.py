import pandas as pd
from holding_data_processor import HoldingDataProcessor
from margin_optimizer import MarginOptimizer


if __name__ == '__main__':
    holding = pd.read_excel('kdb_pos.xlsx').dropna()
    future_data = pd.read_csv('future_quote.csv', encoding='GB2312').dropna()
    option_data = pd.read_csv('option_quote.csv', encoding='GB2312').dropna()
    option_data2 = pd.read_csv('option_quote2.csv', encoding='GB2312').dropna()
    holding = HoldingDataProcessor.preprocess_holding(holding, future_data, [option_data, option_data2])
    optimizer = MarginOptimizer(holding, is_close=False)
    optimization_result = optimizer.run()
    print('Optimization Completed.')

    output_path = 'optimal_holding.csv'
    optimization_result.to_csv(output_path, index=False, encoding='GB2312')
    print(f'The optimal holding is saved to {output_path}.')
