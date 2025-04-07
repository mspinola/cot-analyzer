import os
import pandas as pd
import yaml

import CotSymbolCodeMap as symbol_code_map

# Columns of COT data to consume
NAME = "Market_and_Exchange_Names"
DATE = "Report_Date_as_MM_DD_YYYY"
CODE = "CFTC_Contract_Market_Code"
INTEREST = "Open_Interest_All"
COMM_LONG = "Comm_Positions_Long_All"
COMM_SHORT = "Comm_Positions_Short_All"
LARGE_LONG = "NonComm_Positions_Long_All"
LARGE_SHORT = "NonComm_Positions_Short_All"
SMALL_LONG = "NonRept_Positions_Long_All"
SMALL_SHORT = "NonRept_Positions_Short_All"

# Columns to create for consumed COT data
COMM_NET = "Comm_Positions_Net"
LARGE_NET = "NonComm_Positions_Net"
SMALL_NET = "NonRept_Positions_Net"

class Instrument:
    def __init__(self, asset_class_, name_, symbol_, code_, custom_lookback_):
        self.asset_class = asset_class_
        self.name = name_
        self.symbol = symbol_
        self.code = code_
        self.custom_lookback = custom_lookback_
        self.df = pd.DataFrame()

    def append(self, df):
        if self.df.empty:
            self.df = df
        else:
            self.df = pd.concat([self.df, df])

    def sort_by_date(self, col, ascending=True):
        self.df = self.df.sort_values(by=col, ascending=ascending)

    def __str__(self):
        return f"{self.name} {self.symbol} {self.code} {self.custom_lookback}"

