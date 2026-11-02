# Fixes for unmatched annotations.
# "remove" = annotation doesn't exist in text, drop it
# "replace" = annotation text was wrong, use corrected text
FIXES = {
    "exbc17": [
        ("remove", "Underground Water Tie-in's", "SKILL"),
    ],
    "exbc18": [
        ("replace", 'Gregory S. Coatsworth', "NAME", 'Gregory\xa0S.\xa0Coatsworth'),
        ("replace", '127 Bostwick Drive', "LOCATION", '127\xa0Bostwick\xa0Drive'),
        ("remove", 'San Diego, CA 92101', "LOCATION"),
        ("replace", '(619) 532‐0890', "PHONE", '(619)\xa0532‐0890'),
        ("replace", 'Mark L. Johnson', "NAME", 'Mark\xa0L.\xa0Johnson'),
        ("remove", 'Director of International Services', "TITLE"),
        ("replace", 'GNBA, Inc.', "COMPANY", 'GNBA,\xa0Inc.'),
        ("replace", 'International Relations', "FIELD", 'International\xa0Relations'),
        ("remove", '19+ years', "DATE"),
        ("replace", 'cross‐cultural work experience', "SKILL", 'cross‐cultural\xa0work\xa0experience'),
        ("remove", '18 countries', "LOCATION"),
        ("replace", '40 countries', "LOCATION", '40\xa0countries'),
        ("replace", '12 years', "DATE", '12\xa0years'),
        ("remove", 'strategic planning', "SKILL"),
        ("remove", 'business management', "SKILL"),
        ("remove", 'organizational development', "SKILL"),
        ("remove", 'team building', "SKILL"),
        ("remove", 'project execution', "SKILL"),
        ("remove", 'cross-cultural work experience', "SKILL"),
    ],
    "exex13": [
        ("replace", 'Executive Decision Maker & Fiscal Champion', "SKILL", 'Executive\xa0Decision\xa0Maker\xa0&\xa0Fiscal\xa0Champion'),
        ("replace", 'Corporate Planning & Strategic Development', "SKILL", 'Corporate\xa0Planning\xa0&\xa0Strategic\xa0Development'),
        ("remove", 'Global Multi-Site Operational Leadership', "SKILL"),
        ("replace", 'P&L Management & Budgetary Direction', "SKILL", 'P&L\xa0Management\xa0&\xa0Budgetary\xa0Direction'),
        ("replace", 'Green Field Facility Start Ups', "SKILL", 'Green\xa0Field\xa0Facility\xa0Start\xa0Ups'),
        ("replace", 'Lean & Six Sigma Practitioner', "SKILL", 'Lean\xa0&\xa0Six\xa0Sigma\xa0Practitioner'),
        ("replace", 'MANUFACTURING SPECIALISTS GROUP', "COMPANY", 'MANUFACTURING\xa0SPECIALISTS\xa0GROUP'),
        ("replace", 'Almont, MI', "LOCATION", 'Almont,\xa0MI'),
        ("replace", 'Senior Director/Consultant', "TITLE", 'Senior\xa0Director/Consultant'),
        ("replace", 'LEO ASTOR AUTOMOTIVE', "COMPANY", 'LEO\xa0ASTOR\xa0AUTOMOTIVE'),
        ("replace", 'Detroit, MI', "LOCATION", 'Detroit,\xa0MI'),
    ],
    "exex23": [
        ("replace", 'Vice President  Head of Sales', "TITLE", 'Vice President \uf0a7 Head of Sales'),
    ],
    "exfi18": [
        ("replace", 'Economic Foundations of Policy Analysis', "SKILL", 'Economic Foundations of\nPolicy Analysis'),
        ("replace", 'Public Financial Administration', "SKILL", 'Public Financial\nAdministration'),
        ("replace", 'Public Administration and Democracy', "SKILL", 'Public Administration and\nDemocracy'),
        ("replace", 'Public Personnel Administration', "SKILL", 'Public Personnel\nAdministration'),
        ("replace", 'MS Office Suite - Word, Outlook, PowerPoint', "SKILL", 'MS Office Suite - Word,\nOutlook, PowerPoint'),
    ],
    "exfi19": [
        ("remove", 'FINRA Series 63', "CERT"),
    ],
    "exfi21": [
        ("remove", 'Actuary/Pension Consultant', "TITLE"),
    ],
    "exfi22": [
        ("remove", 'Credit & Collections Manager', "TITLE"),
    ],
    "exfi7": [
        ("replace", 'CERTIFIED RESIDENTIAL APPRAISER', "CERT", 'CERTIFIED\nRESIDENTIAL\nAPPRAISER'),
        ("replace", 'LICENSED APPRAISER', "CERT", 'LICENSED\nAPPRAISER'),
        ("replace", 'Professional Home Inspection for Licensing', "SKILL", 'Professional Home\nInspection for\nLicensing'),
        ("replace", 'Gross Income Multipliers', "SKILL", 'Gross Income\nMultipliers'),
        ("replace", 'Streamlined Reporting Options', "SKILL", 'Streamlined Reporting\nOptions'),
    ],
    "exgov1": [
        ("replace", 'Aviation Training', "SKILL", 'Aviation\nTraining'),
    ],
    "exleg8": [
        ("remove", "Oakland County District Attorney's Office", "COMPANY"),
    ],
    "exman10": [
        ("replace", 'Strategic Operations Management', "SKILL", 'Strategic Operations\nManagement'),
        ("replace", 'Cost Reduction & Budgeting', "SKILL", 'Cost Reduction &\nBudgeting'),
    ],
}
