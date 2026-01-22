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

# XML namespace for KSeF invoices
KSEF_NS = {'ns': 'http://crd.gov.pl/wzor/2023/06/29/12648/'}

# PDF layout constants
COL_WIDTH = 85
GAP_BETWEEN_COLUMNS = 30
FONT_NAME = "Helvetica"
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


def get_xml_text(root: ET.Element, xpath: str, default: str = "") -> str:
    """Extract text from XML element, return default if not found."""
    element = root.find(xpath, KSEF_NS)
    return element.text if element is not None and element.text else default


def parse_invoice_data(xml_file_path: str) -> dict[str, str | float | list[dict]]:
    """Parse XML file and extract invoice data."""
    with open(xml_file_path, 'r', encoding='utf-8') as f:
        root = ET.fromstring(f.read())

    # Extract invoice header data
    inv_number = get_xml_text(root, './/ns:P_2')
    inv_num, inv_year = (inv_number.split('/') + [''])[:2]

    issue_date = get_xml_text(root, './/ns:P_1')
    sale_date = get_xml_text(root, './/ns:P_6', default=issue_date)

    # Extract seller data
    seller_name_raw = get_xml_text(root, './/ns:Podmiot1/ns:DaneIdentyfikacyjne/ns:Nazwa')
    seller_nip = get_xml_text(root, './/ns:Podmiot1/ns:DaneIdentyfikacyjne/ns:NIP')
    seller_address_raw = get_xml_text(root, './/ns:Podmiot1/ns:Adres/ns:AdresL1')

    # Extract buyer data
    buyer_name_raw = get_xml_text(root, './/ns:Podmiot2/ns:DaneIdentyfikacyjne/ns:Nazwa')
    buyer_address_raw = get_xml_text(root, './/ns:Podmiot2/ns:Adres/ns:AdresL1')

    # Extract financial data
    currency = get_xml_text(root, './/ns:KodWaluty')
    total_amount = float(get_xml_text(root, './/ns:P_15', '0'))

    # Extract KSeF number from filename or environment
    ksef_number = os.getenv("KSEF_NUMBER", os.path.splitext(os.path.basename(xml_file_path))[0])

    # Get bank account from environment variable
    account_env_var = f"ACCOUNT_{currency}"
    bank_account = os.getenv(account_env_var, "")
    if not bank_account:
        print(f"Warning: {account_env_var} environment variable not set")

    # Extract invoice items
    items = []
    for wiersz in root.findall('.//ns:FaWiersz', KSEF_NS):
        items.append({
            'desc': transliterate(get_xml_text(wiersz, 'ns:P_7')),
            'unit': get_xml_text(wiersz, 'ns:P_8A'),
            'qty': get_xml_text(wiersz, 'ns:P_8B'),
            'unit_price': float(get_xml_text(wiersz, 'ns:P_9A', '0')),
            'line_total': float(get_xml_text(wiersz, 'ns:P_11', '0')),
            'vat_code': get_xml_text(wiersz, 'ns:P_12', 'np.')
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
        'buyer_name': transliterate(buyer_name_raw),
        'buyer_address': transliterate(buyer_address_raw),
        'currency': currency,
        'total_amount': total_amount,
        'ksef_number': ksef_number,
        'bank_account': bank_account,
        'items': items
    }


def create_pdf_header(pdf: FPDF, data: dict) -> None:
    """Create the invoice header section."""
    pdf.set_font(FONT_NAME, 'B', 14)
    pdf.cell(0, 8, text=f"Invoice No. {data['inv_number']}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(SECTION_SPACING_SMALL)

    pdf.set_font(FONT_NAME, size=9)
    pdf.cell(0, LINE_HEIGHT_LARGE, text=f"Date of issue {data['issue_date']}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    if data['ksef_number']:
        pdf.ln(0.5)
        pdf.set_font(FONT_NAME, size=8)
        pdf.cell(0, LINE_HEIGHT_MEDIUM, text=f"KSeF Number: {data['ksef_number']}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    pdf.ln(SECTION_SPACING_MEDIUM)


def create_seller_buyer_section(pdf: FPDF, data: dict) -> None:
    """Create the seller and buyer information section."""
    pdf.set_font(FONT_NAME, 'B', 10)
    pdf.cell(COL_WIDTH, LINE_HEIGHT_LARGE, text="Seller:", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_xy(COL_WIDTH + GAP_BETWEEN_COLUMNS, pdf.get_y())
    pdf.cell(COL_WIDTH, LINE_HEIGHT_LARGE, text="Buyer:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(FONT_NAME, size=9)
    y_start = pdf.get_y()

    # Build seller text
    seller_parts = [data['seller_name']]
    if data['seller_nip']:
        seller_parts.append(f"NIP: {data['seller_nip']}")
    seller_parts.append(data['seller_address'])

    pdf.multi_cell(COL_WIDTH, LINE_HEIGHT_MEDIUM, text='\n'.join(seller_parts))
    y_after_seller = pdf.get_y()

    # Add buyer info in second column
    pdf.set_xy(COL_WIDTH + GAP_BETWEEN_COLUMNS, y_start)
    buyer_text = f"{data['buyer_name']}\n{data['buyer_address']}"
    pdf.multi_cell(COL_WIDTH, LINE_HEIGHT_MEDIUM, text=buyer_text)

    pdf.set_y(max(y_after_seller, pdf.get_y()) + SECTION_SPACING_LARGE)


def create_payment_details(pdf: FPDF, data: dict) -> None:
    """Create the payment details section."""
    pdf.set_font(FONT_NAME, size=9)
    if data['bank_account']:
        pdf.cell(0, LINE_HEIGHT_MEDIUM, text=f"Bank account: {data['bank_account']}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, LINE_HEIGHT_MEDIUM, text=f"Date of sale: {data['sale_date']}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, LINE_HEIGHT_MEDIUM, text=f"Payment method: Bank transfer in {data['currency']}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(SECTION_SPACING_LARGE)


def create_table_header(pdf: FPDF, currency: str) -> None:
    """Create the items table header."""
    pdf.set_font(FONT_NAME, 'B', 8)
    headers = [
        ('no', "No.", 'C'),
        ('name', "Name of service", 'L'),
        ('qty', "Quantity", 'C'),
        ('unit', "Unit", 'C'),
        ('unit_price', "Unit net price", 'R'),
        ('net_price', "Net price", 'R'),
        ('vat', "VAT tax rate", 'C'),
        ('tax', "Total Tax", 'R'),
        ('currency', f"{currency} value", 'R'),
    ]
    for col_key, label, align in headers:
        pdf.cell(TABLE_COLUMNS[col_key], LINE_HEIGHT_LARGE, label, border=1, align=align)
    pdf.ln()


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


def create_table_items(pdf: FPDF, items: list[dict]) -> float:
    """Create the table rows for invoice items."""
    pdf.set_font(FONT_NAME, size=8)
    total_net = 0.0

    for item_num, item in enumerate(items, start=1):
        total_net += item['line_total']
        x_start, y_start = pdf.get_x(), pdf.get_y()
        desc_height = calculate_description_height(pdf, item['desc'], TABLE_COLUMNS['name'])

        # Row number
        pdf.cell(TABLE_COLUMNS['no'], desc_height, str(item_num), border=1,
                 align='C', new_x=XPos.RIGHT, new_y=YPos.TOP)

        # Service description (wrappable)
        x_name, y_name = pdf.get_x(), pdf.get_y()
        pdf.multi_cell(TABLE_COLUMNS['name'], LINE_HEIGHT_MEDIUM, item['desc'],
                      border='LTR', align='L')
        pdf.set_xy(x_name + TABLE_COLUMNS['name'], y_name)

        # Remaining columns
        cells = [
            ('qty', item['qty'], 'C'),
            ('unit', item['unit'], 'C'),
            ('unit_price', f"{item['unit_price']:.2f}", 'R'),
            ('net_price', f"{item['line_total']:.2f}", 'R'),
            ('vat', item['vat_code'], 'C'),
            ('tax', "0.00", 'R'),  # VAT exempt
            ('currency', f"{item['line_total']:.2f}", 'R'),
        ]
        for col_key, value, align in cells:
            pdf.cell(TABLE_COLUMNS[col_key], desc_height, value, border=1,
                    align=align, new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_xy(x_start, y_start + desc_height)

    return total_net


def create_table_summary(pdf: FPDF, total_net: float) -> None:
    """Create the table summary rows."""
    pdf.set_font(FONT_NAME, 'B', 8)

    # Total row
    summary_cells = [
        ('no', "", 'L'),
        ('name', "Total", 'R'),
        ('qty', "", 'L'),
        ('unit', "", 'L'),
        ('unit_price', "", 'L'),
        ('net_price', f"{total_net:.2f}", 'R'),
        ('vat', "np.", 'C'),
        ('tax', "0.00", 'R'),
        ('currency', f"{total_net:.2f}", 'R'),
    ]
    for col_key, value, align in summary_cells:
        pdf.cell(TABLE_COLUMNS[col_key], LINE_HEIGHT_LARGE, value, border=1, align=align)
    pdf.ln()

    # "In that by rates" row
    rates_cells = [
        ('no', "", 'L'),
        ('name', "in that by rates", 'R'),
        ('qty', "", 'L'),
        ('unit', "", 'L'),
        ('unit_price', "", 'L'),
        ('net_price', f"{total_net:.2f}", 'R'),
        ('vat', "np.", 'C'),
        ('tax', "0.00", 'R'),
        ('currency', "", 'L'),
    ]
    for col_key, value, align in rates_cells:
        pdf.cell(TABLE_COLUMNS[col_key], LINE_HEIGHT_LARGE, value, border=1, align=align)
    pdf.ln(SECTION_SPACING_LARGE)


def generate_invoice_pdf(xml_file_path: str) -> None:
    """Generate PDF invoice from KSeF XML file."""
    data = parse_invoice_data(xml_file_path)

    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font(FONT_NAME, size=10)

    # Create PDF sections
    create_pdf_header(pdf, data)
    create_seller_buyer_section(pdf, data)
    create_payment_details(pdf, data)

    # Create items table
    create_table_header(pdf, data['currency'])
    total_net = create_table_items(pdf, data['items'])
    create_table_summary(pdf, total_net)

    # Amount due
    pdf.set_font(FONT_NAME, 'B', 12)
    pdf.cell(0, 8, text=f"Amount due: ${data['total_amount']:.2f}",
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
