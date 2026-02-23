"""
Invoice PDF generator from KSeF XML files.

This script reads a KSeF XML invoice file and generates a PDF invoice.
The output filename is automatically generated from the invoice data.
"""

import xml.etree.ElementTree as ET
import sys
import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip .env loading

# XML namespaces for KSeF invoices (2023 and 2025 schema)
KSEF_NS_2023 = 'http://crd.gov.pl/wzor/2023/06/29/12648/'
KSEF_NS_2025 = 'http://crd.gov.pl/wzor/2025/06/25/13775/'
KSEF_NS = {'ns': KSEF_NS_2023}

# PDF layout constants
COL_WIDTH = 85
GAP_BETWEEN_COLUMNS = 30
FONT_NAME = "Helvetica"
UNICODE_FONT_NAME = "DejaVu"
# When a Unicode font is loaded, Polish characters (ą, ę, ł, etc.) are shown; otherwise we transliterate.
_use_unicode_font = False
_current_font = FONT_NAME
LINE_HEIGHT_SMALL = 4
LINE_HEIGHT_MEDIUM = 5
LINE_HEIGHT_LARGE = 6
SECTION_SPACING_SMALL = 4
SECTION_SPACING_MEDIUM = 10
SECTION_SPACING_LARGE = 12
MIN_ROW_HEIGHT = 10
ROW_HEIGHT_PER_LINE = 5

# Table column widths (in mm)
TABLE_COLUMNS = {
    'no': 8,
    'name': 50,
    'qty': 12,
    'unit': 10,
    'unit_price': 20,
    'net_price': 20,
    'vat': 21,
    'tax': 15,
    'currency': 20
}

# Labels for invoice (English and Polish when currency is PLN).
# Polish uses proper diacritics (ą, ę, ó, ł, ń, ś, ź, ż) for Unicode font output.
TRANSLATIONS = {
    'invoice_title': {'en': 'Invoice No. ', 'pl': 'Faktura VAT nr '},
    'date_of_issue': {'en': 'Date of issue ', 'pl': 'Data wystawienia '},
    'seller': {'en': 'Seller:', 'pl': 'Sprzedawca:'},
    'buyer': {'en': 'Buyer:', 'pl': 'Nabywca:'},
    'bank_account': {'en': 'Bank account: ', 'pl': 'Konto bankowe: '},
    'date_of_sale': {'en': 'Date of sale: ', 'pl': 'Data sprzedaży: '},
    'payment_method': {'en': 'Payment method: Bank transfer in ', 'pl': 'Sposób zapłaty: Przelew bankowy'},
    'col_no': {'en': 'No.', 'pl': 'Lp.'},
    'col_name': {'en': 'Name of service', 'pl': 'Nazwa usługi'},
    'col_qty': {'en': 'Quantity', 'pl': 'Ilość'},
    'col_unit': {'en': 'Unit', 'pl': 'J.m.'},
    'col_unit_price': {'en': 'Unit net price', 'pl': 'Cena jedn. Netto'},
    'col_net_price': {'en': 'Net price', 'pl': 'Wartość netto'},
    'col_vat': {'en': 'VAT tax rate', 'pl': 'Podatek VAT Stawka'},
    'col_tax': {'en': 'Total Tax', 'pl': 'Kwota VAT'},
    'col_gross': {'en': ' value', 'pl': 'Wartość brutto Kwota'},
    'total': {'en': 'Total', 'pl': 'Razem'},
    'in_that_by_rates': {'en': 'in that by rates', 'pl': 'w tym wg stawek'},
    'amount_due': {'en': 'Amount due: ', 'pl': 'Kwota do zapłaty: '},
}


def _t(data: dict, key: str) -> str:
    """Return label in Polish when currency is PLN, else English."""
    return TRANSLATIONS[key]['pl'] if data.get('currency') == 'PLN' else TRANSLATIONS[key]['en']


# Translation table for Polish to ASCII characters
POLISH_TO_ASCII = str.maketrans({
    'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
    'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
    'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
})


