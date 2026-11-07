"""Builds a synthetic DOCX seeded with every hidden-content type. Synthetic data only."""
import sys, copy
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt

out = sys.argv[1]
d = docx.Document()
cp = d.core_properties
cp.author = "Harriet Okonkwo-Bell"; cp.last_modified_by = "Dev Mehta"; cp.title = "Re: Thornfield v Castellane"
cp.subject = "Matter TF-2026-0417"; cp.keywords = "Castellane, settlement"; cp.comments = "Draft shared with client Marcus Thornfield"
cp.category = "Litigation"

# Header / footer
sec = d.sections[0]
sec.header.paragraphs[0].text = "PRIVILEGED – Thornfield v Castellane Holdings – ref TF-2026-0417"
sec.footer.paragraphs[0].text = "Prepared by Harriet Okonkwo-Bell, 0161 496 0712"

d.add_heading("Attendance note", level=1)
p = d.add_paragraph("I met the client, Marcus Thornfield, at his home at 7 Larkspur Close, Altrincham WA14 2QL. ")
# tracked insertion
ins = OxmlElement("w:ins"); ins.set(qn("w:id"), "101"); ins.set(qn("w:author"), "Dev Mehta"); ins.set(qn("w:date"), "2026-11-02T10:00:00Z")
r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = "His sister Imogen Thornfield was also present. "; t.set(qn("xml:space"), "preserve"); r.append(t); ins.append(r); p._p.append(ins)
# tracked deletion
dele = OxmlElement("w:del"); dele.set(qn("w:id"), "102"); dele.set(qn("w:author"), "Harriet Okonkwo-Bell"); dele.set(qn("w:date"), "2026-11-02T10:05:00Z")
r2 = OxmlElement("w:r"); dt = OxmlElement("w:delText"); dt.text = "He mentioned his NI number is PX 44 19 02 C. "; dt.set(qn("xml:space"), "preserve"); r2.append(dt); dele.append(r2); p._p.append(dele)

p2 = d.add_paragraph("The opposing party is Castellane Holdings Ltd, director Yusuf Castellane. ")
# hidden (vanish) run
run = p2.add_run("Private note: Yusuf's mobile is 07911 123456.")
rpr = run._r.get_or_add_rPr(); v = OxmlElement("w:vanish"); rpr.append(v)

# comment (python-docx >= 1.2)
p3 = d.add_paragraph("Settlement proposed at £185,000 payable within 28 days.")
try:
    d.add_comment(p3.runs, text="Check with Priya Castellane whether the trust account 40-12-88 / 71002934 is still live.", author="Dev Mehta", initials="DM")
except Exception as e:
    print("comment unsupported:", e)

# footnote: build footnotes part manually
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import Part
from docx.opc.packuri import PackURI
fn_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
 '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
 '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
 '<w:footnote w:id="1"><w:p><w:r><w:t xml:space="preserve">See witness statement of Beatrix Lund, DOB 03/09/1979, passport 541203987.</w:t></w:r></w:p></w:footnote>'
 '</w:footnotes>')
fn_part = Part(PackURI("/word/footnotes.xml"), "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml", fn_xml.encode(), d.part.package)
d.part.relate_to(fn_part, RT.FOOTNOTES)
p4 = d.add_paragraph("Liability is disputed on the facts")
r3 = OxmlElement("w:r"); rp = OxmlElement("w:rPr"); vs = OxmlElement("w:vertAlign"); vs.set(qn("w:val"), "superscript"); rp.append(vs); r3.append(rp)
ref = OxmlElement("w:footnoteReference"); ref.set(qn("w:id"), "1"); r3.append(ref); p4._p.append(r3)
p4.add_run(".")

# text box
p5 = d.add_paragraph()
r5 = OxmlElement("w:r"); pict = OxmlElement("w:pict")
shape = OxmlElement("v:shape") if False else None
# build with raw xml for the v: namespace
from lxml import etree
tb = etree.fromstring(
 '<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:v="urn:schemas-microsoft-com:vml">'
 '<v:shape><v:textbox><w:txbxContent><w:p><w:r><w:t>Call Dr Anneliese Vogt (consultant) on 020 7946 0318 re medical report.</w:t></w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict>')
r5.append(tb); p5._p.append(r5)

# table
tbl = d.add_table(rows=2, cols=2)
tbl.cell(0,0).text = "Payee"; tbl.cell(0,1).text = "Sort code / account"
tbl.cell(1,0).text = "Thornfield, M"; tbl.cell(1,1).text = "20-45-67 12309876"

# custom properties
cust_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
 '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="ClientEmail"><vt:lpwstr>marcus.thornfield@example.com</vt:lpwstr></property>'
 '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="3" name="FeeEarner"><vt:lpwstr>Harriet Okonkwo-Bell</vt:lpwstr></property>'
 '</Properties>')
cust = Part(PackURI("/docProps/custom.xml"), "application/vnd.openxmlformats-officedocument.custom-properties+xml", cust_xml.encode(), d.part.package)
d.part.package.relate_to(cust, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties")

d.save(out)
print("wrote", out)
