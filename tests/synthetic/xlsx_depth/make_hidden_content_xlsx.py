"""Builds a synthetic XLSX seeded with every hidden-content type. Synthetic data only."""
import sys
import openpyxl
from openpyxl.comments import Comment
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

out = sys.argv[1]
wb = openpyxl.Workbook()
wb.properties.creator = "Harriet Okonkwo-Bell"
wb.properties.lastModifiedBy = "Dev Mehta"
wb.properties.title = "Schedule of loss – Thornfield"
wb.properties.description = "Prepared for client Marcus Thornfield, matter TF-2026-0417"
wb.properties.keywords = "Castellane; schedule of loss"

ws = wb.active; ws.title = "Schedule of Loss"
ws.append(["Head of loss", "Amount", "Payee", "Notes", "NI number"])
ws.append(["Loss of earnings", 31400, "Marcus Thornfield", "Per payslips", "PX 44 19 02 C"])
ws.append(["Care costs", 4800, "Imogen Thornfield", "Sister, gratuitous care", "JH 55 20 31 D"])
ws.append(["Bank details", None, "Thornfield, M", "Sort 20-45-67 acct 12309876", None])   # row 4 will be hidden
ws.append(["Total", "=SUM(B2:B4)", None, None, None])
ws.append(["Client label", '="Client: "&C2&" ("&E2&")"', None, None, None])             # formula with no cached value
ws.row_dimensions[4].hidden = True
ws.column_dimensions["E"].hidden = True
ws["B2"].comment = Comment("Confirmed with Marcus on 07700 900321 – do not disclose to Castellane.", "Dev Mehta")
ws["C3"].hyperlink = "mailto:imogen.thornfield@example.com"
ws.oddHeader.center.text = "Thornfield v Castellane Holdings – TF-2026-0417"
ws.oddFooter.left.text = "Fee earner: Harriet Okonkwo-Bell"
dv = DataValidation(type="list", formula1='"Marcus Thornfield,Imogen Thornfield,Yusuf Castellane"', allow_blank=True)
ws.add_data_validation(dv); dv.add("C2:C20")

notes = wb.create_sheet("Notes"); notes.sheet_state = "hidden"
notes.append(["Client lives at 7 Larkspur Close, Altrincham WA14 2QL. Daughter Beatrix (aged 6) at Oakfield Primary."])

keys = wb.create_sheet("Internal"); keys.sheet_state = "veryHidden"
keys.append(["Opponent director", "Yusuf Castellane", "DOB 14/02/1971", "passport 541203987"])

wb.defined_names["ClientEmail"] = DefinedName("ClientEmail", attr_text='"marcus.thornfield@example.com"')
wb.defined_names["OpponentRef"] = DefinedName("OpponentRef", attr_text="'Schedule of Loss'!$D$4")

wb.save(out); print("wrote", out)
