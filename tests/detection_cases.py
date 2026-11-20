"""
Detection regression cases. Every value here is synthetic or taken from public court text.

Each case:  text, must_mask (every occurrence must be covered by a detected span),
            must_not_mask (no occurrence may be touched by a detected span).
The cases are grouped by the failure they guard against, not by document, so a new
document type gets a new group rather than edits to existing ones.
"""

# --- Lawyer test 1: IHS confirmation email printed from Gmail (synthetic values, UKVI template wording)
IHS_EMAIL = """Gmail - Your Immigration Health Surcharge

GOV.UK

UK Visas & Immigration
Immigration health surcharge complete
Date: 14 Oct 2026
Name: MS AMARA OKONKWO
IHS reference number: IHS204518736

This email confirms your immigration health surcharge (IHS) reference number.

If you made a payment, you should have received a separate email receipt from Worldpay.

What you need to do next
Finish your visa application and include your IHS reference number. Your visa application number is GWF071234567.

If you're applying in person at a premium service centre, you'll need your IHS reference number when you attend your appointment.

Amount paid: £2,070.00. Questions: amara.okonkwo@example.com

Gmail - Your Immigration Health Surcharge"""

# --- Lawyer test 2: public CJEU judgment (C-25/17), opening and paragraphs as published
CJEU_JUDGMENT = """Judgment of the Court (Grand Chamber) of 10 July 2018. Proceedings brought by Tietosuojavaltuutettu. Request for a preliminary ruling from the Korkein hallinto-oikeus. Reference for a preliminary ruling — Protection of individuals with regard to the processing of personal data — Directive 95/46/EC — Scope of the directive — Article 3 — Data collected and processed by the members of a religious community in the course of their door-to-door preaching — Article 2(c) — Definition of a ‘personal data filing system’.

Case C‑25/17. ECLI:EU:C:2018:551.

1) This request for a preliminary ruling concerns the interpretation of Article 2(c) and (d) and Article 3 of Directive 95/46/EC of the European Parliament and of the Council of 24 October 1995 on the protection of individuals with regard to the processing of personal data and on the free movement of such data (OJ 1995 L 281, p. 31) read in the light of Article 10 of the Charter of Fundamental Rights of the European Union (‘the Charter’).

2) The request has been made in proceedings brought by the Tietosuojavaltuutettu (Data Protection Supervisor, Finland) concerning a decision of the tietosuojalautakunta (Data Protection Board, Finland).

18) As regards the need for the present request for a preliminary ruling, the Korkein hallinto-oikeus (Supreme Administrative Court) takes the view that the examination of the case in the main proceedings requires consideration to be given to the rights to privacy and protection of personal data.

47) The Charter adopts a broad understanding of the concept of ‘religion’ (judgment of 29 May 2018, Liga van Moskeeën en Islamitische Organisaties Provincie Antwerpen VZW and Others, C‑426/16, EU:C:2018:335, paragraph 44 and the case-law cited)."""