def transliterate(text: str | None) -> str:
    """Convert Polish characters to ASCII for font compatibility."""
    return text.translate(POLISH_TO_ASCII) if text else ""


def _normalize_whitespace(text: str | None) -> str:
    """Collapse any run of whitespace (spaces, newlines, tabs) to a single space and strip."""
    if not text:
        return ""
    return " ".join(text.split())


def _find_unicode_font() -> str | None:
    """Return path to a TTF font that supports Polish (e.g. DejaVu Sans), or None."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.getenv("PDF_FONT_PATH"),
        os.path.join(script_dir, "fonts", "DejaVuSans.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        os.path.expanduser("~/Library/Fonts/DejaVuSans.ttf"),
        "/Library/Fonts/Arial Unicode.ttf",
        "/opt/homebrew/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _pdf_text(text: str | None) -> str:
    """Return text as-is when using Unicode font, else transliterate for Helvetica."""
    if not text:
        return ""
    return text if _use_unicode_font else transliterate(text)


def _get_namespaces(root: ET.Element) -> dict[str, str]:
    """Detect KSeF namespace from root element (supports 2023 and 2025 schema)."""
    if root.tag.startswith('{'):
        uri = root.tag[1:root.tag.index('}')]
        return {'ns': uri}
    return KSEF_NS


def get_xml_text(root: ET.Element, xpath: str, default: str = "", namespaces: dict[str, str] | None = None) -> str:
    """Extract text from XML element, return default if not found."""
    ns = namespaces or _get_namespaces(root)
    element = root.find(xpath, ns)
    return element.text if element is not None and element.text else default


def parse_invoice_data(xml_file_path: str) -> dict[str, str | float | list[dict]]:
    """Parse XML file and extract invoice data."""
    with open(xml_file_path, 'r', encoding='utf-8') as f:
        root = ET.fromstring(f.read())

    ns = _get_namespaces(root)

    # Extract invoice header data
    inv_number = get_xml_text(root, './/ns:P_2', namespaces=ns)
    inv_num, inv_year = (inv_number.split('/') + [''])[:2]

    issue_date = get_xml_text(root, './/ns:P_1', namespaces=ns)
    sale_date = get_xml_text(root, './/ns:P_6', default=issue_date, namespaces=ns)

    # Extract seller data
    seller_name_raw = _normalize_whitespace(get_xml_text(root, './/ns:Podmiot1/ns:DaneIdentyfikacyjne/ns:Nazwa', namespaces=ns))
    seller_nip = get_xml_text(root, './/ns:Podmiot1/ns:DaneIdentyfikacyjne/ns:NIP', namespaces=ns)
    seller_address_raw = _normalize_whitespace(get_xml_text(root, './/ns:Podmiot1/ns:Adres/ns:AdresL1', namespaces=ns))

    # Extract buyer data
    buyer_name_raw = _normalize_whitespace(get_xml_text(root, './/ns:Podmiot2/ns:DaneIdentyfikacyjne/ns:Nazwa', namespaces=ns))
    buyer_nip = get_xml_text(root, './/ns:Podmiot2/ns:DaneIdentyfikacyjne/ns:NIP', '', namespaces=ns)
    buyer_address_raw = _normalize_whitespace(get_xml_text(root, './/ns:Podmiot2/ns:Adres/ns:AdresL1', namespaces=ns))

    # Extract financial data
    currency = get_xml_text(root, './/ns:KodWaluty', namespaces=ns)
    total_amount = float(get_xml_text(root, './/ns:P_15', '0', namespaces=ns))

    # Extract KSeF number from filename or environment
    ksef_number = os.getenv("KSEF_NUMBER", os.path.splitext(os.path.basename(xml_file_path))[0])

    # Get bank account from environment variable
    account_env_var = f"ACCOUNT_{currency}"
    bank_account = os.getenv(account_env_var, "")
    if not bank_account:
        print(f"Warning: {account_env_var} environment variable not set")

    # Extract invoice items
    items = []
    for wiersz in root.findall('.//ns:FaWiersz', ns):
        vat_code_raw = get_xml_text(wiersz, 'ns:P_12', 'np.', namespaces=ns)
        line_total = float(get_xml_text(wiersz, 'ns:P_11', '0', namespaces=ns))
        # Format VAT as "23%" when numeric, else "np."
        vat_display = f"{vat_code_raw}%" if vat_code_raw.isdigit() else vat_code_raw
        # Compute VAT amount and gross from net and rate
        if vat_code_raw.isdigit():
            rate = int(vat_code_raw)
            vat_amount = round(line_total * rate / 100, 2)
            line_gross = round(line_total + vat_amount, 2)
        else:
            vat_amount = 0.0
            line_gross = line_total
        desc_raw = get_xml_text(wiersz, 'ns:P_7', namespaces=ns)
        items.append({
            'desc': transliterate(desc_raw),
            'desc_raw': desc_raw,
            'unit': get_xml_text(wiersz, 'ns:P_8A', namespaces=ns),
            'qty': get_xml_text(wiersz, 'ns:P_8B', namespaces=ns),
            'unit_price': float(get_xml_text(wiersz, 'ns:P_9A', '0', namespaces=ns)),
            'line_total': line_total,
            'vat_code': vat_display,
            'vat_amount': vat_amount,
            'line_gross': line_gross,
        })

    return {
        'inv_number': inv_number,
        'inv_num': inv_num,
        'inv_year': inv_year,
        'issue_date': issue_date,
        'sale_date': sale_date,
        'seller_name': transliterate(seller_name_raw),
        'seller_name_raw': seller_name_raw,
        'seller_nip': seller_nip,
        'seller_address': transliterate(seller_address_raw),
        'seller_address_raw': seller_address_raw,
        'buyer_name': transliterate(buyer_name_raw),
        'buyer_address': transliterate(buyer_address_raw),
        'buyer_name_raw': buyer_name_raw,
        'buyer_nip': buyer_nip,
        'buyer_address_raw': buyer_address_raw,
        'currency': currency,
        'total_amount': total_amount,
        'ksef_number': ksef_number,
        'bank_account': bank_account,
        'items': items
    }


def create_pdf_header(pdf: FPDF, data: dict) -> None:
    """Create the invoice header section."""
    pdf.set_font(_current_font, 'B', 14)
    title = _t(data, 'invoice_title') + data['inv_number']
    pdf.cell(0, 8, text=_pdf_text(title),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(SECTION_SPACING_SMALL)

    pdf.set_font(_current_font, size=9)
    pdf.cell(0, LINE_HEIGHT_LARGE, text=_pdf_text(_t(data, 'date_of_issue') + data['issue_date']),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    if data['ksef_number']:
        pdf.ln(0.5)
        pdf.set_font(_current_font, size=8)
        pdf.cell(0, LINE_HEIGHT_MEDIUM, text=f"KSeF Number: {data['ksef_number']}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    pdf.ln(SECTION_SPACING_MEDIUM)


def _wrap_text_to_lines(pdf: FPDF, text: str, width: float, line_height: float) -> list[str]:
    """Split text into lines that fit within width (using multi_cell dry_run)."""
    if not text:
        return [""]
    try:
        lines = pdf.multi_cell(width, line_height, text, border=0, align='L', dry_run=True, output="LINES")
    except TypeError:
        lines = pdf.multi_cell(width, line_height, text, border=0, align='L', split_only=True)
    return list(lines) if lines else [""]


def create_seller_buyer_section(pdf: FPDF, data: dict) -> None:
    """Create the seller and buyer information section with row-by-row layout so columns stay aligned."""
    # Label row: "Seller:" and "Buyer:" side by side
    pdf.set_font(_current_font, 'B', 10)
    pdf.cell(COL_WIDTH, LINE_HEIGHT_LARGE, text=_pdf_text(_t(data, 'seller')), new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_xy(COL_WIDTH + GAP_BETWEEN_COLUMNS, pdf.get_y())
    pdf.cell(COL_WIDTH, LINE_HEIGHT_LARGE, text=_pdf_text(_t(data, 'buyer')), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(_current_font, size=9)
    y_start = pdf.get_y()
    line_height = LINE_HEIGHT_MEDIUM
    buyer_x = COL_WIDTH + GAP_BETWEEN_COLUMNS

    # Build seller lines: name (single), NIP (single), address (wrapped)
    seller_parts = [_pdf_text(data['seller_name_raw'])]
    if data['seller_nip']:
        seller_parts.append(f"NIP: {data['seller_nip']}")
    seller_parts.append(_pdf_text(data['seller_address_raw']))
    seller_lines = []
    for part in seller_parts:
        seller_lines.extend(_wrap_text_to_lines(pdf, part, COL_WIDTH, line_height))

    # Build buyer lines: name (wrapped), NIP (single line if present), address (wrapped) – same pattern as seller
    buyer_parts = [_pdf_text(data['buyer_name_raw'])]
    if data.get('buyer_nip', '').strip():
        buyer_parts.append(f"NIP: {data['buyer_nip'].strip()}")
    buyer_parts.append(_pdf_text(data['buyer_address_raw']))
    buyer_lines = []
    for part in buyer_parts:
        buyer_lines.extend(_wrap_text_to_lines(pdf, part, COL_WIDTH, line_height))

    # Pad to same number of lines and draw row by row so columns never overlap
    n_rows = max(len(seller_lines), len(buyer_lines))
    seller_lines.extend([""] * (n_rows - len(seller_lines)))
    buyer_lines.extend([""] * (n_rows - len(buyer_lines)))
    for i in range(n_rows):
        pdf.set_xy(pdf.l_margin, y_start + i * line_height)
        pdf.cell(COL_WIDTH, line_height, text=seller_lines[i], align='L', new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_xy(buyer_x, y_start + i * line_height)
        pdf.cell(COL_WIDTH, line_height, text=buyer_lines[i], align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(y_start + n_rows * line_height + SECTION_SPACING_LARGE)


def create_payment_details(pdf: FPDF, data: dict) -> None:
    """Create the payment details section."""
    pdf.set_font(_current_font, size=9)
    if data['bank_account']:
        pdf.cell(0, LINE_HEIGHT_MEDIUM, text=_pdf_text(_t(data, 'bank_account') + data['bank_account']),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, LINE_HEIGHT_MEDIUM, text=_pdf_text(_t(data, 'date_of_sale') + data['sale_date']),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    payment_text = _t(data, 'payment_method') if data['currency'] == 'PLN' else _t(data, 'payment_method') + data['currency']
    pdf.cell(0, LINE_HEIGHT_MEDIUM, text=_pdf_text(payment_text),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(SECTION_SPACING_LARGE)


def create_table_header(pdf: FPDF, data: dict) -> None:
    """Create the items table header with multi-line labels so long text wraps."""
    pdf.set_font(_current_font, 'B', 8)
    currency = data['currency']
    last_col = _t(data, 'col_gross') if currency == 'PLN' else currency + _t(data, 'col_gross')
    headers = [
        ('no', _t(data, 'col_no'), 'C'),
        ('name', _t(data, 'col_name'), 'L'),
        ('qty', _t(data, 'col_qty'), 'C'),
        ('unit', _t(data, 'col_unit'), 'C'),
        ('unit_price', _t(data, 'col_unit_price'), 'R'),
        ('net_price', _t(data, 'col_net_price'), 'R'),
        ('vat', _t(data, 'col_vat'), 'C'),
        ('tax', _t(data, 'col_tax'), 'R'),
        ('currency', last_col, 'R'),
    ]
    y_start = pdf.get_y()
    x_start = pdf.get_x()
    x_pos = x_start
    max_y = y_start
    header_line_height = LINE_HEIGHT_SMALL
    col_boundaries = [x_start]
    for col_key, label, align in headers:
        w = TABLE_COLUMNS[col_key]
        pdf.set_xy(x_pos, y_start)
        pdf.multi_cell(w, header_line_height, _pdf_text(label), border=1, align=align)
        max_y = max(max_y, pdf.get_y())
        x_pos += w
        col_boundaries.append(x_pos)
    # Draw vertical lines through full header height so they connect to the data rows
    for x in col_boundaries:
        pdf.line(x, y_start, x, max_y)
    pdf.set_y(max_y)
    pdf.ln(1)


def calculate_description_height(pdf: FPDF, description: str, width: float) -> float:
    """Calculate the height needed for a description that may wrap."""
    try:
        desc_lines = pdf.multi_cell(width, LINE_HEIGHT_SMALL, description, border=0,
                                     align='L', dry_run=True, output="LINES")
    except TypeError:
        # Fallback for older fpdf2 versions
        desc_lines = pdf.multi_cell(width, LINE_HEIGHT_SMALL, description, border=0,
                                     align='L', split_only=True)
    return max(MIN_ROW_HEIGHT, len(desc_lines) * ROW_HEIGHT_PER_LINE)


def create_table_items(pdf: FPDF, items: list[dict]) -> tuple[float, float, float]:
    """Create the table rows for invoice items. Returns (total_net, total_vat, total_gross)."""
    pdf.set_font(_current_font, size=8)
    total_net = 0.0
    total_vat = 0.0
    total_gross = 0.0

    for item_num, item in enumerate(items, start=1):
        total_net += item['line_total']
        total_vat += item['vat_amount']
        total_gross += item['line_gross']
        x_start, y_start = pdf.get_x(), pdf.get_y()
        desc_display = _pdf_text(item['desc_raw'])
        desc_height = calculate_description_height(pdf, desc_display, TABLE_COLUMNS['name'])

        # Row number
        pdf.cell(TABLE_COLUMNS['no'], desc_height, str(item_num), border=1,
                 align='C', new_x=XPos.RIGHT, new_y=YPos.TOP)

        # Service description (wrappable)
        x_name, y_name = pdf.get_x(), pdf.get_y()
        pdf.multi_cell(TABLE_COLUMNS['name'], LINE_HEIGHT_MEDIUM, desc_display,
                      border='LTR', align='L')
        pdf.set_xy(x_name + TABLE_COLUMNS['name'], y_name)

        # Remaining columns (net, VAT rate, VAT amount, gross)
        cells = [
            ('qty', item['qty'], 'C'),
            ('unit', item['unit'], 'C'),
            ('unit_price', f"{item['unit_price']:.2f}", 'R'),
            ('net_price', f"{item['line_total']:.2f}", 'R'),
            ('vat', item['vat_code'], 'C'),
            ('tax', f"{item['vat_amount']:.2f}", 'R'),
            ('currency', f"{item['line_gross']:.2f}", 'R'),
        ]
        for col_key, value, align in cells:
            pdf.cell(TABLE_COLUMNS[col_key], desc_height, value, border=1,
                    align=align, new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_xy(x_start, y_start + desc_height)

    return total_net, total_vat, total_gross


# Column order for table (used for boundary calculation)
_TABLE_COL_ORDER = ('no', 'name', 'qty', 'unit', 'unit_price', 'net_price', 'vat', 'tax', 'currency')


def create_table_summary(pdf: FPDF, data: dict, total_net: float, total_vat: float, total_gross: float) -> float:
    """Create the table summary rows. Returns y position of bottom of table (before spacing)."""
    pdf.set_font(_current_font, 'B', 8)

    # Total row
    summary_cells = [
        ('no', "", 'L'),
        ('name', _t(data, 'total'), 'R'),
        ('qty', "", 'L'),
        ('unit', "", 'L'),
        ('unit_price', "", 'L'),
        ('net_price', f"{total_net:.2f}", 'R'),
        ('vat', "23%", 'C'),
        ('tax', f"{total_vat:.2f}", 'R'),
        ('currency', f"{total_gross:.2f}", 'R'),
    ]
    for col_key, value, align in summary_cells:
        pdf.cell(TABLE_COLUMNS[col_key], LINE_HEIGHT_LARGE, _pdf_text(value) if value else value, border=1, align=align)
    pdf.ln()

    # "In that by rates" row
    rates_cells = [
        ('no', "", 'L'),
        ('name', _t(data, 'in_that_by_rates'), 'R'),
        ('qty', "", 'L'),
        ('unit', "", 'L'),
        ('unit_price', "", 'L'),
        ('net_price', f"{total_net:.2f}", 'R'),
        ('vat', "23%", 'C'),
        ('tax', f"{total_vat:.2f}", 'R'),
        ('currency', "", 'L'),
    ]
    for col_key, value, align in rates_cells:
        pdf.cell(TABLE_COLUMNS[col_key], LINE_HEIGHT_LARGE, _pdf_text(value) if value else value, border=1, align=align)
    return pdf.get_y()


def generate_invoice_pdf(xml_file_path: str) -> None:
    """Generate PDF invoice from KSeF XML file."""
    global _use_unicode_font, _current_font
    data = parse_invoice_data(xml_file_path)

    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    font_path = _find_unicode_font()
    if font_path:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            fonts_dir = os.path.join(script_dir, "fonts")
            pdf.add_font(UNICODE_FONT_NAME, "", font_path)
            bold_path = os.path.join(fonts_dir, "DejaVuSans-Bold.ttf")
            if os.path.isfile(bold_path):
                pdf.add_font(UNICODE_FONT_NAME, "B", bold_path)
            _use_unicode_font = True
            _current_font = UNICODE_FONT_NAME
        except Exception:
            _use_unicode_font = False
            _current_font = FONT_NAME
    else:
        _use_unicode_font = False
        _current_font = FONT_NAME

    pdf.set_font(_current_font, size=10)

    # Create PDF sections
    create_pdf_header(pdf, data)
    create_seller_buyer_section(pdf, data)
    create_payment_details(pdf, data)

    # Create items table
    y_table_top = pdf.get_y()
    create_table_header(pdf, data)
    total_net, total_vat, total_gross = create_table_items(pdf, data['items'])
    y_table_bottom = create_table_summary(pdf, data, total_net, total_vat, total_gross)

    # Draw full table vertical lines from header top to summary bottom (no breaks)
    x_table = pdf.l_margin
    x_pos = x_table
    for col_key in _TABLE_COL_ORDER:
        pdf.line(x_pos, y_table_top, x_pos, y_table_bottom)
        x_pos += TABLE_COLUMNS[col_key]
    pdf.line(x_pos, y_table_top, x_pos, y_table_bottom)

    pdf.set_y(y_table_bottom)
    pdf.ln(SECTION_SPACING_LARGE)

    # Amount due
    pdf.set_font(_current_font, 'B', 12)
    amount_due_label = _t(data, 'amount_due')
    amount_str = f"{data['total_amount']:.2f}"
    if data['currency'] == 'PLN':
        amount_str = f"PLN {amount_str}"
    pdf.cell(0, 8, text=_pdf_text(amount_due_label) + amount_str,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Save PDF to output directory
    output_path = _build_output_path(data)
    pdf.output(output_path)
    print(f"PDF saved as {output_path}")


def _build_output_path(data: dict) -> str:
    """Build the output file path from invoice data and environment settings."""
    seller_name_safe = transliterate(data['seller_name_raw'])
    filename = f"{seller_name_safe} - Invoice {data['inv_num']}-{data['inv_year']}.pdf"

    output_dir = os.getenv("OUTPUT_DIR", ".")
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    return os.path.join(output_dir, filename)


def main() -> None:
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: python invoice.py <xml_file>")
        sys.exit(1)

    generate_invoice_pdf(sys.argv[1])


if __name__ == "__main__":
    main()
