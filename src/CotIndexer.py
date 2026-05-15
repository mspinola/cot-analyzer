import constants as const
import metrics

import os
import pandas as pd
import yaml
import yfinance as yf

import CotSymbolCodeMap as symbol_code_map
import utils

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


class CotIndexer:
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
            df = pd.read_excel(xl, usecols=[const.MARKET_NAME_XLS, const.REPORT_DATE_XLS,
                                            const.CONTRACT_CODE_XLS, const.OPEN_INTEREST_XLS,
                                            const.COMM_LONG_POS_XLS, const.COMM_SHORT_POS_XLS,
                                            const.LARGE_LONG_POS_XLS, const.LARGE_SHORT_POS_XLS,
                                            const.SMALL_LONG_POS_XLS, const.SMALL_SHORT_POS_XLS
                                            ], index_col=0)

            for instrument in self.supported_instruments:
                self.instruments[instrument].append(
                    df.loc[df[const.CONTRACT_CODE_XLS] == instrument])

        for instrument in self.supported_instruments:
            # Sort by date and add a row count index
            self.instruments[instrument].sort_by_date(const.REPORT_DATE_XLS, ascending=True)
            self.instruments[instrument].df.index = range(
                0, len(self.instruments[instrument].df))


    @staticmethod
    def estimate_current_gap_positions(df, symbol, COMM_CORR, LARGE_CORR, SMALL_CORR):
        """Estimates the net position change from Tuesday close to Friday."""
        if df.empty:
            return

        # Tuesday's official data
        last_row = df.iloc[-1]
        tue_price = last_row[const.CLOSING_PRICE]
        tue_oi = last_row[const.OPEN_INTEREST_XLS]
        if tue_price == 0:
            df.at[df.index[-1], const.COMM_NET_EST] = 0
            df.at[df.index[-1], const.LARGE_NET_EST] = 0
            df.at[df.index[-1], const.SMALL_NET_EST] = 0
            return

        # Fetch current data (Wed-Fri)
        # symbol = instrument.symbol
        ticker = f"{symbol}=F"
        try:
            # Fetch last 5 days to ensure we capture the Tue-Fri window
            current_data = yf.download(ticker, period="5d", interval="1d", progress=False)
            if current_data.empty:
                df.at[df.index[-1], const.COMM_NET_EST] = 0
                df.at[df.index[-1], const.LARGE_NET_EST] = 0
                df.at[df.index[-1], const.SMALL_NET_EST] = 0
                return

            YAHOO_PRICE_TOKEN = 'Close'
            YAHOO_VOLUME_TOKEN = 'Volume'
            YAHOO_OI_TOKEN = 'Open Interest'
            if isinstance(current_data.columns, pd.MultiIndex):
                latest_price = current_data[YAHOO_PRICE_TOKEN][ticker].iloc[-1]
                price_change_pct = (latest_price - tue_price) / tue_price
                total_volume_since_tue = current_data[YAHOO_VOLUME_TOKEN][ticker].sum()
                latest_oi = current_data[YAHOO_OI_TOKEN][ticker].iloc[-1] if YAHOO_OI_TOKEN in current_data else tue_oi
                oi_net_change_pct = (latest_oi - tue_oi) / tue_oi if tue_oi else 0
            else:
                latest_price = current_data[YAHOO_PRICE_TOKEN].iloc[-1]
                price_change_pct = (latest_price - tue_price) / tue_price
                total_volume_since_tue = current_data[YAHOO_VOLUME_TOKEN].sum()
                latest_oi = current_data[YAHOO_OI_TOKEN].iloc[-1] if YAHOO_OI_TOKEN in current_data else tue_oi
                oi_net_change_pct = (latest_oi - tue_oi) / tue_oi if tue_oi else 0

            # Calculate Volume Intensity:
            # How much 'churn' has occurred relative to the total open contracts?
            # A value of 1.0 means the equivalent of the entire Tuesday OI has traded.
            volume_intensity = total_volume_since_tue / tue_oi if tue_oi else 0

            # The Estimation Multiplier:
            # Intensity (how much was traded) * Conviction (did the pool grow?)
            # We cap Volume Intensity at a reasonable multiplier (e.g., 0.5) to avoid
            # unrealistic swings on hyper-liquid days.
            estimation_multiplier = min(volume_intensity, 0.5) * (1 + oi_net_change_pct)

            # Apply the delta to the Tuesday net position
            for net_col, corr_col in [
                (const.COMM_NET, COMM_CORR),
                (const.LARGE_NET, LARGE_CORR),
                (const.SMALL_NET, SMALL_CORR)
            ]:
                est_col = f"{net_col} Est"

                # The 'Delta' is the Tuesday Position size * Price Move * Correlation * Our Volume-Weighted Multiplier
                delta = abs(last_row[net_col]) * price_change_pct * last_row[corr_col] * estimation_multiplier
                df.at[df.index[-1], est_col] = round(last_row[net_col] + delta, 0)

        except Exception as e:
            utils.cot_logger.error(f"Error estimating gap for {symbol}: {e}")
            df.at[df.index[-1], const.COMM_NET_EST] = 0
            df.at[df.index[-1], const.LARGE_NET_EST] = 0
            df.at[df.index[-1], const.SMALL_NET_EST] = 0

        utils.cot_logger.debug(f"Estimated positions for {symbol} - Comm: {df.at[df.index[-1], const.COMM_NET_EST]}, Large: {df.at[df.index[-1], const.LARGE_NET_EST]}, Small: {df.at[df.index[-1], const.SMALL_NET_EST]}")


    @staticmethod
    def process_lookback(lookback, symbol, df):
        lb_name = lookback[0]
        lb_weeks = lookback[1]
        idx_col_header_name = "Custom Idx" if lb_name == "Custom" else str(lb_weeks) + " Idx"
        norm_idx_col_header_name = "Custom Norm Idx" if lb_name == "Custom" else str(lb_weeks) + " Norm Idx"
        willco_col_header_name = "Custom" if lb_name == "Custom" else str(lb_weeks)

        for idx in range(len(df)):
            COMM_IDX = "Comm " + idx_col_header_name
            LRG_IDX = "Lrg Spec " + idx_col_header_name
            SML_IDX = "Sml Spec " + idx_col_header_name
            COMM_NORM_IDX = "Comm " + norm_idx_col_header_name
            LRG_NORM_IDX = "Lrg Spec " + norm_idx_col_header_name
            SML_NORM_IDX = "Sml Spec " + norm_idx_col_header_name
            WILLCO = "WILLCO " + willco_col_header_name
            if lb_weeks < 0 or idx < lb_weeks:
                df.at[idx, COMM_IDX] = None
                df.at[idx, LRG_IDX] = None
                df.at[idx, SML_IDX] = None
                df.at[idx, COMM_NORM_IDX] = None
                df.at[idx, LRG_NORM_IDX] = None
                df.at[idx, SML_NORM_IDX] = None
                df.at[idx, WILLCO] = None
            else:
                lb_idx = idx - lb_weeks
                df.at[idx, COMM_IDX] = metrics.calculate_cot_index(df[const.COMM_NET], lb_idx, idx)
                df.at[idx, LRG_IDX] = metrics.calculate_cot_index(df[const.LARGE_NET], lb_idx, idx)
                df.at[idx, SML_IDX] = metrics.calculate_cot_index(df[const.SMALL_NET], lb_idx, idx)
                df.at[idx, COMM_NORM_IDX] = metrics.calculate_cot_index(df[const.COMM_NET_NORM], lb_idx, idx)
                df.at[idx, LRG_NORM_IDX] = metrics.calculate_cot_index(df[const.LARGE_NET_NORM], lb_idx, idx)
                df.at[idx, SML_NORM_IDX] = metrics.calculate_cot_index(df[const.SMALL_NET_NORM], lb_idx, idx)
                df.at[idx, WILLCO] = metrics.calculate_willco(df[const.COMM_PCT_OI], lb_idx, idx)

        # Z-Score
        zscore_col_header_name = "Custom Zscore" if lb_name == "Custom" else str(lb_weeks) + " Zscore"
        COMM_ZS = "Comm " + zscore_col_header_name
        LRG_ZS = "Lrg Spec " + zscore_col_header_name
        SML_ZS = "Sml Spec " + zscore_col_header_name
        df[COMM_ZS] = metrics.calculate_z_score(df[const.COMM_NET], lb_weeks)
        df[LRG_ZS] = metrics.calculate_z_score(df[const.LARGE_NET], lb_weeks)
        df[SML_ZS] = metrics.calculate_z_score(df[const.SMALL_NET], lb_weeks)
        df[COMM_ZS] = df[COMM_ZS].fillna(0)
        df[LRG_ZS] = df[LRG_ZS].fillna(0)
        df[SML_ZS] = df[SML_ZS].fillna(0)

        # Calculate Raw Tension: Large Spec Net / Abs(Commercial Net)
        # Avoid division by zero by adding a small epsilon
        raw_tension = df[const.LARGE_NET] / (df[const.COMM_NET].abs() + 1e-9)
        tension_col_header_name = "Custom" if lb_name == "Custom" else str(lb_weeks)
        TENSION_Z = "Tension Zscore " + tension_col_header_name
        df[TENSION_Z] = metrics.calculate_z_score(raw_tension, lb_weeks)
        df[TENSION_Z] = df[TENSION_Z].fillna(0)

        # Spearman Correlation
        spearman_header_name = "Custom Spearman" if lb_name == "Custom" else str(lb_weeks) + " Spearman"
        COMM_SPR = "Comm " + spearman_header_name
        LRG_SPR = "Lrg Spec " + spearman_header_name
        SML_SPR = "Sml Spec " + spearman_header_name
        if const.CLOSING_PRICE in df.columns:
            # Calculate the rank of the price and position within the rolling window
            price_rank = df[const.CLOSING_PRICE].rolling(window=lb_weeks).rank()
            comm_pos_rank = df[const.COMM_NET].rolling(window=lb_weeks).rank()
            lrg_pos_rank = df[const.LARGE_NET].rolling(window=lb_weeks).rank()
            sml_pos_rank = df[const.SMALL_NET].rolling(window=lb_weeks).rank()

            # Pearson correlation of the ranks = Spearman correlation
            # We apply a rolling correlation to the already-ranked series
            df[COMM_SPR] = price_rank.rolling(window=lb_weeks).corr(comm_pos_rank)
            df[LRG_SPR] = price_rank.rolling(window=lb_weeks).corr(lrg_pos_rank)
            df[SML_SPR] = price_rank.rolling(window=lb_weeks).corr(sml_pos_rank)

            df[COMM_SPR] = df[COMM_SPR].fillna(0)
            df[LRG_SPR] = df[LRG_SPR].fillna(0)
            df[SML_SPR] = df[SML_SPR].fillna(0)
        else:
            df[COMM_SPR] = 0
            df[LRG_SPR] = 0
            df[SML_SPR] = 0

        # Momentum Index
        momentum_idx_header_name = "Custom Move Idx" if lb_name == "Custom" else str(lb_weeks) + " Move Idx"
        idx_col_name = "Custom Idx" if lb_name == "Custom" else str(lb_weeks) + " Idx"
        COMM_MOVE = "Comm " + momentum_idx_header_name
        LRG_MOVE = "Lrg Spec " + momentum_idx_header_name
        SML_MOVE = "Sml Spec " + momentum_idx_header_name
        df[COMM_MOVE] = metrics.calculate_momentum_index(df["Comm " + idx_col_name])
        df[LRG_MOVE] = metrics.calculate_momentum_index(df["Lrg Spec " + idx_col_name])
        df[SML_MOVE] = metrics.calculate_momentum_index(df["Sml Spec " + idx_col_name])


    @staticmethod
    def retrieve_report_date_closing_prices(instrument, years):
        df = instrument.df
        symbol = instrument.symbol
        ticker = f"{symbol}=F"  # Yahoo Finance ticker format for futures contracts

        try:
            # Fetch and Merge Closing Price for the Report Date
            utils.cot_logger.debug(f"Retrieving closing prices for {symbol} from Yahoo Finance...")
            start_date = f"{years[0]}-01-01"
            price_data = yf.download(ticker, start=start_date, interval="1d", progress=False)
            YAHOO_PRICE_TOKEN = 'Close'

            if not price_data.empty:
                # Clean the price data
                if isinstance(price_data.columns, pd.MultiIndex):
                    price_series = price_data[YAHOO_PRICE_TOKEN][ticker]
                else:
                    price_series = price_data[YAHOO_PRICE_TOKEN]

                price_df = pd.DataFrame(price_series).rename(columns={YAHOO_PRICE_TOKEN: 'Report_Date_Price'})
                # Convert price index to datetime and force nanosecond resolution
                price_df.index = pd.to_datetime(price_df.index).tz_localize(None).astype('datetime64[ns]')

                # Ensure COT dates are datetime and force matching nanosecond resolution
                df[const.REPORT_DATE_XLS] = pd.to_datetime(df[const.REPORT_DATE_XLS]).dt.tz_localize(None).astype('datetime64[ns]')
                utils.cot_logger.debug(f"Successfully retrieved price data for {symbol} with {len(price_df)} records.")

                # Merge price data into the main dataframe based on the const.DATE column
                # Use 'forward' to find the closest next trading day if a Tuesday was a holiday
                merged = pd.merge_asof(
                    df.sort_values(const.REPORT_DATE_XLS),
                    price_df.sort_values(by=price_df.index.name or 'Date'),
                    left_on=const.REPORT_DATE_XLS,
                    right_index=True,
                    direction='forward'
                )
                instrument.df[const.CLOSING_PRICE] = merged[ticker]  # Add the closing price to the instrument's dataframe

                # Refresh the local 'df' reference after the merge
                utils.cot_logger.info(f"Integrated report-date price for {symbol}")
            else:
                instrument.df[const.CLOSING_PRICE] = None
                utils.cot_logger.warning(f"No price data found for {ticker}")
        except Exception as e:
            df[const.CLOSING_PRICE] = 0
            utils.cot_logger.error(f"Error fetching price for {symbol}: {e}")


    def calculate_weekly_data(self):
        for instrument in self.supported_instruments:
            df = self.instruments[instrument].df

            # Add new columns for net positions
            df[const.COMM_NET] = df[const.COMM_LONG_POS_XLS] - df[const.COMM_SHORT_POS_XLS]
            df[const.LARGE_NET] = df[const.LARGE_LONG_POS_XLS] - df[const.LARGE_SHORT_POS_XLS]
            df[const.SMALL_NET] = df[const.SMALL_LONG_POS_XLS] - df[const.SMALL_SHORT_POS_XLS]

            # Add new columns for net positions normalized by open interest
            df[const.COMM_NET_NORM] = df[const.COMM_NET] / (df[const.OPEN_INTEREST_XLS] + 1e-9)
            df[const.LARGE_NET_NORM] = df[const.LARGE_NET] / (df[const.OPEN_INTEREST_XLS] + 1e-9)
            df[const.SMALL_NET_NORM] = df[const.SMALL_NET] / (df[const.OPEN_INTEREST_XLS] + 1e-9)

            # We only estimate the last row (current week) since that's the only one that would have a gap between Tuesday and Friday
            df[const.COMM_NET_EST] = df[const.COMM_NET]
            df[const.LARGE_NET_EST] = df[const.LARGE_NET]
            df[const.SMALL_NET_EST] = df[const.SMALL_NET]

            # Add new columns for position as percent of open interest
            # Adding epsilon (1e-9) to denominator prevents division by zero
            df[const.COMM_PCT_OI] = round((df[const.COMM_NET] / (df[const.OPEN_INTEREST_XLS] + 1e-9)) * 100, 2)
            df[const.LARGE_PCT_OI] = round((df[const.LARGE_NET] / (df[const.OPEN_INTEREST_XLS] + 1e-9)) * 100, 2)
            df[const.SMALL_PCT_OI] = round((df[const.SMALL_NET] / (df[const.OPEN_INTEREST_XLS] + 1e-9)) * 100, 2)

            self.retrieve_report_date_closing_prices(self.instruments[instrument], self.years)

            CotIndexer.process_lookback(
                ["Custom", self.instruments[instrument].custom_lookback], self.instruments[instrument].symbol, df)
            for lookback in self.lookbacks:
                CotIndexer.process_lookback(lookback, self.instruments[instrument].symbol, df)

            # Check for sign change in Large Speculator Net Position
            df[const.LARGE_FLIP] = (df[const.LARGE_NET] * df[const.LARGE_NET].shift(1) < 0)

    def collect_symbol_summary_results(self, instrument):
        df = self.instruments[instrument].df

        # Construct summary dataframe with only relevant columns for the summary csv
        summary_df = pd.DataFrame()
        summary_df[const.DATE] = df[const.REPORT_DATE_XLS]
        summary_df[const.SYMBOL] = self.instruments[instrument].symbol
        summary_df[const.OPEN_INTEREST] = df[const.OPEN_INTEREST_XLS]
        summary_df[const.COMM_NET] = df[const.COMM_NET]
        summary_df[const.LARGE_NET] = df[const.LARGE_NET]
        summary_df[const.SMALL_NET] = df[const.SMALL_NET]
        summary_df[const.CLOSING_PRICE] = df[const.CLOSING_PRICE]

        # Grab index values
        index_cols = [col for col in df.columns if " Idx" in col]
        for col in index_cols:
            summary_df[col] = df[col]

        # Grab z-score values
        index_cols = [col for col in df.columns if " Zscore" in col]
        for col in index_cols:
            summary_df[col] = df[col]

        # Grab Spearman values
        index_cols = [col for col in df.columns if " Spearman" in col]
        for col in index_cols:
            summary_df[col] = df[col]

        # Grab WILLCO values
        index_cols = [col for col in df.columns if "WILLCO" in col]
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
            summary_df.to_csv(summary_csv_path, sep=",", index=False, header=True)

    def export_weekly_summary_results_to_csv(self):
        working_dir = os.getcwd()
        csv_data = 'data/csv_data'
        os.makedirs(csv_data, exist_ok=True)
        summary_csv_path = os.path.join(
            working_dir, csv_data, "positioning_summary.csv")

        cols = [const.DATE, const.SYMBOL, const.NAME,
                const.COMM_CUSTOM_IDX, const.LARGE_CUSTOM_IDX, const.SMALL_CUSTOM_IDX,
                const.COMM_26_IDX, const.LARGE_26_IDX, const.SMALL_26_IDX,
                const.COMM_52_IDX, const.LARGE_52_IDX, const.SMALL_52_IDX,
                const.COMM_CUSTOM_ZSCORE, const.LARGE_CUSTOM_ZSCORE, const.SMALL_CUSTOM_ZSCORE,
                const.COMM_26_ZSCORE, const.LARGE_26_ZSCORE, const.SMALL_26_ZSCORE,
                const.COMM_52_ZSCORE, const.LARGE_52_ZSCORE, const.SMALL_52_ZSCORE,
                const.COMM_CUSTOM_CORR, const.LARGE_CUSTOM_CORR, const.SMALL_CUSTOM_CORR,
                const.COMM_26_CORR, const.LARGE_26_CORR, const.SMALL_26_CORR,
                const.COMM_52_CORR, const.LARGE_52_CORR, const.SMALL_52_CORR,
                ]
        positioning_df = pd.DataFrame(columns=cols)

        for asset in self.asset_class_map:
            instruments = self.get_assets_for_asset_class(asset)
            for instrument_name in instruments:
                instrument = self.get_instrument_from_name(instrument_name)
                df = instrument.df

                new_df = pd.DataFrame(
                    [[df.iloc[-1][const.REPORT_DATE_XLS].date(), instrument.symbol, instrument.name,
                      df.iloc[-1][const.COMM_CUSTOM_IDX], df.iloc[-1][const.LARGE_CUSTOM_IDX], df.iloc[-1][const.SMALL_CUSTOM_IDX],
                      df.iloc[-1][const.COMM_26_IDX], df.iloc[-1][const.LARGE_26_IDX], df.iloc[-1][const.SMALL_26_IDX],
                      df.iloc[-1][const.COMM_52_IDX], df.iloc[-1][const.LARGE_52_IDX], df.iloc[-1][const.SMALL_52_IDX],

                      df.iloc[-1][const.COMM_CUSTOM_ZSCORE], df.iloc[-1][const.LARGE_26_ZSCORE], df.iloc[-1][const.SMALL_CUSTOM_ZSCORE],
                      df.iloc[-1][const.COMM_26_ZSCORE], df.iloc[-1][const.LARGE_26_ZSCORE], df.iloc[-1][const.SMALL_26_ZSCORE],
                      df.iloc[-1][const.COMM_52_ZSCORE], df.iloc[-1][const.LARGE_52_ZSCORE], df.iloc[-1][const.SMALL_52_ZSCORE],

                      df.iloc[-1][const.COMM_CUSTOM_CORR], df.iloc[-1][const.LARGE_CUSTOM_CORR], df.iloc[-1][const.SMALL_CUSTOM_CORR],
                      df.iloc[-1][const.COMM_26_CORR], df.iloc[-1][const.LARGE_26_CORR], df.iloc[-1][const.SMALL_26_CORR],
                      df.iloc[-1][const.COMM_52_CORR], df.iloc[-1][const.LARGE_52_CORR], df.iloc[-1][const.SMALL_52_CORR],
                      ]], columns=positioning_df.columns)
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
        commercial_idx_df[const.DATE] = df[const.REPORT_DATE_XLS].apply(lambda x: x.date())
        commercial_idx_df[const.SYMBOL] = [
            self.instruments[instrument].symbol] * len(df[const.REPORT_DATE_XLS])
        commercial_idx_df["Type"] = 1  # Commercials index
        commercial_idx_df["Value"] = df[const.COMM_CUSTOM_IDX]
        commercial_idx_df = commercial_idx_df[commercial_idx_df["Value"] != -1]

        # Add large specs
        large_specs_idx_df = pd.DataFrame()
        large_specs_idx_df[const.DATE] = df[const.REPORT_DATE_XLS].apply(lambda x: x.date())
        large_specs_idx_df[const.SYMBOL] = [
            self.instruments[instrument].symbol] * len(df[const.REPORT_DATE_XLS])
        large_specs_idx_df["Type"] = 2  # Large specs index
        large_specs_idx_df["Value"] = df[const.LARGE_CUSTOM_IDX]
        large_specs_idx_df = large_specs_idx_df[large_specs_idx_df["Value"] != -1]

        # Add small specs
        small_specs_idx_df = pd.DataFrame()
        small_specs_idx_df[const.DATE] = df[const.REPORT_DATE_XLS].apply(lambda x: x.date())
        small_specs_idx_df[const.SYMBOL] = [
            self.instruments[instrument].symbol] * len(df[const.REPORT_DATE_XLS])
        small_specs_idx_df["Type"] = 3  # Small specs index
        small_specs_idx_df["Value"] = df[const.SMALL_CUSTOM_IDX]
        small_specs_idx_df = small_specs_idx_df[small_specs_idx_df["Value"] != -1]

        #
        # Net Positions
        #
        # Add commercials
        commercial_pos_df = pd.DataFrame()
        commercial_pos_df[const.DATE] = df[const.REPORT_DATE_XLS].apply(lambda x: x.date())
        commercial_pos_df[const.SYMBOL] = [
            self.instruments[instrument].symbol + "_B"] * len(df[const.REPORT_DATE_XLS])
        commercial_pos_df["Type"] = 4  # Commercials net position
        commercial_pos_df["Value"] = df[const.COMM_NET]
        commercial_pos_df = commercial_pos_df[commercial_pos_df["Value"] != -1]

        # Add large specs
        large_specs_pos_df = pd.DataFrame()
        large_specs_pos_df[const.DATE] = df[const.REPORT_DATE_XLS].apply(lambda x: x.date())
        large_specs_pos_df[const.SYMBOL] = [
            self.instruments[instrument].symbol + "_B"] * len(df[const.REPORT_DATE_XLS])
        large_specs_pos_df["Type"] = 5  # Large specs net position
        large_specs_pos_df["Value"] = df[const.LARGE_NET]
        large_specs_pos_df = large_specs_pos_df[large_specs_pos_df["Value"] != -1]

        # Add small specs
        small_specs_pos_df = pd.DataFrame()
        small_specs_pos_df[const.DATE] = df[const.REPORT_DATE_XLS].apply(lambda x: x.date())
        small_specs_pos_df[const.SYMBOL] = [
            self.instruments[instrument].symbol + "_B"] * len(df[const.REPORT_DATE_XLS])
        small_specs_pos_df["Type"] = 6  # Small specs net position
        small_specs_pos_df["Value"] = df[const.SMALL_NET]
        small_specs_pos_df = small_specs_pos_df[small_specs_pos_df["Value"] != -1]

        # Concatenate into one dataframe
        result_df = commercial_idx_df
        result_df = pd.concat([result_df, large_specs_idx_df])
        result_df = pd.concat([result_df, small_specs_idx_df])
        result_df = pd.concat([result_df, large_specs_pos_df])
        result_df = pd.concat([result_df, large_specs_pos_df])
        result_df = pd.concat([result_df, small_specs_pos_df])

        return result_df

    def get_asset_classes(self, sort=True):
        classes = list(self.asset_class_map)
        if sort:
            classes.sort()
        return classes

    def get_default_asset_class(self):
        first_key = ""
        if not (len(self.asset_class_map)) == 0:
            if 'Equities' in self.asset_class_map:
                return 'Equities'

            first_key = next(iter(self.asset_class_map))
            if first_key is None:
                first_key = ""
        return first_key

    def get_assets_for_asset_class(self, asset_class, sort=True):
        result = []
        if asset_class in self.asset_class_map:
            result = list(self.asset_class_map[asset_class])
        if sort:
            result.sort()
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

    def get_symbols_data(self, name, lookback):
        instrument = self.get_instrument_from_name(name)
        if instrument is not None:
            idx_col_header_name = lookback + " Idx"
            COMM_IDX = "Comm " + idx_col_header_name
            LRG_IDX = "Lrg Spec " + idx_col_header_name
            SML_IDX = "Sml Spec " + idx_col_header_name

            norm_idx_col_header_name = lookback + " Norm Idx"
            COMM_NORM_IDX = "Comm " + norm_idx_col_header_name
            LRG_NORM_IDX = "Lrg Spec " + norm_idx_col_header_name
            SML_NORM_IDX = "Sml Spec " + norm_idx_col_header_name

            zscore_col_header_name = lookback + " Zscore"
            COMM_ZS = "Comm " + zscore_col_header_name
            LRG_ZS = "Lrg Spec " + zscore_col_header_name
            SML_ZS = "Sml Spec " + zscore_col_header_name

            spearman_col_header_name = lookback + " Spearman"
            COMM_SPR = "Comm " + spearman_col_header_name
            LRG_SPR = "Lrg Spec " + spearman_col_header_name
            SML_SPR = "Sml Spec " + spearman_col_header_name

            momentum_idx_header_name = lookback + " Move Idx"
            COMM_MOM = "Comm " + momentum_idx_header_name
            LRG_MOM = "Lrg Spec " + momentum_idx_header_name
            SML_MOM = "Sml Spec " + momentum_idx_header_name

            willco_col_header_name = "WILLCO " + lookback
            WILLCO = willco_col_header_name

            tension_col_header_name = "Custom" if lookback == "Custom" else lookback
            TENSION_Z = "Tension Zscore " + tension_col_header_name

            df = instrument.df
            result = pd.DataFrame()
            result[const.DATE] = df[const.REPORT_DATE_XLS]

            result["comms_idx"] = df[COMM_IDX]
            result["lrg_idx"] = df[LRG_IDX]
            result["sml_idx"] = df[SML_IDX]

            result["comms_norm_idx"] = df[COMM_NORM_IDX]
            result["lrg_norm_idx"] = df[LRG_NORM_IDX]
            result["sml_norm_idx"] = df[SML_NORM_IDX]

            result["comms_zscore"] = df[COMM_ZS]
            result["lrg_zscore"] = df[LRG_ZS]
            result["sml_zscore"] = df[SML_ZS]

            result["comms_spearman"] = df[COMM_SPR]
            result["lrg_spearman"] = df[LRG_SPR]
            result["sml_spearman"] = df[SML_SPR]

            result["comm_momentum"] = df[COMM_MOM]
            result["lrg_momentum"] = df[LRG_MOM]
            result["sml_momentum"] = df[SML_MOM]

            result["willco"] = df[WILLCO]

            result["tension"] = df[TENSION_Z]

            result[const.COMM_NET] = df[const.COMM_NET]
            result[const.LARGE_NET] = df[const.LARGE_NET]
            result[const.SMALL_NET] = df[const.SMALL_NET]
            result[const.COMM_NET_NORM] = df[const.COMM_NET_NORM]
            result[const.LARGE_NET_NORM] = df[const.LARGE_NET_NORM]
            result[const.SMALL_NET_NORM] = df[const.SMALL_NET_NORM]
            result[const.LARGE_FLIP] = df[const.LARGE_FLIP]

            result[const.COMM_PCT_OI] = df[const.COMM_PCT_OI]
            result[const.LARGE_PCT_OI] = df[const.LARGE_PCT_OI]
            result[const.SMALL_PCT_OI] = df[const.SMALL_PCT_OI]

            result[const.OPEN_INTEREST] = df[const.OPEN_INTEREST_XLS]
            result[const.CLOSING_PRICE] = df[const.CLOSING_PRICE]

            result.set_index(const.DATE, inplace=True)
            return result
        return None

    def get_positioning_table_by_asset_class(self, asset_classes, lookback, estimate_gap=False):
        idx_col_header_name = lookback + " Idx"
        COMM_IDX = "Comm " + idx_col_header_name
        LRG_IDX = "Lrg Spec " + idx_col_header_name
        SML_IDX = "Sml Spec " + idx_col_header_name

        zscore_col_header_name = lookback + " Zscore"
        COMM_ZS = "Comm " + zscore_col_header_name
        LRG_ZS = "Lrg Spec " + zscore_col_header_name
        SML_ZS = "Sml Spec " + zscore_col_header_name

        spearman_col_header_name = lookback + " Spearman"
        COMM_SPR = "Comm " + spearman_col_header_name
        LRG_SPR = "Lrg Spec " + spearman_col_header_name
        SML_SPR = "Sml Spec " + spearman_col_header_name

        willco_col_header_name = "WILLCO " + lookback
        WILLCO = willco_col_header_name

        cols = [const.DATE, const.ASSET_CLASS, const.SYMBOL, const.NAME,
                const.COMM_NET, const.LARGE_NET, const.SMALL_NET,
                COMM_IDX, LRG_IDX, SML_IDX,
                const.COMM_NET_EST, const.LARGE_NET_EST, const.SMALL_NET_EST,
                const.COMM_IDX_EST, const.LARGE_IDX_EST, const.SMALL_IDX_EST,
                COMM_ZS, LRG_ZS, SML_ZS,
                COMM_SPR, LRG_SPR, SML_SPR,
                WILLCO]
        positioning_df = pd.DataFrame(columns=cols)

        for asset in self.asset_class_map:
            if asset not in asset_classes:
                continue

            instruments = self.get_assets_for_asset_class(asset)
            for instrument_name in instruments:
                instrument = self.get_instrument_from_name(instrument_name)
                if instrument:
                    df = instrument.df
                    idx = len(df) - 1
                    symbol = instrument.symbol
                    if estimate_gap:
                        self.estimate_current_gap_positions(df, symbol, COMM_SPR, LRG_SPR, SML_SPR)

                        lb_weeks = utils.get_lookback_weeks(lookback, instrument)
                        utils.cot_logger.debug(f"Calculating indexes for {symbol} with lookback {lookback} ({lb_weeks} weeks)...")

                        lb_idx = idx - lb_weeks
                        df.at[idx, const.COMM_IDX_EST] = metrics.calculate_cot_index(df[const.COMM_NET_EST], lb_idx, idx)
                        df.at[idx, const.LARGE_IDX_EST] = metrics.calculate_cot_index(df[const.LARGE_NET_EST], lb_idx, idx)
                        df.at[idx, const.SMALL_IDX_EST] = metrics.calculate_cot_index(df[const.SMALL_NET_EST], lb_idx, idx)
                    else:
                        df.at[idx, const.COMM_IDX_EST] = 0
                        df.at[idx, const.LARGE_IDX_EST] = 0
                        df.at[idx, const.SMALL_IDX_EST] = 0

                    new_df = pd.DataFrame(
                        [[df.iloc[-1][const.REPORT_DATE_XLS].date(), instrument.asset_class, instrument.symbol, instrument.name,
                          df.iloc[-1][const.COMM_NET], df.iloc[-1][const.LARGE_NET], df.iloc[-1][const.SMALL_NET],
                          df.iloc[-1][COMM_IDX], df.iloc[-1][LRG_IDX], df.iloc[-1][SML_IDX],
                          df.iloc[-1][const.COMM_NET_EST], df.iloc[-1][const.LARGE_NET_EST], df.iloc[-1][const.SMALL_NET_EST],
                          df.iloc[-1][const.COMM_IDX_EST], df.iloc[-1][const.LARGE_IDX_EST], df.iloc[-1][const.SMALL_IDX_EST],
                          round(df.iloc[-1][COMM_ZS], 2), round(df.iloc[-1][LRG_ZS], 2), round(df.iloc[-1][SML_ZS], 2),
                          round(df.iloc[-1][COMM_SPR], 2), round(df.iloc[-1][LRG_SPR], 2), round(df.iloc[-1][SML_SPR], 2),
                          df.iloc[-1][WILLCO]
                        ]], columns=positioning_df.columns)

                    if positioning_df.empty:
                        positioning_df = new_df
                    else:
                        positioning_df = pd.concat([positioning_df, new_df])
        return positioning_df

    def get_asset_class_z_score_heat(self, asset_class, lookback):
        """Returns the latest Z-scores for all assets in a class."""
        assets = self.get_assets_for_asset_class(asset_class)
        heat_data = []

        for name in assets:
            instrument = self.get_instrument_from_name(name)
            if instrument is not None and not instrument.df.empty:
                df = instrument.df
                # Get the most recent non-NaN Z-scores
                latest = df.iloc[-1]
                if lookback == "26":
                    heat_data.append({
                        "Asset": name,
                        "Commercials": latest.get(const.COMM_26_ZSCORE, 0),
                        "Large Specs": latest.get(const.LARGE_26_ZSCORE, 0),
                        "Small Specs": latest.get(const.SMALL_26_ZSCORE, 0)
                    })
                elif lookback == "52":
                    heat_data.append({
                        "Asset": name,
                        "Commercials": latest.get(const.COMM_52_ZSCORE, 0),
                        "Large Specs": latest.get(const.LARGE_52_ZSCORE, 0),
                        "Small Specs": latest.get(const.SMALL_52_ZSCORE, 0)
                    })
                else:
                    heat_data.append({
                        "Asset": name,
                        "Commercials": latest.get(const.COMM_CUSTOM_ZSCORE, 0),
                        "Large Specs": latest.get(const.LARGE_CUSTOM_ZSCORE, 0),
                        "Small Specs": latest.get(const.SMALL_CUSTOM_ZSCORE, 0)
                    })

        return pd.DataFrame(heat_data)

    def get_asset_class_index_heat(self, asset_class, lookback):
        """Returns the latest Index for all assets in a class."""
        assets = self.get_assets_for_asset_class(asset_class)
        heat_data = []

        for name in assets:
            instrument = self.get_instrument_from_name(name)
            if instrument is not None and not instrument.df.empty:
                df = instrument.df
                # Get the most recent non-NaN Z-scores
                latest = df.iloc[-1]

                if lookback == "26":
                    heat_data.append({
                        "Asset": name,
                        "Commercials": latest.get(const.COMM_26_IDX, 0),
                        "Large Specs": latest.get(const.LARGE_26_IDX, 0),
                        "Small Specs": latest.get(const.SMALL_26_IDX, 0)
                    })
                elif lookback == "52":
                    heat_data.append({
                        "Asset": name,
                        "Commercials": latest.get(const.COMM_52_IDX, 0),
                        "Large Specs": latest.get(const.LARGE_52_IDX, 0),
                        "Small Specs": latest.get(const.SMALL_52_IDX, 0)
                    })
                else:
                    heat_data.append({
                        "Asset": name,
                        "Commercials": latest.get(const.COMM_CUSTOM_IDX, 0),
                        "Large Specs": latest.get(const.LARGE_CUSTOM_IDX, 0),
                        "Small Specs": latest.get(const.SMALL_CUSTOM_IDX, 0)
                    })

        return pd.DataFrame(heat_data)
