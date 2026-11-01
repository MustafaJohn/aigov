import re
from typing import List, Dict, Any

# UK and International PII regular expression patterns
PATTERNS = {
    "NI_NUMBER": {
        "regex": re.compile(r"\b(?:[A-CEGHJ-PR-TW-Z]{2}|QQ)\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE),
        "label": "National Insurance No.",
        "placeholder_type": "NI NUMBER"
    },
    "SORT_CODE": {
        "regex": re.compile(r"\b(?:\d{2}-\d{2}-\d{2}|\d{2}\s\d{2}\s\d{2})\b"),
        "label": "Sort Code",
        "placeholder_type": "SORT CODE"
    },
    "ACCOUNT_NUMBER": {
        # Require bank/account context: Account, Account Number, Account No, A/C, Bank Acc
        "regex": re.compile(r"(?i:\b(?:acc(?:ount)?(?:\s+(?:no\.?|number))?|a\/c|bank\s+acc(?:ount)?)\s*[:#\-|]?\s*)(\d{8,10})\b"),
        "label": "Bank Account No.",
        "placeholder_type": "ACCOUNT"
    },
    "CREDIT_CARD": {
        "regex": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "label": "Card Number",
        "placeholder_type": "CARD"
    },
    "UK_POSTCODE": {
        "regex": re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE),
        "label": "UK Postcode",
        "placeholder_type": "POSTCODE"
    },
    "PHYSICAL_ADDRESS": {
        "regex": re.compile(
            r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|Road|Avenue|Lane|Drive|Grove|Way|Close|Gardens|Court|Boulevard|Hill|Walk|Terrace|Square|Crescent)(?:,\s*[A-Z][a-z]+)?\b"
        ),
        "label": "Street Address",
        "placeholder_type": "ADDRESS"
    },
    "EMAIL": {
        "regex": re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),
        "label": "Email Address",
        "placeholder_type": "EMAIL"
    },
    "PHONE": {
        "regex": re.compile(r"(?<!\w)(?:(?:\+44\s?|0)(?:20\s?\d{4}|1\d{3}\s?\d{3}|7\d{3}\s?\d{3})\s?\d{3,4}|\+?[0-9]{1,3}[-.\s]\(?\d{2,4}\)?[-.\s]\d{3}[-.\s]\d{3,4})\b"),
        "label": "Phone Number",
        "placeholder_type": "PHONE"
    },
    "PASSPORT": {
        "regex": re.compile(r"(?i:\b(?:passport|ppt|passport\s+no\.?|passport\s+number)\s*[:#\-–]?\s*)([A-Z0-9]{8,10})\b"),
        "label": "Passport Number",
        "placeholder_type": "PASSPORT"
    },
    "DRIVING_LICENCE": {
        "regex": re.compile(r"(?i:\b(?:driving\s+licence|driver\s+licence|licence\s+no\.?)\s*[:#-]?\s*)([A-Z0-9\s]{8,18})\b|\b([A-Z]{5}\d{6}[A-Z0-9]{5})\b"),
        "label": "Driving Licence No.",
        "placeholder_type": "DRIVING LICENCE"
    },
    "MATTER_REF": {
        "regex": re.compile(r"\b(?:MAT|REF|CLM|FILE|CAS|CASE|ACT)[\/-][A-Za-z0-9\/-]{4,15}\b", re.IGNORECASE),
        "label": "Matter/Case Ref",
        "placeholder_type": "MATTER"
    },
    "MONETARY_AMOUNT": {
        "regex": re.compile(r"(?:£|\$|€)\s?\d+(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:million|billion|thousand|k|m))?\b", re.IGNORECASE),
        "label": "Financial Amount",
        "placeholder_type": "AMOUNT"
    },
    "DATE_OF_BIRTH": {
        "regex": re.compile(r"\b(?:DOB|D\.O\.B\.|Date of Birth|born on)\s*[:\-–]?\s*(\d{1,2}[-\/.]\d{1,2}[-\/.]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b", re.IGNORECASE),
        "label": "Date of Birth",
        "placeholder_type": "DATE"
    }
}

# 1. Honorifics and Titles for Person Detection (matches single surnames e.g. "Mrs Patel" as well as full names e.g. "Mr Jonathan Vance")
PERSON_TITLES_REGEX = re.compile(
    r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?|Lord|Lady|Sir|Dame|Justice|Judge|Baroness|Master|Hon\.?)[ \t]+[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,2}\b"
)

