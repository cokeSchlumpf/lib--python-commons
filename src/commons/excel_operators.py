import pandas as pd
import xlsxwriter  # type: ignore

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, List, Literal, Optional, TypeVar, TypedDict, Union, cast
from xlsxwriter import worksheet  # type: ignore


class ExcelTheme(TypedDict):
    """Theme configuration for Excel spreadsheet styling.

    Defines color scheme for various UI elements including primary colors,
    accent colors, neutral tones, and status indicators.

    Attributes:
       primary_bg_color: Primary background color (hex format)
       primary_color: Primary text/foreground color (hex format)
       accent_1_bg_color: First accent background color (hex format)
       accent_1_color: First accent text/foreground color (hex format)
       accent_2_bg_color: Second accent background color (hex format)
       accent_2_color: Second accent text/foreground color (hex format)
       neutral_dark: Dark neutral color (hex format)
       neutral_mid: Medium neutral color (hex format)
       neutral_light: Light neutral color (hex format)
       positive: Positive status indicator color (hex format)
       caution: Caution/warning status indicator color (hex format)
       negative: Negative/error status indicator color (hex format)
    """

    primary_bg_color: str
    primary_color: str

    accent_1_bg_color: str
    accent_1_color: str

    accent_2_bg_color: str
    accent_2_color: str

    neutral_dark: str
    neutral_mid: str
    neutral_light: str

    positive_bg_color: str
    positive_color: str

    caution_bg_color: str
    caution_color: str

    negative_bg_color: str
    negative_color: str


class ExcelCellFormat(TypedDict, total=False):
    """Cell formatting configuration for Excel cells.

    All fields are optional (total=False). Used to customize the appearance
    of cells including alignment, colors, borders, and text wrapping.

    Attributes:
       align: Horizontal text alignment ("left", "center", or "right")
       bg_color: Background color (hex format)
       bold: Whether text should be bold
       border: Border width for all sides (integer value)
       bottom: Bottom border width (integer value)
       color: Text/foreground color (hex format)
       left: Left border width (integer value)
       right: Right border width (integer value)
       text_wrap: Whether text should wrap within the cell
       top: Top border width (integer value)
       valign: Vertical text alignment ("top", "center", or "bottom")
    """

    align: Literal["left", "center", "right"]
    bg_color: str
    bold: bool
    border: int
    bottom: int
    color: str
    left: int
    right: int
    text_wrap: bool
    top: int
    valign: Literal["top", "center", "bottom"]


@dataclass
class ExcelColumn:
    """Configuration for an Excel column.

    Defines the properties and formatting for a single column in an Excel worksheet,
    including name, display title, width, and custom formatting functions.

    Attributes:
       name: Column name (used to reference data in DataFrame)
       title: Display title for column header (defaults to name if not provided)
       width: Column width in character units (default: 40)
       format: Optional function to customize cell format. Takes (theme, base_format)
          and returns modified ExcelCellFormat
       header_format: Optional function to customize header cell format. Takes
          (theme, base_format) and returns modified ExcelCellFormat
       modify_cell: Optional callback for advanced cell modification. Takes
          (theme, workbook, worksheet, column_index, row_count) and allows direct
          manipulation of cells in the column
    """

    name: str
    title: Optional[str] = None
    width: Optional[int] = 40
    hidden: bool = False
    format: Optional[Callable[[ExcelTheme, ExcelCellFormat], ExcelCellFormat]] = None
    header_format: Optional[Callable[[ExcelTheme, ExcelCellFormat], ExcelCellFormat]] = None
    modify_cell: Optional[Callable[[ExcelTheme, xlsxwriter.Workbook, worksheet.Worksheet, int, int], None]] = None


T = TypeVar("T")