class CotCmrIndexer:
    def __init__(self, real_test_data_dir='data/real_test_data'):
        self.real_test_data_dir = real_test_data_dir
        self.instruments = dict()
        self.supported_instruments = set()
        self.asset_class_map = dict()
        self.lookbacks = []
        self.years = []

        self.load_years()
        self.load_instruments()
        self.load_lookbacks()
        self.populate_instruments()
        self.calculate_weekly_data()
        self.export_to_csv()
        self.export_summary_results_to_csv()
        self.create_real_test_event_lists_with_custom_lookback()
        self.create_real_test_event_lists_with_net_positions()

    def load_years(self):
        with open("config/params.yaml", 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for year in yaml_data["years"]:
                self.years.append(year)

    def load_instruments(self):
        with open("config/params.yaml", 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for asset_class_dict in yaml_data["AssetClasses"]:
                for asset_class, assets in asset_class_dict.items():
                    self.asset_class_map[asset_class] = set()
                    for asset in assets:
                        code = symbol_code_map.cot_root_code_map[asset["Symbol"]]
                        if not code == "":
                            self.instruments[code] = Instrument(asset_class, asset["Name"], asset["Symbol"], code, asset["CustomLookbackWeeks"])
                            self.supported_instruments.add(code)
                            self.asset_class_map[asset_class].add(asset["Name"])

    def load_lookbacks(self):
        with open("config/params.yaml", 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for lb in yaml_data["lookbacks"]:
                self.lookbacks.append([lb[0], int(lb[1])])

    def populate_instruments(self):
        working_dir = os.getcwd()
        xls_data = 'data/xls_data'

        for year in self.years:
            data_file_name = f'{year}.xls'
            xl_path = os.path.join(working_dir, xls_data, data_file_name)

            # Load Excel file into pandas
            xl = pd.ExcelFile(xl_path)
            df = pd.read_excel(xl, usecols=[NAME, DATE, CODE, INTEREST, LARGE_LONG, LARGE_SHORT, COMM_LONG, COMM_SHORT, SMALL_LONG, SMALL_SHORT], index_col=0)

            for instrument in self.supported_instruments:
                self.instruments[instrument].append(df.loc[df[CODE] == instrument])

        for instrument in self.supported_instruments:
            # Sort by date and add a row count index
            self.instruments[instrument].sort_by_date(DATE, ascending=True)
            self.instruments[instrument].df.index = range(0, len(self.instruments[instrument].df))

    @staticmethod
    def calculate_cot_index(col_to_search, lb_idx, cur_idx):
        range_to_search = col_to_search[lb_idx:cur_idx+1]
        min_net = range_to_search.min()
        max_net = range_to_search.max()
        cur_net = col_to_search[cur_idx]
        result = 50
        if max_net != min_net:
            result = round((cur_net - min_net) / (max_net - min_net) * 100)
        return int(result)

    @staticmethod
    def process_lookback(lookback, df):
        lb_name = lookback[0]
        lb_weeks = lookback[1]
        col_header_name = lb_name + "-idx"

        for idx in range(len(df)):
            if lb_weeks < 0 or idx < lb_weeks:
                df.at[idx, "Comm-" + col_header_name] = -1
                df.at[idx, "LrgSpec-" + col_header_name] = -1
                df.at[idx, "SmlSpec-" + col_header_name] = -1
            else:
                lb_idx = idx - lb_weeks
                df.at[idx, "Comm-" + col_header_name] = CotCmrIndexer.calculate_cot_index(df[COMM_NET], lb_idx, idx)
                df.at[idx, "LrgSpec-" + col_header_name] = CotCmrIndexer.calculate_cot_index(df[LARGE_NET], lb_idx, idx)
                df.at[idx, "SmlSpec-" + col_header_name] = CotCmrIndexer.calculate_cot_index(df[SMALL_NET], lb_idx, idx)

    def calculate_weekly_data(self):
        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df
            name = self.instruments[instrument].name

            # Add new columns for net positions
            df.insert(df.columns.get_loc(COMM_SHORT) + 1, COMM_NET, df[COMM_LONG] - df[COMM_SHORT])
            df.insert(df.columns.get_loc(LARGE_SHORT) + 1, LARGE_NET, df[LARGE_LONG] - df[LARGE_SHORT])
            df.insert(df.columns.get_loc(SMALL_SHORT) + 1, SMALL_NET, df[SMALL_LONG] - df[SMALL_SHORT])

            CotCmrIndexer.process_lookback(["custom", self.instruments[instrument].custom_lookback], df)
            for lookback in self.lookbacks:
                CotCmrIndexer.process_lookback(lookback, df)

    def export_to_csv(self):
        working_dir = os.getcwd()
        csv_data_detailed = 'data/csv_data/detailed'
        csv_data_summary = 'data/csv_data/summary'
        os.makedirs(csv_data_detailed, exist_ok=True)
        os.makedirs(csv_data_summary, exist_ok=True)

        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df
            name = self.instruments[instrument].name
            data_file_name = f'{name}.csv'
            detailed_csv_path = os.path.join(working_dir, csv_data_detailed, data_file_name)
            summary_csv_path = os.path.join(working_dir, csv_data_summary, "summary_" + data_file_name)

            df.to_csv(detailed_csv_path, sep=",", index=True, header=True)
            summary_df = pd.DataFrame()
            summary_df["Date"] = df[DATE]
            summary_df["Code"] = df[CODE]
            summary_df["OpenInterest"] = df[INTEREST]
            summary_df["CommercialNet"] = df[COMM_NET]
            summary_df["LargeSpecNet"] = df[LARGE_NET]
            summary_df["SmallSpecNet"] = df[SMALL_NET]

            # Grab index values
            index_cols = [col for col in df.columns if "-idx" in col]
            for col in index_cols:
                summary_df[col] = df[col]
            summary_df.to_csv(summary_csv_path, sep=",", index=False, header=True)

    def export_summary_results_to_csv(self):
        working_dir = os.getcwd()
        csv_data = 'data/csv_data'
        os.makedirs(csv_data, exist_ok=True)
        summary_csv_path = os.path.join(working_dir, csv_data, "positioning_summary.csv")

        cols = ['Date', 'Symbol', 'Name', 'Commercials', 'Large Specs', 'Small Specs']
        positioning_df = pd.DataFrame(columns=cols)

        for asset in self.asset_class_map:
            instruments = self.get_assets_for_asset_class(asset)
            for instrument_name in instruments:
                instrument = self.get_instrument_from_name(instrument_name)
                symbol = instrument.symbol
                name = instrument.name
                df = instrument.df
                date = df.iloc[-1][DATE].date()
                comm_idx = df.iloc[-1]['Comm-custom-idx']
                lrg_idx = df.iloc[-1]['LrgSpec-custom-idx']
                sml_idx = df.iloc[-1]['SmlSpec-custom-idx']

                new_df = pd.DataFrame([[date, symbol, name, comm_idx, lrg_idx, sml_idx]], columns=positioning_df.columns)
                if positioning_df.empty:
                    positioning_df = new_df
                else:
                    positioning_df = pd.concat([positioning_df, new_df])

        positioning_df.to_csv(summary_csv_path, sep=",", index=False, header=True)

    def create_real_test_event_lists_with_custom_lookback(self):
        # Event List format: https://mhptrading.com/docs/topics/idh-topic490.htm
        # The first row of the file must contain column names from the following list:
        # •Symbol – the symbol for which the event occurred
        # •Date – the date of the event
        # •Time – the time of the event (optional)
        # •Type – any numeric code > 0 -- Here type 1 is Commercials, 2 is Large Specs, and 3 is Small Specs
        # •Value – any numeric value (e.g. dividend amount, or EPS, or index constituency flags)
        working_dir = os.getcwd()
        os.makedirs(self.real_test_data_dir, exist_ok=True)

        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df
            name = self.instruments[instrument].name
            data_file_name = f'{name}.csv'
            csv_path = os.path.join(working_dir, self.real_test_data_dir, data_file_name)
            real_test_csv_path = os.path.join(working_dir, self.real_test_data_dir, "RT_custom_index_event_list_" + data_file_name)

            # Add commercials
            commercial_df = pd.DataFrame()
            commercial_df["Date"] = df[DATE].apply(lambda x: x.date())
            commercial_df["Symbol"] = [self.instruments[instrument].symbol] * len(df[DATE])
            commercial_df["Type"] = 1  # Commercials
            commercial_df["index"] = df['Comm-custom-idx']
            commercial_df = commercial_df[commercial_df["index"] != -1]

            # Add row for large specs
            large_specs_df = pd.DataFrame()
            large_specs_df["Date"] = df[DATE].apply(lambda x: x.date())
            large_specs_df["Symbol"] = [self.instruments[instrument].symbol] * len(df[DATE])
            large_specs_df["Type"] = 2  # Large specs
            large_specs_df["index"] = df['LrgSpec-custom-idx']
            large_specs_df = large_specs_df[large_specs_df["index"] != -1]

            # Add small specs
            small_specs_df = pd.DataFrame()
            small_specs_df["Date"] = df[DATE].apply(lambda x: x.date())
            small_specs_df["Symbol"] = [self.instruments[instrument].symbol] * len(df[DATE])
            small_specs_df["Type"] = 3  # Small specs
            small_specs_df["index"] = df['SmlSpec-custom-idx']
            small_specs_df = small_specs_df[small_specs_df["index"] != -1]

            # Concatenate into one dataframe
            result_df = commercial_df
            result_df = pd.concat([result_df, large_specs_df])
            result_df = pd.concat([result_df, small_specs_df])
            result_df.to_csv(real_test_csv_path, sep=",", index=False, header=True)

    def create_real_test_event_lists_with_net_positions(self):
        # Event List format: https://mhptrading.com/docs/topics/idh-topic490.htm
        # The first row of the file must contain column names from the following list:
        # •Symbol – the symbol for which the event occurred
        # •Date – the date of the event
        # •Time – the time of the event (optional)
        # •Type – any numeric code > 0 -- Here type 1 is Commercials, 2 is Large Specs, and 3 is Small Specs
        # •Value – any numeric value (e.g. dividend amount, or EPS, or index constituency flags)
        working_dir = os.getcwd()
        os.makedirs(self.real_test_data_dir, exist_ok=True)

        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df
            name = self.instruments[instrument].name
            data_file_name = f'{name}.csv'
            csv_path = os.path.join(working_dir, self.real_test_data_dir, data_file_name)
            real_test_csv_path = os.path.join(working_dir, self.real_test_data_dir, "RT_net_position_event_list_" + data_file_name)

            # Add commercials
            commercial_df = pd.DataFrame()
            commercial_df["Date"] = df[DATE].apply(lambda x: x.date())
            commercial_df["Symbol"] = [self.instruments[instrument].symbol] * len(df[DATE])
            commercial_df["Type"] = 1  # Commercials
            commercial_df["Net"] = df[COMM_NET]
            commercial_df = commercial_df[commercial_df["Net"] != -1]

            # Add row for large specs
            large_specs_df = pd.DataFrame()
            large_specs_df["Date"] = df[DATE].apply(lambda x: x.date())
            large_specs_df["Symbol"] = [self.instruments[instrument].symbol] * len(df[DATE])
            large_specs_df["Type"] = 2  # Large specs
            large_specs_df["Net"] = df[LARGE_NET]
            large_specs_df = large_specs_df[large_specs_df["Net"] != -1]

            # Add small specs
            small_specs_df = pd.DataFrame()
            small_specs_df["Date"] = df[DATE].apply(lambda x: x.date())
            small_specs_df["Symbol"] = [self.instruments[instrument].symbol] * len(df[DATE])
            small_specs_df["Type"] = 3  # Small specs
            small_specs_df["Net"] = df[SMALL_NET]
            small_specs_df = small_specs_df[small_specs_df["Net"] != -1]

            # Concatenate into one dataframe
            result_df = commercial_df
            result_df = pd.concat([result_df, large_specs_df])
            result_df = pd.concat([result_df, small_specs_df])
            result_df.to_csv(real_test_csv_path, sep=",", index=False, header=True)

    def get_asset_classes(self):
        return list(self.asset_class_map)

    def get_default_asset_class(self):
        first_key = ""
        if not (len(self.asset_class_map)) == 0:
            first_key = next(iter(self.asset_class_map))
            if first_key is None:
                first_key = ""
        return first_key

    def get_assets_for_asset_class(self, asset_class):
        result = []
        if asset_class in self.asset_class_map:
            result = list(self.asset_class_map[asset_class])
        return result

    def get_instrument_names(self):
        result = []
        for code in self.instruments:
            result.append(self.instruments[code].symbol)
        return result

    def get_instrument_from_name(self, name):
        for inst_code in self.instruments:
            if self.instruments[inst_code].name == name:
                return self.instruments[inst_code]
        return None

    def get_instrument_from_symbol(self, symbol):
        for inst_code in self.instruments:
            if self.instruments[inst_code].symbol == symbol:
                return self.instruments[inst_code]
        return None

    def get_symbols_custom_index(self, name):
        instrument = self.get_instrument_from_name(name)
        if instrument is not None:
            if instrument is not None:
                df = instrument.df
                result = pd.DataFrame()
                result["date"] = df[DATE]
                result["comms"] = df['Comm-custom-idx']
                result["lrg"] = df['LrgSpec-custom-idx']
                result["sml"] = df['SmlSpec-custom-idx']
                result["comms_net"] = df[COMM_NET]
                result["lrg_net"] = df[LARGE_NET]
                result["sml_net"] = df[SMALL_NET]
                result = result[result["comms"] != -1]
                result.set_index("date", inplace=True)
                return result
        return None

    def get_positioning_table_by_asset_class(self, asset_classes):
        cols = ['Date', 'Symbol', 'Name', 'Commercials', 'Large Specs', 'Small Specs']
        positioning_df = pd.DataFrame(columns=cols)

        for asset in self.asset_class_map:
            if asset not in asset_classes:
                continue

            instruments = self.get_assets_for_asset_class(asset)
            for instrument_name in instruments:
                instrument = self.get_instrument_from_name(instrument_name)
                if not instrument is None:
                    symbol = instrument.symbol
                    name = instrument.name
                    df = instrument.df
                    date = df.iloc[-1][DATE].date()
                    comm_idx = df.iloc[-1]['Comm-custom-idx']
                    lrg_idx = df.iloc[-1]['LrgSpec-custom-idx']
                    sml_idx = df.iloc[-1]['SmlSpec-custom-idx']

                    new_df = pd.DataFrame([[date, symbol, name, comm_idx, lrg_idx, sml_idx]], columns=positioning_df.columns)
                    if positioning_df.empty:
                        positioning_df = new_df
                    else:
                        positioning_df = pd.concat([positioning_df, new_df])
        return positioning_df

    def get_positioning_table_by_symbol(self, requested_symbols):
        cols = ['Date', 'Symbol', 'Name', 'Commercials', 'Large Specs', 'Small Specs']
        positioning_df = pd.DataFrame(columns=cols)

        for instrument in self.supported_instruments:
            symbol = self.instruments[instrument].symbol
            if not symbol in requested_symbols:
                continue

            name = self.instruments[instrument].name
            df = self.instruments[instrument].df
            date = df.iloc[-1][DATE].date()
            comm_idx = df.iloc[-1]['Comm-custom-idx']
            lrg_idx = df.iloc[-1]['LrgSpec-custom-idx']
            sml_idx = df.iloc[-1]['SmlSpec-custom-idx']

            new_df = pd.DataFrame([[date, symbol, name, comm_idx, lrg_idx, sml_idx]], columns=positioning_df.columns)
            if positioning_df.empty:
                positioning_df = new_df
            else:
                positioning_df = pd.concat([positioning_df, new_df])

        return positioning_df