# 2. Role-based Person Detection (legal contracts, notarised deeds, witness statements, general documents)
ROLE_BASED_PERSON_REGEX = re.compile(
    r"(?i:\b(?:Claimant|Respondent|Defendant|Plaintiff|Appellant|Solicitor|Counsel|Partner|Director|Witness|Author|Client|Party(?:\s+[A-Z])?|Name|Full\s+Name|Candidate|Employee|Applicant|Prepared\s+by|Attn|Attention|Dear|Notary(?:\s+Public)?|Commissioner(?:\s+for\s+Oaths)?|Sworn\s+by|Signed\s+by|Executed\s+by|In\s+the\s+presence\s+of)\b)[ \t]*[:\-–]?[ \t]*([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,2})\b"
)

# 3. Curated Common First Names in legal/business contexts
COMMON_FIRST_NAMES = {
    "John", "Jonathan", "Jane", "Elizabeth", "Arthur", "David", "Robert", "Sarah", "Michael",
    "James", "William", "Richard", "Thomas", "Charles", "Christopher", "Daniel", "Matthew",
    "Anthony", "Mark", "Steven", "Paul", "Andrew", "George", "Edward", "Alexander", "Peter",
    "Henry", "Adam", "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Susan", "Jessica",
    "Emily", "Victoria", "Emma", "Olivia", "Sophia", "Charlotte", "Alice", "Hannah", "Grace",
    "Claire", "Oliver", "Harry", "Jack", "Jacob", "Noah", "Leo", "Lucas", "Liam", "Benjamin",
    "Samuel", "Joseph", "Sebastian", "Julian", "Marcus", "Nicholas", "Dominic", "Philip",
    "Simon", "Stephen", "Martin", "Patrick", "Rachel", "Rebecca", "Laura", "Helen", "Anna",
    "Sophie", "Eleanor", "Lucy", "Megan", "Zoe", "Chloe", "Fiona", "Gemma", "Catherine",
    "Priya", "Ali", "Khan", "Ahmed", "Kumar", "Singh", "Sharma", "Hussain", "Chen", "Wang", "Zhang", "Liu", "Yang"
}

# Words to exclude from generic name matching
NAME_STOPWORDS = {
    "High Court", "Supreme Court", "Crown Court", "Privileged Legal", "Civil Procedure",
    "Summary Judgment", "Legal Memorandum", "Common Law", "Data Protection", "United Kingdom",
    "European Union", "Barclays Bank", "Parties Background", "Core Obligations", "Asset Transfer",
    "Commercial Dispute", "Draft Terms", "Subject Proposed", "Curriculum Vitae", "Work Experience",
    "Education Background", "Professional Summary", "Key Skills", "Technical Skills", "Employment History",
    "Contact Information", "Personal Profile", "References Available", "Driving Licence", "Passport Number",
    "National Insurance", "Sort Code", "Account Number", "Bank Account", "United States", "London High"
}

# 4. Company & Organisation Detection (Including schools, care homes, clinics, councils, agencies)
# Exclude "National Insurance" from being matched as a company
COMPANY_REGEX = re.compile(
    r"\b(?!(?:UK\s+)?National\s+Insurance)(?:[A-Z][A-Za-z0-9'&.-]+\s+){1,4}(?:LLP|Ltd\.?|Limited|PLC|LLC|Inc\.?|Corp\.?|Corporation|Holdings|Partners|Chambers|Solicitors|Law\s+Firm|Assurance|Insurance|Group|School|Primary\s+School|Secondary\s+School|Academy|College|University|Hospital|Clinic|Care\s+Home|Council|Association|Agency|Trust|Foundation|Centre|Center)\b"
)

# 5. Major Financial Institutions & Banks
BANK_REGEX = re.compile(
    r"\b(?:Barclays(?:\s+Bank)?(?:\s+PLC)?|HSBC(?:\s+Bank)?(?:\s+PLC)?|Lloyds(?:\s+Bank)?(?:\s+PLC)?|NatWest(?:\s+Bank)?|Santander|Standard\s+Chartered)\b",
    re.IGNORECASE
)