CASES = [
    # ---------------- Lawyer feedback ----------------
    dict(name="ihs_email", text=IHS_EMAIL,
         must_mask=["AMARA OKONKWO", "IHS204518736", "GWF071234567", "amara.okonkwo@example.com"],
         must_not_mask=["Surcharge", "surcharge", "Request"]),
    dict(name="cjeu_public_judgment", text=CJEU_JUDGMENT,
         must_mask=[],
         must_not_mask=["Request", "Korkein", "Directive 95/46/EC", "EC", "C‑25/17", "C‑426/16",
                        "EU:C:2018:551", "European Parliament", "Charter of Fundamental Rights",
                        "Tietosuojavaltuutettu", "Article 3", "Grand Chamber", "Data Protection Board",
                        "Liga van Moskeeën en Islamitische Organisaties Provincie Antwerpen VZW"]),
    dict(name="cited_case_vs_client", text="My client John Doe relies on Smith v Jones [2019] EWCA Civ 123 and on Brown v Green Ltd [2020] UKSC 4.",
         must_mask=["John Doe"], must_not_mask=["Smith v Jones", "Brown v Green Ltd"]),
    dict(name="uan_and_card", text="UAN 3434-0459-5933-5591 is on the letter. Card 4539 1488 0343 6467 was charged.",
         must_mask=["3434-0459-5933-5591", "4539 1488 0343 6467"], must_not_mask=[]),
    dict(name="labelled_reference", text="Policy number: PX-77120-B. Booking ref: 8KQ2ZT. Claim No. KB-2026-000123.",
         must_mask=["PX-77120-B", "8KQ2ZT", "KB-2026-000123"], must_not_mask=[]),
    dict(name="brp_number", text="Her BRP number is ZU1234567 and expires next year.",
         must_mask=["ZU1234567"], must_not_mask=[]),

    # ---------------- Review findings ----------------
    dict(name="venue_substring", text="The witness, Courtney Hale, met Simon Harcourt at the office on Monday.",
         must_mask=["Courtney Hale", "Simon Harcourt"], must_not_mask=["Monday"]),
    dict(name="caps_pleading", text="BETWEEN:\n\nJOHN ALDRIDGE\nClaimant\n\nand\n\nHALDEN LOGISTICS LIMITED\nDefendant\n\nJohn Aldridge says the goods were late. Mr Aldridge was not paid.",
         must_mask=["JOHN ALDRIDGE", "HALDEN LOGISTICS LIMITED", "John Aldridge", "Aldridge"],
         must_not_mask=["Claimant", "Defendant", "BETWEEN"]),
    dict(name="irish_name", text="The claimant Oluwaseun Adeyemi and her sister Siobhan Ní Bhriain instructed us. Ms Ní Bhriain was present.",
         must_mask=["Oluwaseun Adeyemi", "Siobhan Ní Bhriain", "Ní Bhriain"], must_not_mask=[]),
    dict(name="surname_first", text="Hearing list: SMITH, John v PATEL, Meena. Listed for 10:30.",
         must_mask=["SMITH, John", "PATEL, Meena"], must_not_mask=[]),
    dict(name="spouses", text="Mr Daniel Hale attended with his wife. Mrs Hale signed the consent form. Daniel Hale left early.",
         must_mask=["Mr Daniel Hale", "Mrs Hale", "Daniel Hale"], must_not_mask=[]),
    dict(name="every_occurrence", text="Priya Raghunathan joined in 2019.\n\nThe board thanked Priya Raghunathan.\n\nRaghunathan resigned.",
         must_mask=["Priya Raghunathan", "Raghunathan"], must_not_mask=[]),

    # ---------------- Found by reading redacted output of realistic documents ----------------
    dict(name="defined_term", text='I was employed by Ashworth Care Homes Limited ("Ashworth") from 2021. My mother later called Ashworth to complain. The Company ("the Company") agreed.',
         must_mask=["Ashworth Care Homes Limited", "Ashworth"], must_not_mask=["the Company"]),
    dict(name="relative_is_other_person", text="Client: Jonathan Vance. Jonathan Vance said his wife, Mrs Vance, has concerns.",
         must_mask=["Jonathan Vance", "Mrs Vance"], must_not_mask=[]),
    dict(name="name_of_address", text="Made between Brightwater Solutions Ltd and Oluwaseun Adeyemi of Flat 3, 41 Elm Street, Croydon CR0 2PL. Signed by Oluwaseun Adeyemi.",
         must_mask=["Oluwaseun Adeyemi", "41 Elm Street", "CR0 2PL"], must_not_mask=[]),
    dict(name="exhibit_and_town", text="I, Meena Patel, of 22 Willow Grove, Leicester LE2 7QP, say. Dr Helen O'Connor of Leicester Royal Infirmary examined me. Her report is exhibited as MP/1.",
         must_mask=["Meena Patel", "Helen O'Connor", "MP/1", "LE2 7QP"], must_not_mask=["Leicester Royal Infirmary"]),
    dict(name="table_header_labels", text="Client | Matter Ref | Sort Code | Account | Amount | Contact\n\nName | Role | Email",
         must_mask=[], must_not_mask=["Client", "Matter Ref", "Role", "Name"]),
    dict(name="possessive", text="P. Smith (finance director) to call. Peter Smith's direct line is 020 7946 0321. John Smith is not involved.",
         must_mask=["P. Smith", "Peter Smith", "John Smith"], must_not_mask=[]),

    dict(name="deceased_heading", text="ESTATE OF THE LATE MARGARET ANNE FOSTER\n\nExecutors: Mr Robert Foster (son). Contact Robert on robert.foster@example.net.",
         must_mask=["MARGARET ANNE FOSTER", "Robert Foster", "robert.foster@example.net"], must_not_mask=["ESTATE"]),
    dict(name="company_with_brackets", text="BETWEEN\nDEREK ANTHONY HOLLOWAY\nClaimant\n-and-\nSUNRISE LETTINGS (NORTH WEST) LIMITED\nDefendant\n\nORDER\n\nIN THE COUNTY COURT AT MANCHESTER. Hearing at 1 Bridge Street, Manchester M60 9DJ.",
         must_mask=["DEREK ANTHONY HOLLOWAY", "SUNRISE LETTINGS (NORTH WEST) LIMITED", "M60 9DJ"], must_not_mask=["ORDER", "MANCHESTER"]),
    dict(name="name_in_email_not_ordinary", text="Name: MS AMARA OKONKWO. Okonkwo confirmed by email to amara.okonkwo@example.com.",
         must_mask=["AMARA OKONKWO", "Okonkwo"], must_not_mask=[]),
    dict(name="certificate_number", text="Acas early conciliation certificate number: R123456/26/78.",
         must_mask=["R123456/26/78"], must_not_mask=[]),

    # ---------------- Lawyer test 3: Indian letter of recommendation ----------------
    dict(name="lor_first_name_is_person", text=open(__file__.replace("detection_cases.py", "fixtures/lor.txt"), encoding="utf-8").read(),
         must_mask=["Amaan Siddiqui", "Amaan", "Dr. Satya Prakash Singh", "+91-9818526340", "98185 26341", "satya.prakash@nsut.ac.in"],
         must_not_mask=["Associate Professor", "New Delhi"]),
    dict(name="phones_international", text=(
            "UK 07700 900481 and +44 (0) 20 7946 0958. India +91 98185 26340. Pakistan +92 300 1234567. "
            "Nigeria +234 803 123 4567. US +1 415-555-0132. WhatsApp: 0300 1234567. Tel. no: 2025550143."),
         must_mask=["07700 900481", "+44 (0) 20 7946 0958", "+91 98185 26340", "+92 300 1234567", "+234 803 123 4567",
                    "+1 415-555-0132", "0300 1234567", "2025550143"], must_not_mask=[]),
    dict(name="phones_no_false_positives", text=(
            "Company number 09876543. ISBN 9780140449136. Batch 20261014. Paid £2,070.00 on 14/10/2026. "
            "Sort code 20-32-06, account 43918265. Claim No. KB-2026-000123. Between 2019 and 2020. "
            "Section 43B of the Employment Rights Act 1996. (OJ 1995 L 281, p. 31). Paragraphs 12-14 and 101-105."),
         must_mask=["43918265", "20-32-06"],
         must_not_mask=["09876543", "9780140449136", "20261014", "14/10/2026", "2019", "1996", "281", "101-105"]),

    # ---------------- Behaviour fixed in PR5, must not regress ----------------
    dict(name="pr5_reclassified_person", text="Marcus Sterling (Executive) signed. Halden Logistics Ltd employs Marcus Sterling.",
         must_mask=["Marcus Sterling", "Halden Logistics Ltd"], must_not_mask=[]),
    dict(name="pr5_org_first_name", text="Morgan Stanley and John Lewis are counterparties.",
         must_mask=["Morgan Stanley", "John Lewis"], must_not_mask=[]),
    dict(name="pr5_dob_carveout", text="Claimant: Peter Smith, DOB 01/02/1985, NI QQ 12 34 56 C.",
         must_mask=["Peter Smith", "01/02/1985", "QQ 12 34 56 C"], must_not_mask=[]),
    dict(name="pr5_phone_sortcode", text="Call +44 (0) 20 7946 0958. Sort code 20-45-12, account 12345678. Hearing on 12 03 26.",
         must_mask=["+44 (0) 20 7946 0958", "20-45-12", "12345678"], must_not_mask=["12 03 26"]),
    dict(name="pr5_common_words", text="Rose Grant gave evidence. Prices rose after the grant was made. Grant of probate followed.",
         must_mask=["Rose Grant"], must_not_mask=["rose", "grant"]),
]

# Placeholder text each entity type should produce, and pairs that must share a placeholder.
SAME_PERSON = [
    ("lor_first_name_is_person", "Amaan Siddiqui", "Amaan"),
    ("pr5_reclassified_person", "Marcus Sterling", "Marcus Sterling"),
    ("caps_pleading", "JOHN ALDRIDGE", "John Aldridge"),
    ("every_occurrence", "Priya Raghunathan", "Raghunathan"),
    ("defined_term", "Ashworth Care Homes Limited", "Ashworth"),
    ("possessive", "P. Smith", "Peter Smith"),
    ("name_of_address", "Oluwaseun Adeyemi", "Oluwaseun Adeyemi"),
]
DIFFERENT_PEOPLE = [("deceased_heading", "MARGARET ANNE FOSTER", "Mr Robert Foster"), ("relative_is_other_person", "Mrs Vance", "Jonathan Vance"), ("possessive", "Peter Smith", "John Smith"),
                    ("spouses", "Mrs Hale", "Daniel Hale"), ("surname_first", "SMITH, John", "PATEL, Meena")]
