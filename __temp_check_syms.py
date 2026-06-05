from symbols import get_working_symbols
syms = get_working_symbols()
print(f'Total symbols: {len(syms)}')
print(f'First 10: {syms[:10]}')
us = [s for s in syms if s in ['SPY','QQQ','IWM','DIA','VTI']]
print(f'US ETFs present: {us}')
