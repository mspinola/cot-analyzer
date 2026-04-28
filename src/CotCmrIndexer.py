import logging
import math
import os
import pandas as pd
import yaml
import yfinance as yf

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

COMM_Z_SCORE = "Comm_Z_Score"
LARGE_Z_SCORE = "NonComm_Z_Score"
SMALL_Z_SCORE = "NonRept_Z_Score"

COMM_PCT_OI = "Comm_OI_Pct"
LARGE_PCT_OI = "NonComm_OI_Pct"
SMALL_PCT_OI = "NonRept_OI_Pct"

COMM_CORR = "Comm_Price_Spearman"
LARGE_CORR = "Large_Price_Spearman"
SMALL_CORR = "Small_Price_Spearman"

COMM_26_IDX = "Comm-26-idx"
CLOSING_PRICE = "Closing_Price"
WILLCO = "willco"


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
    def __init__(self, real_test_data_dir='data/real_test_data', params_dir='config/params.yaml'):
        self.real_test_data_dir = real_test_data_dir
        self.params_dir = params_dir
        self.instruments = dict()
        self.supported_instruments = set()
        self.asset_class_map = dict()
        self.lookbacks = []
        self.years = []
        self.paletter = []

        self.load_years()
        self.load_instruments()
        self.load_lookbacks()
        self.load_palette()
        self.populate_instruments()
        self.calculate_weekly_data()
        self.export_cot_data_to_csv()
        self.export_weekly_summary_results_to_csv()
        self.export_real_test_data_to_csv()

    def load_years(self):
        with open(self.params_dir, 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for year in yaml_data["years"]:
                self.years.append(year)

    def load_instruments(self):
        with open(self.params_dir, 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for asset_class_dict in yaml_data["AssetClasses"]:
                for asset_class, assets in asset_class_dict.items():
                    self.asset_class_map[asset_class] = set()
                    for asset in assets:
                        code = symbol_code_map.cot_root_code_map[asset["Symbol"]]
                        if not code == "":
                            self.instruments[code] = Instrument(
                                asset_class, asset["Name"], asset["Symbol"], code, asset["CustomLookbackWeeks"])
                            self.supported_instruments.add(code)
                            self.asset_class_map[asset_class].add(
                                asset["Name"])

    def load_lookbacks(self):
        with open(self.params_dir, 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for lb in yaml_data["lookbacks"]:
                self.lookbacks.append([lb[0], int(lb[1])])

    def load_palette(self):
        """Loads all palettes from params.yaml."""
        with open(self.params_dir, 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            self.palettes = yaml_data.get("palettes", {})
            # Set a default for initial load
            self.default_palette_name = list(self.palettes.keys())[
                0] if self.palettes else None

    def get_palette(self, name=None):
        """Returns a specific palette by name or the first one as default."""
        if not name or name not in self.palettes:
            return self.palettes.get(self.default_palette_name, ["#e70307", "#0000ff", "#ffff00", "#00FF00", "#E2E8F0"])
        return self.palettes[name]

    def get_palette_names(self):
        """Returns a list of available palette names for the dropdown."""
        return list(self.palettes.keys())

    def populate_instruments(self):
        working_dir = os.getcwd()
        xls_data = 'data/xls_data'

        for year in self.years:
            data_file_name = f'{year}.xls'
            xl_path = os.path.join(working_dir, xls_data, data_file_name)

            # Load Excel file into pandas
            xl = pd.ExcelFile(xl_path)
            df = pd.read_excel(xl, usecols=[NAME, DATE, CODE, INTEREST, LARGE_LONG,
                               LARGE_SHORT, COMM_LONG, COMM_SHORT, SMALL_LONG, SMALL_SHORT], index_col=0)

            for instrument in self.supported_instruments:
                self.instruments[instrument].append(
                    df.loc[df[CODE] == instrument])

        for instrument in self.supported_instruments:
            # Sort by date and add a row count index
            self.instruments[instrument].sort_by_date(DATE, ascending=True)
            self.instruments[instrument].df.index = range(
                0, len(self.instruments[instrument].df))

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
                df.at[idx, "Comm-" + col_header_name] = None
                df.at[idx, "LrgSpec-" + col_header_name] = None
                df.at[idx, "SmlSpec-" + col_header_name] = None
                df.at[idx, COMM_26_IDX] = None
            else:
                lb_idx = idx - lb_weeks
                df.at[idx, "Comm-" + col_header_name] = CotCmrIndexer.calculate_cot_index(
                    df[COMM_NET], lb_idx, idx)
                df.at[idx, "LrgSpec-" + col_header_name] = CotCmrIndexer.calculate_cot_index(
                    df[LARGE_NET], lb_idx, idx)
                df.at[idx, "SmlSpec-" + col_header_name] = CotCmrIndexer.calculate_cot_index(
                    df[SMALL_NET], lb_idx, idx)

                # Always calculate the 26-week commercial Index for use in the IW process, even if the lookback being processed is not 26 weeks
                if idx < 26:
                    df.at[idx, COMM_26_IDX] = None
                else:
                    df.at[idx, COMM_26_IDX] = CotCmrIndexer.calculate_cot_index(
                        df[COMM_NET], idx - 26, idx)

    @staticmethod
    def is_commodity(asset_class):
        return asset_class.startswith("Energ") or asset_class.startswith("Grain") or asset_class.startswith("Metal") or asset_class.startswith("Soft")

    def retrieve_report_date_closing_prices(self, instrument):
        df = instrument.df
        symbol = instrument.symbol
        ticker = f"{symbol}=F"  # Yahoo Finance ticker format for futures contracts

        try:
            # Fetch and Merge Closing Price for the Report Date
            logging.debug(f"Retrieving closing prices for {symbol} from Yahoo Finance...")
            start_date = f"{self.years[0]}-01-01"
            price_data = yf.download(ticker, start=start_date, interval="1d", progress=False)

            if not price_data.empty:
                # Clean the price data
                if isinstance(price_data.columns, pd.MultiIndex):
                    price_series = price_data['Close'][ticker]
                else:
                    price_series = price_data['Close']

                price_df = pd.DataFrame(price_series).rename(columns={'Close': 'Report_Date_Price'})
                # Convert price index to datetime and force nanosecond resolution
                price_df.index = pd.to_datetime(price_df.index).tz_localize(None).astype('datetime64[ns]')

                # Ensure COT dates are datetime and force matching nanosecond resolution
                df[DATE] = pd.to_datetime(df[DATE]).dt.tz_localize(None).astype('datetime64[ns]')
                logging.debug(f"Successfully retrieved price data for {symbol} with {len(price_df)} records.")

                # Merge price data into the main dataframe based on the DATE column
                # Use 'forward' to find the closest next trading day if a Tuesday was a holiday
                merged = pd.merge_asof(
                    df.sort_values(DATE),
                    price_df.sort_values(by=price_df.index.name or 'Date'),
                    left_on=DATE,
                    right_index=True,
                    direction='forward'
                )
                instrument.df[CLOSING_PRICE] = merged[ticker]  # Add the closing price to the instrument's dataframe

                # Refresh the local 'df' reference after the merge
                # df = instrument.df
                logging.info(f"Integrated report-date price for {symbol}")
            else:
                instrument.df[CLOSING_PRICE] = None
                logging.warning(f"No price data found for {ticker}")
        except Exception as e:
            logging.error(f"Error fetching price for {symbol}: {e}")

    def calculate_willco(self, lb_weeks, df):
        for idx in range(len(df)):
            asset_class = self.get_instrument_from_code(df[CODE][idx]).asset_class
            if not CotCmrIndexer.is_commodity(asset_class) or lb_weeks < 0 or idx < lb_weeks:
                df.at[idx, WILLCO] = None
            else:
                # We find the rolling min and max of the Commercial Normalized Net position
                oi_min = df[COMM_PCT_OI].iloc[idx+1-lb_weeks:idx+1].min()
                oi_max = df[COMM_PCT_OI].iloc[idx+1-lb_weeks:idx+1].max()

                if math.isnan(oi_max) or math.isnan(oi_min):
                    df.at[idx, WILLCO] = None
                else:
                    # Adding a tiny epsilon to the denominator prevents division by zero
                    cur_normalized_net = df.at[idx, COMM_PCT_OI]
                    willco = int((cur_normalized_net - oi_min) / (oi_max - oi_min + 1e-9) * 100)
                    df.at[idx, WILLCO] = willco


    def calculate_weekly_data(self):
        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df

            # Add new columns for net positions
            df[COMM_NET] = df[COMM_LONG] - df[COMM_SHORT]
            df[LARGE_NET] = df[LARGE_LONG] - df[LARGE_SHORT]
            df[SMALL_NET] = df[SMALL_LONG] - df[SMALL_SHORT]

            # Add new columns for position as percent of open interest
            # Adding epsilon (1e-9) to denominator prevents division by zero
            df[COMM_PCT_OI] = round((df[COMM_NET] / (df[INTEREST] + 1e-9)) * 100, 0)
            df[LARGE_PCT_OI] = round((df[LARGE_NET] / (df[INTEREST] + 1e-9)) * 100, 0)
            df[SMALL_PCT_OI] = round((df[SMALL_NET] / (df[INTEREST] + 1e-9)) * 100, 0)

            CotCmrIndexer.process_lookback(
                ["custom", self.instruments[instrument].custom_lookback], df)
            for lookback in self.lookbacks:
                CotCmrIndexer.process_lookback(lookback, df)

            self.retrieve_report_date_closing_prices(self.instruments[instrument])

            corr_window = 26
            if CLOSING_PRICE in df.columns:
                logging.debug(f"Calculating Rolling Spearman Correlation for {self.instruments[instrument].symbol}...")

                # Calculate the rank of the price and position within the rolling window
                price_rank = df[CLOSING_PRICE].rolling(window=corr_window).rank()
                comm_pos_rank = df[COMM_NET].rolling(window=corr_window).rank()
                lrg_pos_rank = df[LARGE_NET].rolling(window=corr_window).rank()
                sml_pos_rank = df[SMALL_NET].rolling(window=corr_window).rank()

                # Pearson correlation of the ranks = Spearman correlation
                # We apply a rolling correlation to the already-ranked series
                df[COMM_CORR] = price_rank.rolling(window=corr_window).corr(comm_pos_rank)
                df[LARGE_CORR] = price_rank.rolling(window=corr_window).corr(lrg_pos_rank)
                df[SMALL_CORR] = price_rank.rolling(window=corr_window).corr(sml_pos_rank)

                # Optional: Fill NaNs for the initial window period to avoid plotting artifacts
                df[COMM_CORR] = df[COMM_CORR].fillna(0)
                df[LARGE_CORR] = df[LARGE_CORR].fillna(0)
                df[SMALL_CORR] = df[SMALL_CORR].fillna(0)
            else:
                df[COMM_CORR] = 0
                df[LARGE_CORR] = 0
                df[SMALL_CORR] = 0

            z_window = 52
            # Commercials Z-Score
            comm_mean = df[COMM_NET].rolling(window=z_window).mean()
            comm_std = df[COMM_NET].rolling(window=z_window).std()
            df[COMM_Z_SCORE] = (df[COMM_NET] - comm_mean) / comm_std

            # Large Speculators Z-Score
            lrg_mean = df[LARGE_NET].rolling(window=z_window).mean()
            lrg_std = df[LARGE_NET].rolling(window=z_window).std()
            df[LARGE_Z_SCORE] = (df[LARGE_NET] - lrg_mean) / lrg_std

            # Small Speculators Z-Score
            sml_mean = df[SMALL_NET].rolling(window=z_window).mean()
            sml_std = df[SMALL_NET].rolling(window=z_window).std()
            df[SMALL_Z_SCORE] = (df[SMALL_NET] - sml_mean) / sml_std

            # Handle initial NaNs to keep the plots clean
            df[[COMM_Z_SCORE, LARGE_Z_SCORE, SMALL_Z_SCORE]] = df[[COMM_Z_SCORE, LARGE_Z_SCORE, SMALL_Z_SCORE]].fillna(0)

            self.calculate_willco(26, df)

    def collect_symbol_summary_results(self, instrument):
        df = self.instruments[instrument].df
        symbol = self.instruments[instrument].symbol

        # Construct summary dataframe with only relevant columns for the summary csv
        summary_df = pd.DataFrame()
        summary_df["Date"] = df[DATE]
        summary_df["Symbol"] = symbol
        summary_df["COMM_26_IDX"] = df[COMM_26_IDX]
        summary_df["OpenInterest"] = df[INTEREST]
        summary_df["CommercialNet"] = df[COMM_NET]
        summary_df["LargeSpecNet"] = df[LARGE_NET]
        summary_df["SmallSpecNet"] = df[SMALL_NET]
        summary_df["WillCo"] = df[WILLCO]
        summary_df["ClosingPrice"] = df[CLOSING_PRICE]

        # Grab index values
        index_cols = [col for col in df.columns if "-idx" in col]
        for col in index_cols:
            summary_df[col] = df[col]
        return summary_df

    def collect_symbol_detailed_results(self, instrument):
        # Construct detailed dataframe with all columns
        df = self.instruments[instrument].df
        detailed_df = df.copy()
        return detailed_df

    def export_cot_data_to_csv(self):
        working_dir = os.getcwd()
        csv_data_detailed = 'data/csv_data/detailed'
        csv_data_summary = 'data/csv_data/summary'
        os.makedirs(csv_data_detailed, exist_ok=True)
        os.makedirs(csv_data_summary, exist_ok=True)

        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df
            symbol = self.instruments[instrument].symbol

            data_file_name = f'{symbol}.csv'
            detailed_csv_path = os.path.join(
                working_dir, csv_data_detailed, "detailed_" + data_file_name)
            summary_csv_path = os.path.join(
                working_dir, csv_data_summary, "summary_" + data_file_name)

            # Write everything to the detailed csv
            df.to_csv(detailed_csv_path, sep=",", index=True, header=True)

            # Construct summary dataframe with only relevant columns for the summary csv
            summary_df = self.collect_symbol_summary_results(instrument)
            summary_df.to_csv(summary_csv_path, sep=",",
                              index=False, header=True)

    def export_weekly_summary_results_to_csv(self):
        working_dir = os.getcwd()
        csv_data = 'data/csv_data'
        os.makedirs(csv_data, exist_ok=True)
        summary_csv_path = os.path.join(
            working_dir, csv_data, "positioning_summary.csv")

        cols = ['Date', 'Symbol', 'Name',
                'Commercials', 'Large Specs', 'Small Specs']
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

                new_df = pd.DataFrame(
                    [[date, symbol, name, comm_idx, lrg_idx, sml_idx]], columns=positioning_df.columns)
                if positioning_df.empty:
                    positioning_df = new_df
                else:
                    positioning_df = pd.concat([positioning_df, new_df])

        positioning_df.to_csv(summary_csv_path, sep=",",
                              index=False, header=True)

    def export_real_test_data_to_csv(self):
        # Event List format: https://mhptrading.com/docs/topics/idh-topic490.htm
        # The first row of the file must contain column names from the following list:
        # •Symbol – the symbol for which the event occurred
        # •Date – the date of the event
        # •Time – the time of the event (optional)
        # •Type – any numeric code > 0 --
        #         Here type 1 is Commercials Index, 2 is Large Specs Index, and 3 is Small Specs Index
        #              type 4 is Commercials Net Position, 5 is Large Specs Net Position, and 6 is Small Specs Net Position
        # •Value – any numeric value (e.g. dividend amount, or EPS, or index constituency flags)
        working_dir = os.getcwd()
        real_test_data_dir = self.real_test_data_dir
        os.makedirs(real_test_data_dir, exist_ok=True)

        for instrument in self.supported_instruments:
            symbol = self.instruments[instrument].symbol
            lb = self.instruments[instrument].custom_lookback
            data_file_name = f'{symbol}.csv'
            real_test_csv_path = os.path.join(
                working_dir, real_test_data_dir, "RT_event_list_lb_" + str(lb) + "_" + data_file_name)
            real_test_df = self.create_real_test_event_asset_list(instrument)
            real_test_df.to_csv(real_test_csv_path, sep=",",
                                index=True, header=True)

    def create_real_test_event_asset_list(self, instrument):
        df = self.instruments[instrument].df
        #
        # Indexes
        #
        # Add commercials
        commercial_idx_df = pd.DataFrame()
        commercial_idx_df["Date"] = df[DATE].apply(lambda x: x.date())
        commercial_idx_df["Symbol"] = [
            self.instruments[instrument].symbol] * len(df[DATE])
        commercial_idx_df["Type"] = 1  # Commercials index
        commercial_idx_df["Value"] = df['Comm-custom-idx']
        commercial_idx_df = commercial_idx_df[commercial_idx_df["Value"] != -1]

        # Add large specs
        large_specs_idx_df = pd.DataFrame()
        large_specs_idx_df["Date"] = df[DATE].apply(lambda x: x.date())
        large_specs_idx_df["Symbol"] = [
            self.instruments[instrument].symbol] * len(df[DATE])
        large_specs_idx_df["Type"] = 2  # Large specs index
        large_specs_idx_df["Value"] = df['LrgSpec-custom-idx']
        large_specs_idx_df = large_specs_idx_df[large_specs_idx_df["Value"] != -1]

        # Add small specs
        small_specs_idx_df = pd.DataFrame()
        small_specs_idx_df["Date"] = df[DATE].apply(lambda x: x.date())
        small_specs_idx_df["Symbol"] = [
            self.instruments[instrument].symbol] * len(df[DATE])
        small_specs_idx_df["Type"] = 3  # Small specs index
        small_specs_idx_df["Value"] = df['SmlSpec-custom-idx']
        small_specs_idx_df = small_specs_idx_df[small_specs_idx_df["Value"] != -1]

        #
        # Net Positions
        #
        # Add commercials
        commercial_pos_df = pd.DataFrame()
        commercial_pos_df["Date"] = df[DATE].apply(lambda x: x.date())
        commercial_pos_df["Symbol"] = [
            self.instruments[instrument].symbol + "_B"] * len(df[DATE])
        commercial_pos_df["Type"] = 4  # Commercials net position
        commercial_pos_df["Value"] = df[COMM_NET]
        commercial_pos_df = commercial_pos_df[commercial_pos_df["Value"] != -1]

        # Add large specs
        large_specs_pos_df = pd.DataFrame()
        large_specs_pos_df["Date"] = df[DATE].apply(lambda x: x.date())
        large_specs_pos_df["Symbol"] = [
            self.instruments[instrument].symbol + "_B"] * len(df[DATE])
        large_specs_pos_df["Type"] = 5  # Large specs net position
        large_specs_pos_df["Value"] = df[LARGE_NET]
        large_specs_pos_df = large_specs_pos_df[large_specs_pos_df["Value"] != -1]

        # Add small specs
        small_specs_pos_df = pd.DataFrame()
        small_specs_pos_df["Date"] = df[DATE].apply(lambda x: x.date())
        small_specs_pos_df["Symbol"] = [
            self.instruments[instrument].symbol + "_B"] * len(df[DATE])
        small_specs_pos_df["Type"] = 6  # Small specs net position
        small_specs_pos_df["Value"] = df[SMALL_NET]
        small_specs_pos_df = small_specs_pos_df[small_specs_pos_df["Value"] != -1]

        # Concatenate into one dataframe
        result_df = commercial_idx_df
        result_df = pd.concat([result_df, large_specs_idx_df])
        result_df = pd.concat([result_df, small_specs_idx_df])
        result_df = pd.concat([result_df, large_specs_pos_df])
        result_df = pd.concat([result_df, large_specs_pos_df])
        result_df = pd.concat([result_df, small_specs_pos_df])

        return result_df

    def get_asset_classes(self):
        return list(self.asset_class_map)

    def get_default_asset_class(self):
        first_key = ""
        if not (len(self.asset_class_map)) == 0:
            if 'Equities' in self.asset_class_map:
                return 'Equities'

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

    def get_instrument_symbol_from_name(self, name):
        for code in self.instruments:
            if self.instruments[code].name == name:
                return self.instruments[code].symbol
        return None

    def get_instrument_from_code(self, code):
        if code in self.instruments:
            return self.instruments[code]
        return None

    def get_instrument_code_from_name(self, name):
        for code in self.instruments:
            if self.instruments[code].name == name:
                return code
        return None

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
            df = instrument.df
            result = pd.DataFrame()
            result["date"] = df[DATE]

            result["comms"] = df['Comm-custom-idx']
            result["lrg"] = df['LrgSpec-custom-idx']
            result["sml"] = df['SmlSpec-custom-idx']

            result["comms_net"] = df[COMM_NET]
            result["lrg_net"] = df[LARGE_NET]
            result["sml_net"] = df[SMALL_NET]

            result["comm_oi_pct"] = df[COMM_PCT_OI]
            result["lrg_oi_pct"] = df[LARGE_PCT_OI]
            result["sml_oi_pct"] = df[SMALL_PCT_OI]

            result["comm_spearman"] = df[COMM_CORR]
            result["lrg_spearman"] = df[LARGE_CORR]
            result["sml_spearman"] = df[SMALL_CORR]

            result["comms-z"] = df[COMM_Z_SCORE]
            result["lrg-z"] = df[LARGE_Z_SCORE]
            result["sml-z"] = df[SMALL_Z_SCORE]

            result["oi"] = df[INTEREST]
            result["price"] = df[CLOSING_PRICE]

            result.set_index("date", inplace=True)
            return result
        return None

    def get_positioning_table_by_asset_class(self, asset_classes):
        cols = ['Date', 'Asset Class', 'Symbol', 'Name',
                'Commercials', 'Large Specs', 'Small Specs', 'Comms (26-Week)', 'Willco']
        positioning_df = pd.DataFrame(columns=cols)

        for asset in self.asset_class_map:
            if asset not in asset_classes:
                continue

            instruments = self.get_assets_for_asset_class(asset)
            for instrument_name in instruments:
                instrument = self.get_instrument_from_name(instrument_name)
                if not instrument is None:
                    symbol = instrument.symbol
                    asset_class = instrument.asset_class
                    name = instrument.name
                    df = instrument.df
                    date = df.iloc[-1][DATE].date()
                    comm_idx = df.iloc[-1]['Comm-custom-idx']
                    lrg_idx = df.iloc[-1]['LrgSpec-custom-idx']
                    sml_idx = df.iloc[-1]['SmlSpec-custom-idx']

                    iwIndex = df.iloc[-1][COMM_26_IDX]
                    willco = df.iloc[-1][WILLCO]

                    new_df = pd.DataFrame(
                        [[date, asset_class, symbol, name, comm_idx, lrg_idx, sml_idx, iwIndex, willco]], columns=positioning_df.columns)
                    if positioning_df.empty:
                        positioning_df = new_df
                    else:
                        positioning_df = pd.concat([positioning_df, new_df])
        return positioning_df

    def get_positioning_table_by_symbol(self, requested_symbols):
        cols = ['Date', 'Symbol', 'Name',
                'Commercials', 'Large Specs', 'Small Specs']
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

            new_df = pd.DataFrame(
                [[date, symbol, name, comm_idx, lrg_idx, sml_idx]], columns=positioning_df.columns)
            if positioning_df.empty:
                positioning_df = new_df
            else:
                positioning_df = pd.concat([positioning_df, new_df])

        return positioning_df


    def get_asset_class_z_score_heat(self, asset_class):
        """Returns the latest Z-scores for all assets in a class."""
        assets = self.get_assets_for_asset_class(asset_class)
        heat_data = []

        for name in assets:
            instrument = self.get_instrument_from_name(name)
            if instrument is not None and not instrument.df.empty:
                df = instrument.df
                # Get the most recent non-NaN Z-scores
                latest = df.iloc[-1]
                heat_data.append({
                    "Asset": name,
                    "Commercials": latest.get("Comm_Z_Score", 0),
                    "Large Specs": latest.get("NonComm_Z_Score", 0),
                    "Small Specs": latest.get("NonRept_Z_Score", 0)
                })

        return pd.DataFrame(heat_data)

    def get_asset_class_index_heat(self, asset_class):
        """Returns the latest Index for all assets in a class."""
        assets = self.get_assets_for_asset_class(asset_class)
        heat_data = []

        for name in assets:
            instrument = self.get_instrument_from_name(name)
            if instrument is not None and not instrument.df.empty:
                df = instrument.df
                # Get the most recent non-NaN Z-scores
                latest = df.iloc[-1]
                heat_data.append({
                    "Asset": name,
                    "Commercials": latest.get("Comm-custom-idx", 0),
                    "Large Specs": latest.get("LrgSpec-custom-idx", 0),
                    "Small Specs": latest.get("SmlSpec-custom-idx", 0)
                })

        return pd.DataFrame(heat_data)
