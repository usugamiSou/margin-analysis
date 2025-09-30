import os
from data import DataLoader, HoldingDataProcessor
from margin_optimizer import MarginOptimizer


root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_path = os.path.join(root_path, 'data')
input_path = os.path.join(data_path, 'input')
output_path = os.path.join(data_path, 'output')
temp_path = os.path.join(data_path, 'temp')


def main():
    holding = DataLoader.load_holding(os.path.join(input_path, 'kdb_pos.xlsx'))
    future_data = DataLoader.load_market_data(os.path.join(input_path, 'future_quote.csv'))
    option_data = DataLoader.load_market_data(os.path.join(input_path, 'option_quote.csv'))
    margin_ratio, _, _ = DataLoader.load_params(os.path.join(input_path, 'marginCfg.xlsx'))
    data_processor = HoldingDataProcessor(holding, future_data, option_data,
                                          None, None, margin_ratio)
    holding = data_processor.process()
    holding.to_csv(os.path.join(temp_path, 'processed_holding.csv'),
                   index=False, encoding='GB2312')

    optimizer = MarginOptimizer(holding, is_close=False)
    optimization_result = optimizer.run()
    print('Optimization Completed.')
    output_filename = 'optimal_holding.csv'
    optimization_result.to_csv(os.path.join(output_path, output_filename),
                               index=False, encoding='GB2312')
    print(f'The optimal holding has been saved to {os.path.join(output_path, output_filename)}.')


if __name__ == '__main__':
    main()
