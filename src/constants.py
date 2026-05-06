# Columns of COT data to consume
MARKET_NAME_XLS = "Market_and_Exchange_Names"
REPORT_DATE_XLS = "Report_Date_as_MM_DD_YYYY"
CONTRACT_CODE_XLS = "CFTC_Contract_Market_Code"
OPEN_INTEREST_XLS = "Open_Interest_All"
COMM_LONG_POS_XLS = "Comm_Positions_Long_All"
COMM_SHORT_POS_XLS = "Comm_Positions_Short_All"
LARGE_LONG_POS_XLS = "NonComm_Positions_Long_All"
LARGE_SHORT_POS_XLS = "NonComm_Positions_Short_All"
SMALL_LONG_POS_XLS = "NonRept_Positions_Long_All"
SMALL_SHORT_POS_XLS = "NonRept_Positions_Short_All"

COMM_LONG = "Comm Positions Long All"
COMM_SHORT = "Comm Positions Short All"
LARGE_LONG = "Lrg Positions Long All"
LARGE_SHORT = "Lrg Positions Short All"
SMALL_LONG = "Sml Positions Long All"
SMALL_SHORT = "Sml Positions Short All"

# Columns to create for consumed COT data
DATE = "Date"
SYMBOL = "Symbol"
NAME = "Name"
ASSET_CLASS = "Asset Class"
OPEN_INTEREST = "Open Interest"

COMM_NET = "Comm Net Pos"
LARGE_NET = "Lrg Spec Net Pos"
SMALL_NET = "Sml Spec Net Pos"
LARGE_FLIP = "Lrg Spec Net Pos Flip"

COMM_PCT_OI = "Comm OI Pct"
LARGE_PCT_OI = "Lrg OI Pct"
SMALL_PCT_OI = "Sml OI Pct"

COMM_CUSTOM_CORR = "Comm Custom Spearman"
LARGE_CUSTOM_CORR = "Lrg Spec Custom Spearman"
SMALL_CUSTOM_CORR = "Sml Spec Custom Spearman"
COMM_26_CORR = "Comm 26 Spearman"
LARGE_26_CORR = "Lrg Spec 26 Spearman"
SMALL_26_CORR = "Sml Spec 26 Spearman"
COMM_52_CORR = "Comm 52 Spearman"
LARGE_52_CORR = "Lrg Spec 52 Spearman"
SMALL_52_CORR = "Sml Spec 52 Spearman"

COMM_CUSTOM_IDX = "Comm Custom Idx"
LARGE_CUSTOM_IDX = "Lrg Spec Custom Idx"
SMALL_CUSTOM_IDX = "Sml Spec Custom Idx"
COMM_26_IDX = "Comm 26 Idx"
LARGE_26_IDX = "Lrg Spec 26 Idx"
SMALL_26_IDX = "Sml Spec 26 Idx"
COMM_52_IDX = "Comm 52 Idx"
LARGE_52_IDX = "Lrg Spec 52 Idx"
SMALL_52_IDX = "Sml Spec 52 Idx"

COMM_CUSTOM_ZSCORE = "Comm Custom Zscore"
LARGE_CUSTOM_ZSCORE = "Lrg Spec Custom Zscore"
SMALL_CUSTOM_ZSCORE = "Sml Spec Custom Zscore"
COMM_26_ZSCORE = "Comm 26 Zscore"
LARGE_26_ZSCORE = "Lrg Spec 26 Zscore"
SMALL_26_ZSCORE = "Sml Spec 26 Zscore"
COMM_52_ZSCORE = "Comm 52 Zscore"
LARGE_52_ZSCORE = "Lrg Spec 52 Zscore"
SMALL_52_ZSCORE = "Sml Spec 52 Zscore"

COMM_MOMENTUM_CUSTOM_IDX = "Comm Custom Move Idx"
LARGE_MOMENTUM_CUSTOM_IDX = "Lrg Spec Custom Move Idx"
SMALL_MOMENTUM_CUSTOM_IDX = "Sml Spec Custom Move Idx"
COMM_MOMENTUM_26_IDX = "Comm 26 Move Idx"
LARGE_MOMENTUM_26_IDX = "Lrg Spec 26 Move Idx"
SMALL_MOMENTUM_26_IDX = "Sml Spec 26 Move Idx"
COMM_MOMENTUM_26_IDX = "Comm 52 Move Idx"
LARGE_MOMENTUM_26_IDX = "Lrg Spec 52 Move Idx"
SMALL_MOMENTUM_26_IDX = "Sml Spec 52 Move Idx"
MOMENTUM_PERIOD = 1

CLOSING_PRICE = "Closing Price"
WILLCO_CUSTOM = "WILLCO Custom"
WILLCO_26 = "WILLCO 26"
WILLCO_52 = "WILLCO 52"

TENSION_Z_CUSTOM = "Tension Zscore Custom"
TENSION_Z_26 = "Tension Zscore 26"
TENSION_Z_52 = "Tension Zscore 52"

TEXT_COLOR = "#ABB8C9"
BRIGHTER_TEXT_COLOR = "#E2E8F0"
HOVER_TEXT_COLOR = "#FFFFFF"
BACKGROUND_COLOR = "#1a1a1a"
BLUE_BACKGROUND = "#375a7f"
GRID_COLOR = "rgba(255, 255, 255, 0.2)"  # Subtle white grid
EMPTY_COLOR = 'rgba(0, 0, 0, 0)'

# Plotting Dimensions
PIXELS_PER_ROW = 275
FIXED_OVERHEAD = 120

app_timezone = "US/Eastern"

label_style={
    'color': TEXT_COLOR,
    'fontSize': '0.85rem',
    'marginRight': '5px',
    'marginBottom': 0,
}

hr_style={
    'height': '38px',
    'display': 'flex',
    'alignItems': 'center',
    'fontSize': '0.8rem',
    'color': BRIGHTER_TEXT_COLOR,
    'backgroundColor': TEXT_COLOR,
    'height': '1px',
    'border': 'none',
    'opacity': '0.5',
    'marginTop': '10px',
    'marginBottom': '30px',
    'width': '95%',
    'marginLeft': 'auto',
    'marginRight': 'auto',
}

button_style={
    'height': '38px',
    'display': 'flex',
    'alignItems': 'center',
    'backgroundColor': BACKGROUND_COLOR,
    'color': BRIGHTER_TEXT_COLOR,
    'borderColor': BRIGHTER_TEXT_COLOR,
    'border': f'1.5px solid TEXT_COLOR',
    'fontSize': '0.8rem',
    'textAlign': 'center',
    'width': '100%',
    'maxWidth': '200px',
}

row_start_style={
    'paddingLeft': '2.5%',
    'paddingRight': '2.5%'
}

link_style={
    'color': BRIGHTER_TEXT_COLOR,
    'fontSize': '1.5rem',
}

# Plot related
WILLCO_MIN_THRESHOLD = 20
WILLCO_MAX_THRESHOLD = 80

ZSCORE_MIN_THRESHOLD = -2.0
ZSCORE_MAX_THRESHOLD = 2.0

MOMENTUM_MIN_THRESHOLD = -40
MOMENTUM_MAX_THRESHOLD = 40

PIXELS_PER_PLOT = 250
PIXELS_OVERHEAD_PER_PLOT = 25

VERTICAL_SPACING = 0.1
ENABLE_HLINE_THRESHOLDS = False
HLINE_OPACITY = 0.01

DEFAULT_WEEKS_TO_VIEW = 78
