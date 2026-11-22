"""Industry classification of job postings (LLD §5.18). The rules are in `industries.json`."""

# The stored values of jobs.industry, in display order; `other` means "Other / Unclassified".
# industries.json must list exactly these codes (checked when the rules load).
INDUSTRIES = (
    "software_it", "ai_data", "finance_banking", "marketing", "sales_business", "human_resources", "design",
    "operations_supply_chain", "healthcare", "education", "engineering", "legal", "other",
)
