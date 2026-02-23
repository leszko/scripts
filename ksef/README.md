# KSeF Invoice PDF Generator

This script generates PDF invoices from KSeF (Krajowy System e-Faktur) XML files.

## Prerequisites

- Python 3.8 or higher
- [uv](https://github.com/astral-sh/uv) package manager (or pip)

## Setup

1. Install dependencies using uv:
   ```bash
   uv sync
   ```

   Or using pip:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your personal details:

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` with your actual bank account numbers and output directory.

   The script will automatically use the appropriate account based on the invoice currency (USD or PLN).

## Usage

Run the script with the XML file as an argument:

```bash
uv run python invoice.py <path_to_xml_file>
```

Example:
```bash
uv run python invoice.py ~/Downloads/ksef-number.xml
```

## Output

The script will:
- Generate a PDF invoice with the format: `{Seller Name} - Invoice {number}-{year}.pdf`
- Save it to the directory specified in `OUTPUT_DIR` environment variable (or current directory if not set)
- Extract the KSeF number from the XML filename

## Polish characters

For PLN invoices, the PDF is generated in Polish. Polish diacritics (ą, ę, ł, ó, ś, ź, ż, etc.) are shown when a Unicode-capable font is available. The script looks for **DejaVu Sans** in `ksef/fonts/` (included) or in system paths; you can override with `PDF_FONT_PATH` (path to a `.ttf` file).

## Environment Variables

- `ACCOUNT_USD`: Bank account number for USD invoices
- `ACCOUNT_PLN`: Bank account number for PLN invoices
- `OUTPUT_DIR`: Directory where PDF files will be saved (defaults to current directory)
- `KSEF_NUMBER`: Optional override for KSeF number (normally extracted from filename)
- `PDF_FONT_PATH`: Optional path to a TTF font that supports Polish (e.g. DejaVu Sans); used for correct ą, ę, ó, etc. in the PDF

