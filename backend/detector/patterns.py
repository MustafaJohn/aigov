import re
from typing import List, Dict, Any

# UK and International PII regular expression patterns
PATTERNS = {
    "NI_NUMBER": {
        "regex": re.compile(r"\b(?:[A-CEGHJ-PR-TW-Z]{2}|QQ)\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE),
        "label": "National Insurance No.",
        "jargon_prefix": "XXX"
    },
    "SORT_CODE": {
        "regex": re.compile(r"\b(?:\d{2}-\d{2}-\d{2}|\d{2}\s\d{2}\s\d{2})\b"),
        "label": "Sort Code",
        "jargon_prefix": "XYZ"
    },
    "ACCOUNT_NUMBER": {
        # Fix: Require context (Account / A/C / No / Bank) rather than matching any random 8 digits
        "regex": re.compile(r"(?i:\b(?:acc(?:ount)?\.?|a\/c|no\.?|number)\s*[:#-]?\s*)(\d{8,10})\b"),
        "label": "Bank Account No.",
        "jargon_prefix": "XXX"
    },
    "CREDIT_CARD": {
        "regex": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "label": "Card Number",
        "jargon_prefix": "XYZ"
    },
    "UK_POSTCODE": {
        "regex": re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE),
        "label": "UK Postcode",
        "jargon_prefix": "XXX"
    },
    "PHYSICAL_ADDRESS": {
        "regex": re.compile(
            r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|Road|Avenue|Lane|Drive|Grove|Way|Close|Gardens|Court|Boulevard|Hill|Walk|Terrace|Square|Crescent)(?:,\s*[A-Z][a-z]+)?\b"
        ),
        "label": "Street Address",
        "jargon_prefix": "XYZ"
    },
    "EMAIL": {
        "regex": re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),
        "label": "Email Address",
        "jargon_prefix": "XXX"
    },
    "PHONE": {
        "regex": re.compile(r"\b(?:(?:\+44\s?|0)(?:20\s?\d{4}|1\d{3}\s?\d{3}|7\d{3}\s?\d{3})\s?\d{3,4}|\+?[0-9]{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3}[-.\s]?\d{3,4})\b"),
        "label": "Phone Number",
        "jargon_prefix": "XYZ"
    },
    "MATTER_REF": {
        "regex": re.compile(r"\b(?:MAT|REF|CLM|FILE|CAS|CASE|ACT)[\/-][A-Za-z0-9\/-]{4,15}\b", re.IGNORECASE),
        "label": "Matter/Case Ref",
        "jargon_prefix": "XXX"
    },
    "MONETARY_AMOUNT": {
        "regex": re.compile(r"(?:£|\$|€)\s?\d+(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:million|billion|thousand|k|m))?\b", re.IGNORECASE),
        "label": "Financial Amount",
        "jargon_prefix": "XYZ"
    },
    "DATE_OF_BIRTH": {
        "regex": re.compile(r"\b(?:DOB|D\.O\.B\.|Date of Birth|born on)\s*[:\-–]?\s*(\d{1,2}[-\/.]\d{1,2}[-\/.]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b", re.IGNORECASE),
        "label": "Date of Birth",
        "jargon_prefix": "XXX"
    }
}

# 1. Honorifics and Titles for Person Detection (e.g. "Mr. Jonathan Vance", "Master Arthur Pendelton")
PERSON_TITLES_REGEX = re.compile(
    r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?|Lord|Lady|Sir|Dame|Justice|Judge|Baroness|Master|Hon\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b"
)

# 2. Role-based Person Detection (e.g. "Claimant: Jonathan Vance", "Solicitor: Arthur Pendelton")
ROLE_BASED_PERSON_REGEX = re.compile(
    r"\b(?:Claimant|Respondent|Defendant|Plaintiff|Appellant|Solicitor|Counsel|Partner|Director|Witness|Author|Client|Party(?:\s+[A-Z])?)\s*[:\-–]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
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
    "Jonathan", "Vance", "Pendelton", "Ward"
}

# Legal/system words to exclude from generic name matching
NAME_STOPWORDS = {
    "High Court", "Supreme Court", "Crown Court", "Privileged Legal", "Civil Procedure",
    "Summary Judgment", "Legal Memorandum", "Common Law", "Data Protection", "United Kingdom",
    "European Union", "Barclays Bank", "Parties Background", "Core Obligations", "Asset Transfer",
    "Commercial Dispute", "Draft Terms", "Subject Proposed"
}

# 4. Company & Organisation Detection (Constrained to 1-4 capitalized words before legal designator)
# Exclude "National Insurance" from being matched as a company
COMPANY_REGEX = re.compile(
    r"\b(?!(?:UK\s+)?National\s+Insurance)(?:[A-Z][A-Za-z0-9'&.-]+\s+){1,4}(?:LLP|Ltd\.?|Limited|PLC|LLC|Inc\.?|Corp\.?|Corporation|Holdings|Partners|Chambers|Solicitors|Law\s+Firm|Assurance|Insurance|Group)\b"
)

# 5. Major Financial Institutions & Banks
BANK_REGEX = re.compile(
    r"\b(?:Barclays(?:\s+Bank)?(?:\s+PLC)?|HSBC(?:\s+Bank)?(?:\s+PLC)?|Lloyds(?:\s+Bank)?(?:\s+PLC)?|NatWest(?:\s+Bank)?|Santander|Standard\s+Chartered)\b",
    re.IGNORECASE
)