class ExcelWriter:
    """Writer for creating formatted Excel spreadsheets.

    Provides high-level API for creating Excel files from pandas DataFrames or
    Python objects with consistent formatting, theming, and styling.

    Type aliases:
       CellFormat: Alias for ExcelCellFormat
       Column: Alias for ExcelColumn
       Theme: Alias for ExcelTheme

    Usage:
       writer = ExcelWriter.create()
       writer.write_excel_from_df(df, Path("output.xlsx"), columns)
    """

    CellFormat = ExcelCellFormat
    Column = ExcelColumn
    Theme = ExcelTheme

    Workbook = xlsxwriter.Workbook
    Worksheet = worksheet.Worksheet

    class StandardFormats:
        """Collection of standard cell format presets.

        Provides commonly used border format configurations. Border widths:
        - 1: Thin border
        - 2: Medium border

        Attributes:
           border_bottom_thin: Thin bottom border (width 1)
           border_bottom_medium: Medium bottom border (width 2)
           border_left_thin: Thin left border (width 1)
           border_left_medium: Medium left border (width 2)
           border_right_thin: Thin right border (width 1)
           border_right_medium: Medium right border (width 2)
           border_top_thin: Thin top border (width 1)
           border_top_medium: Medium top border (width 2)
        """

        border_bottom_thin: ExcelCellFormat = {"bottom": 1}
        border_bottom_medium: ExcelCellFormat = {"bottom": 2}
        border_left_thin: ExcelCellFormat = {"left": 1}
        border_left_medium: ExcelCellFormat = {"left": 2}
        border_right_thin: ExcelCellFormat = {"right": 1}
        border_right_medium: ExcelCellFormat = {"right": 2}
        border_top_thin: ExcelCellFormat = {"top": 1}
        border_top_medium: ExcelCellFormat = {"top": 2}

    def __init__(self, header_format: ExcelCellFormat, std_cell_format: ExcelCellFormat, theme: ExcelTheme) -> None:
        """Initialize ExcelWriter with formatting configuration.

        Note: Direct instantiation is discouraged. Use ExcelWriter.create() factory
        method instead for default configurations.

        Args:
           header_format: Format configuration for header cells
           std_cell_format: Format configuration for standard data cells
           theme: Color theme for styling
        """

        self.header_format = header_format
        self.std_cell_format = std_cell_format
        self.theme = theme

    @staticmethod
    def create(
        theme: Optional[ExcelTheme] = None,
        header_format_factory: Optional[Callable[[ExcelTheme, ExcelCellFormat], ExcelCellFormat]] = None,
        std_cell_format_factory: Optional[Callable[[ExcelTheme, ExcelCellFormat], ExcelCellFormat]] = None,
    ) -> "ExcelWriter":
        """Create an ExcelWriter instance with optional custom configuration.

        Factory method that provides sensible defaults for theme and formatting.
        If no theme is provided, uses a blue-based professional color scheme.

        Args:
           theme: Optional custom color theme. If None, uses default blue theme
              with primary color #00338D (deep blue) and complementary accents
           header_format_factory: Optional function to customize header format.
              Takes (theme, default_header_format) and returns modified format.
              Default header format includes: bold text, text wrap, top alignment,
              left alignment, primary theme colors, and medium bottom border
           std_cell_format_factory: Optional function to customize standard cell
              format. Takes (theme, default_cell_format) and returns modified format.
              Default cell format includes: top alignment and text wrap

        Returns:
           Configured ExcelWriter instance ready to write Excel files

        Example:
           # Use defaults
           writer = ExcelWriter.create()

           # Custom theme
           custom_theme = {"primary_bg_color": "#FF0000", ...}
           writer = ExcelWriter.create(theme=custom_theme)

           # Custom formatting
           def my_header_fmt(theme, base_fmt):
              return {**base_fmt, "align": "center"}
           writer = ExcelWriter.create(header_format_factory=my_header_fmt)
        """

        if not theme:
            theme = {
                "primary_bg_color": "#00338D",  # Deep Blue
                "primary_color": "#ffffff",
                "accent_1_bg_color": "#005EB8",  # Royal Blue
                "accent_1_color": "#ffffff",
                "accent_2_bg_color": "#94C7ED",  # Light Blue
                "accent_2_color": "#000000",
                "neutral_dark": "#4D4F53",
                "neutral_mid": "#A7A8AA",
                "neutral_light": "#E7E7E8",
                "positive_bg_color": "#76B947",
                "positive_color": "#000000",
                "caution_bg_color": "#FFC20E",
                "caution_color": "#000000",
                "negative_bg_color": "#D81E05",
                "negative_color": "#ffffff",
            }

        header_format: ExcelCellFormat = {
            "bold": True,
            "text_wrap": True,
            "valign": "top",
            "align": "left",
            "bg_color": theme["primary_bg_color"],
            "color": theme["primary_color"],
            **ExcelWriter.StandardFormats.border_bottom_medium,
        }
        if header_format_factory:
            header_format = header_format_factory(theme, header_format)

        std_cell_format: ExcelCellFormat = {"valign": "top", "text_wrap": True}
        if std_cell_format_factory:
            std_cell_format = std_cell_format_factory(theme, std_cell_format)

        return ExcelWriter(header_format, std_cell_format, theme)

    def write_excel_from_df(
        self,
        df: pd.DataFrame,
        path: Union[Path, BinaryIO],
        columns: Optional[List[ExcelColumn]] = None,
        sheet_name: str = "Sheet 1",
        sheet_fomatter: Optional[
            Callable[[xlsxwriter.Workbook, worksheet.Worksheet, List[ExcelColumn], pd.DataFrame], None]
        ] = None,
    ) -> None:
        """Write a pandas DataFrame to an Excel file with formatting.

        Creates an Excel workbook at the specified path with the DataFrame data.
        Automatically applies formatting, column widths, freeze panes, and autofilters.

        Args:
           df: pandas DataFrame to write to Excel
           path: File path where Excel file should be written
           columns: Optional list of ExcelColumn configurations. If None, creates
              default columns from df.columns with standard formatting
           sheet_name: Name of the worksheet (default: "Sheet 1")
           sheet_fomatter: Optional callback for advanced worksheet customization.
              Takes (worksheet, workbook, columns, dataframe) for post-processing

        Features:
           - Applies custom column widths and formatting
           - Freezes top header row
           - Adds autofilter to all columns
           - Uses theme colors for headers
           - Supports per-column format customization

        Example:
           columns = [
              ExcelColumn("name", width=30),
              ExcelColumn("email", width=40),
           ]
           writer.write_excel_from_df(df, Path("output.xlsx"), columns)
        """

        if not columns:
            columns = [ExcelColumn(c) for c in df.columns]

        df = pd.DataFrame(df.to_dict(orient="records"))[[c.name for c in columns]]

        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)

            wb = cast(xlsxwriter.Workbook, writer.book)
            ws = cast(worksheet.Worksheet, writer.sheets[sheet_name])

            for i, col in enumerate(columns):
                hf = wb.add_format(
                    col.header_format(self.theme, self.header_format) if col.header_format else self.header_format
                )
                cf = wb.add_format(col.format(self.theme, self.std_cell_format) if col.format else self.std_cell_format)

                ws.write(0, i, col.title or col.name, hf)

                if col.hidden:
                    ws.set_column(i, i, None, cf, {"hidden": True})
                else:
                    ws.set_column(i, i, col.width, cf)

                if col.modify_cell:
                    col.modify_cell(self.theme, wb, ws, i, len(df))

            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), len(columns) - 1)

            if sheet_fomatter:
                sheet_fomatter(wb, ws, columns, df)

        return

    def write_excel_from_objects(
        self,
        items: List[T],
        items_to_dict: Callable[[T], dict],
        path: Union[Path, BinaryIO],
        columns: List[ExcelColumn],
        sheet_name: str = "Sheet 1",
        sheet_fomatter: Optional[
            Callable[[xlsxwriter.Workbook, worksheet.Worksheet, List[ExcelColumn], pd.DataFrame], None]
        ] = None,
    ) -> None:
        """Write a list of Python objects to an Excel file with formatting.

        Converts objects to dictionaries, then to DataFrame, and writes to Excel.
        Provides a convenient interface for writing domain objects or dataclasses
        to Excel without manual DataFrame conversion.

        Args:
           items: List of objects to write to Excel
           items_to_dict: Function that converts each object to a dictionary.
              Dictionary keys should match column names
           path: File path where Excel file should be written
           columns: List of ExcelColumn configurations defining column order,
              widths, and formatting
           sheet_name: Name of the worksheet (default: "Sheet 1")
           sheet_fomatter: Optional callback for advanced worksheet customization.
              Takes (worksheet, workbook, columns, dataframe) for post-processing

        Note:
           If items list is empty, creates an Excel file with headers only.

        Example:
           @dataclass
           class Person:
              name: str
              age: int

           people = [Person("Alice", 30), Person("Bob", 25)]
           columns = [
              ExcelColumn("name", width=30),
              ExcelColumn("age", width=10),
           ]

           def person_to_dict(p: Person) -> dict:
              return {"name": p.name, "age": p.age}

           writer.write_excel_from_objects(
              people, person_to_dict, Path("people.xlsx"), columns
           )
        """

        rows = [items_to_dict(i) for i in items]
        if not rows:
            rows = [{}]

        df = pd.DataFrame(rows)[[c.name for c in columns]]
        self.write_excel_from_df(df, path, columns, sheet_name, sheet_fomatter)

    def write_excel_multi_sheet(
        self,
        sheets: List[tuple[str, pd.DataFrame, List[ExcelColumn]]],
        path: Union[Path, BinaryIO],
    ) -> None:
        """Write multiple sheets to an Excel file with formatting.

        Creates an Excel workbook with multiple worksheets, each with its own
        DataFrame and column configuration.

        Args:
           sheets: List of tuples, each containing:
              - sheet_name: Name of the worksheet
              - df: pandas DataFrame to write
              - columns: List of ExcelColumn configurations
           path: File path where Excel file should be written

        Example:
           sheets = [
              ("Users", users_df, user_columns),
              ("Orders", orders_df, order_columns),
           ]
           writer.write_excel_multi_sheet(sheets, Path("output.xlsx"))
        """
        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            for sheet_name, df, columns in sheets:
                if not columns:
                    columns = [ExcelColumn(c) for c in df.columns]

                df = pd.DataFrame(df.to_dict(orient="records"))
                if columns:
                    df = df[[c.name for c in columns]]

                df.to_excel(writer, index=False, sheet_name=sheet_name)

                wb = cast(xlsxwriter.Workbook, writer.book)
                ws = cast(worksheet.Worksheet, writer.sheets[sheet_name])

                for i, col in enumerate(columns):
                    hf = wb.add_format(
                        col.header_format(self.theme, self.header_format) if col.header_format else self.header_format
                    )
                    cf = wb.add_format(
                        col.format(self.theme, self.std_cell_format) if col.format else self.std_cell_format
                    )

                    ws.write(0, i, col.title or col.name, hf)

                    if col.hidden:
                        ws.set_column(i, i, None, cf, {"hidden": True})
                    else:
                        ws.set_column(i, i, col.width, cf)

                    if col.modify_cell:
                        col.modify_cell(self.theme, wb, ws, i, len(df))

                ws.freeze_panes(1, 0)
                ws.autofilter(0, 0, max(len(df), 1), len(columns) - 1)
