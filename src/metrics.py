import constants as const

import math


def calculate_z_score(col_to_search, lb_weeks):
    roll_mean = col_to_search.rolling(window=lb_weeks).mean()
    roll_std = col_to_search.rolling(window=lb_weeks).std()
    z_score = (col_to_search - roll_mean) /  (roll_std + 1e-9)
    return z_score


def calculate_cot_index(col_to_search, lb_idx, cur_idx):
    range_to_search = col_to_search[lb_idx:cur_idx+1]
    min_net = range_to_search.min()
    max_net = range_to_search.max()
    cur_net = col_to_search[cur_idx]
    result = (cur_net - min_net) / (max_net - min_net + 1e-9) * 100
    result = 0 if math.isnan(result) else round(result, 0)
    return result


def calculate_tension_index(col_to_search, lb_weeks):
    roll_mean = col_to_search.rolling(window=lb_weeks).mean()
    roll_std = col_to_search.rolling(window=lb_weeks).std()
    tension_osc = (col_to_search - roll_mean) / (roll_std + 1e-9)
    return tension_osc


def calculate_momentum_index(col_to_search):
    result = col_to_search - col_to_search.shift(const.MOMENTUM_PERIOD)
    result = result.fillna(0)
    return result


def calculate_willco(col_to_search, lb_idx, cur_idx):
    # We find the rolling min and max of the Commercial Normalized Net position
    oi_min = col_to_search.iloc[lb_idx:cur_idx+1].min()
    oi_max = col_to_search.iloc[lb_idx:cur_idx+1].max()
    cur_normalized_net = col_to_search.iloc[cur_idx]
    willco = round((cur_normalized_net - oi_min) / (oi_max - oi_min + 1e-9) * 100)
    return int(willco)


def is_commodity(asset_class):
    return asset_class.startswith("Energ") or asset_class.startswith("Grain") or asset_class.startswith("Metal") or asset_class.startswith("Soft")
