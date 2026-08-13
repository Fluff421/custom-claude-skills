
***

## 3. `office-documents/SKILL.md`

```markdown
# Office Documents Skill (DOCX / PPTX / XLSX)

## Purpose
Create, read, edit, and format Microsoft Word documents (.docx), PowerPoint presentations (.pptx), and Excel workbooks (.xlsx) with proper structure, formulas, charts, and professional styling — outputting production-ready files instead of Markdown approximations.

## When to Use This Skill
- Generating Word reports, proposals, or contracts with proper headings, tables, and formatting
- Building PowerPoint decks with slides, layouts, and speaker notes
- Creating or manipulating Excel workbooks with formulas, named ranges, charts, and pivot tables
- Converting data (JSON, CSV, dict) directly into formatted Office files
- Automating repetitive document creation tasks

## How It Works
Uses python-docx, python-pptx, and openpyxl — the standard Python libraries for Office automation — with correct API calls, styling patterns, and best practices for each format.

## Instructions for Claude

### For DOCX (python-docx)
1. Use `Document()` to create or open files
2. Apply built-in styles: 'Heading 1', 'Heading 2', 'Normal', 'Table Grid'
3. Always set font name and size explicitly for custom styling
4. Use `add_table()` with proper column widths for tabular data
5. Save with descriptive filename

### For PPTX (python-pptx)
1. Use `Presentation()` and select appropriate slide layouts
2. Access placeholders by index: title=0, content=1
3. Use `Inches()` and `Pt()` for measurements
4. Add charts using `add_chart()` with ChartData objects
5. Always include speaker notes for presentation slides

### For XLSX (openpyxl)
1. Use `Workbook()` and name sheets meaningfully
2. Apply `PatternFill`, `Font`, and `Border` for professional styling
3. Use `write_only=True` mode for large datasets (>10k rows)
4. Add charts with `BarChart`, `LineChart`, `PieChart` objects
5. Freeze panes on header rows: `ws.freeze_panes = 'A2'`

## Examples

### Create a styled Word report
```python
from docx import Document
from docx.shared import Pt
doc = Document()
doc.add_heading('Quarterly Report', 0)
p = doc.add_paragraph('Executive Summary: ')
p.add_run('Revenue grew 23% YoY.').bold = True
doc.add_heading('Key Metrics', level=1)
table = doc.add_table(rows=1, cols=3, style='Table Grid')
table.rows.cells.text = 'Metric'
table.rows.cells[1].text = 'Q3'
table.rows.cells[2].text = 'Q4'
doc.save('quarterly_report.docx')
