# PDF Skill

## Purpose
Give Claude full end-to-end PDF mastery: read, extract, parse, merge, split, rotate, watermark, fill forms, and generate PDFs from scratch.

## When to Use This Skill
- Extracting text or tables from PDF reports, contracts, or research papers
- Merging multiple PDFs into a single document
- Splitting a large PDF into individual pages or sections
- Filling out PDF forms programmatically
- Adding watermarks, page numbers, or annotations
- Converting PDF content into structured data (JSON, CSV, Markdown)

## How It Works
This skill loads specialized PDF handling patterns and instructs Claude to use appropriate Python libraries (pypdf, pdfplumber, reportlab, pymupdf) with correct method calls, error handling, and output formatting for every PDF operation.

## Instructions for Claude
When a PDF task is requested:
1. Identify the operation type: read/extract, manipulate (merge/split/rotate), annotate, form-fill, or generate
2. Select the appropriate library:
   - **pdfplumber** → text and table extraction
   - **pypdf** → merge, split, rotate, metadata
   - **reportlab** → generate PDFs from scratch
   - **pymupdf (fitz)** → annotations, watermarks, form filling
3. Write complete, runnable Python code with proper error handling
4. Always verify the output file was created successfully
5. Return extracted content in clean, structured format (Markdown tables for tabular data)

## Examples

### Extract text from a PDF
```python
import pdfplumber
with pdfplumber.open('report.pdf') as pdf:
    for page in pdf.pages:
        print(page.extract_text())
