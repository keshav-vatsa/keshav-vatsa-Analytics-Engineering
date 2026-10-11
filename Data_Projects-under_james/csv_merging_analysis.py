# %%
import pandas as pd
import re
from pathlib import Path

# ============================================================
# TASK 5: CONSOLIDATE ESTATE AGENT CONTACT INFORMATION
# ============================================================

# 1. File paths
PURCHASED_FILE = Path(
    "/Users/keshavvatsa/Downloads/WORKSHOP ANALYTICS ENGINEERING /"
    "Estate-Agents-Purchased.csv"
)

VALIDATED_FILE = Path(
    "/Users/keshavvatsa/Downloads/WORKSHOP ANALYTICS ENGINEERING /"
    "UK-Agents-Validated.csv"
)

OUTPUT_FILE = Path(
    "/Users/keshavvatsa/Documents/Git-AnalyticsEngineering-Keshav/"
    "keshav-vatsa-Analytics-Engineering/output_files/Consolidated_Estate_Agents.csv"
)


# 2. Read CSV files
def read_csv_safely(file_path):
    """Read a CSV file and standardise column names."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Try common encodings
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Unable to read file: {file_path}")

    # Clean column names
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )

    # Remove completely empty rows
    df = df.dropna(how="all")

    print(f"\nLoaded: {file_path.name}")
    print(f"Rows: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")

    return df


purchased = read_csv_safely(PURCHASED_FILE)
validated = read_csv_safely(VALIDATED_FILE)


# 3. Identify columns automatically
def find_column(df, possible_names):
    """Find the first matching column from a list of alternatives."""
    for col in possible_names:
        if col in df.columns:
            return col

    # Allow partial matches for variations in column naming
    for col in df.columns:
        for name in possible_names:
            if name in col or col in name:
                return col

    return None


COLUMN_ALIASES = {
    "name": [
        "agent_name", "estate_agent_name", "agency_name",
        "business_name", "company_name", "trading_name",
        "organisation_name", "organization_name", "name",
        "company", "agency", "business"
    ],
    "email": [
        "email_address", "email", "e_mail", "contact_email",
        "business_email", "email_id"
    ],
    "address": [
        "full_address", "business_address", "office_address",
        "registered_address", "address", "location",
        "property_address"
    ],
    "telephone": [
        "telephone_number", "phone_number", "telephone",
        "phone", "contact_number", "mobile_number",
        "mobile", "tel", "contact_phone"
    ],
    "postcode": [
        "postal_code", "postcode", "post_code", "zip_code",
        "zip"
    ],
    "website": [
        "website_url", "website", "web_address", "url"
    ]
}


def standardise_columns(df, source_name):
    """Map available input columns to standard output fields."""
    result = pd.DataFrame(index=df.index)

    for standard_name, aliases in COLUMN_ALIASES.items():
        col = find_column(df, aliases)
        if col is not None:
            result[standard_name] = df[col]
        else:
            result[standard_name] = pd.NA

    # Preserve source and original row number for traceability
    result["source"] = source_name
    result["source_row"] = df.index + 2

    return result


purchased_clean = standardise_columns(purchased, "Purchased")
validated_clean = standardise_columns(validated, "Validated")


# 4. Clean text fields
TEXT_FIELDS = [
    "name", "email", "address", "telephone",
    "postcode", "website"
]


def clean_text(value):
    """Standardise whitespace and missing values."""
    if pd.isna(value):
        return pd.NA

    value = str(value).strip()

    if value.lower() in ["", "nan", "none", "null", "n/a", "na", "-"]:
        return pd.NA

    return re.sub(r"\s+", " ", value)


for df in [purchased_clean, validated_clean]:
    for col in TEXT_FIELDS:
        df[col] = df[col].apply(clean_text)

    # Standardise emails to lowercase
    df["email"] = df["email"].apply(
        lambda x: x.lower() if pd.notna(x) else pd.NA
    )

    # Standardise postcodes for matching
    df["postcode"] = df["postcode"].apply(
        lambda x: re.sub(r"\s+", "", x.upper()) if pd.notna(x) else pd.NA
    )


# 5. Validate email addresses
def is_valid_email(email):
    if pd.isna(email):
        return False
    pattern = r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
    return bool(re.match(pattern, email))


purchased_clean["email_valid"] = purchased_clean["email"].apply(is_valid_email)
validated_clean["email_valid"] = validated_clean["email"].apply(is_valid_email)


# 6. Combine both datasets
combined = pd.concat([purchased_clean, validated_clean], ignore_index=True)

# Prefer records containing an email, then a name and address
combined["completeness"] = (
    combined["email"].notna().astype(int) * 4
    + combined["name"].notna().astype(int) * 2
    + combined["address"].notna().astype(int) * 2
    + combined["telephone"].notna().astype(int)
    + combined["postcode"].notna().astype(int)
    + combined["website"].notna().astype(int)
)


# 7. Match records using email, name and postcode
def make_match_key(row):
    """
    Use email as the strongest matching key.
    Otherwise use name + postcode, then name + address.
    """
    if pd.notna(row["email"]):
        return "EMAIL|" + row["email"]

    if pd.notna(row["name"]) and pd.notna(row["postcode"]):
        return "NAME_POSTCODE|" + row["name"].lower() + "|" + row["postcode"]

    if pd.notna(row["name"]) and pd.notna(row["address"]):
        return "NAME_ADDRESS|" + row["name"].lower() + "|" + row["address"].lower()

    return pd.NA


combined["match_key"] = combined.apply(make_match_key, axis=1)

# Keep records without a reliable key rather than merging them
# incorrectly with unrelated businesses.
with_key = combined[combined["match_key"].notna()].copy()
without_key = combined[combined["match_key"].isna()].copy()

with_key = with_key.sort_values(
    by=["completeness", "email_valid"],
    ascending=[False, False]
)

deduplicated = with_key.drop_duplicates(subset="match_key", keep="first")

combined = pd.concat([deduplicated, without_key], ignore_index=True)


# 8. Consolidate missing information from matching records
original = pd.concat([purchased_clean, validated_clean], ignore_index=True)
original["match_key"] = original.apply(make_match_key, axis=1)
original = original[original["match_key"].notna()]

original["completeness"] = (
    original["email"].notna().astype(int) * 4
    + original["name"].notna().astype(int) * 2
    + original["address"].notna().astype(int) * 2
    + original["telephone"].notna().astype(int)
    + original["postcode"].notna().astype(int)
    + original["website"].notna().astype(int)
)

original = original.sort_values(
    by=["completeness", "email_valid"],
    ascending=[False, False]
)


def merge_group(group):
    result = group.iloc[0].copy()

    for col in TEXT_FIELDS:
        values = group[col].dropna()
        if pd.isna(result[col]) and not values.empty:
            result[col] = values.iloc[0]

    result["source"] = " + ".join(sorted(group["source"].dropna().unique()))
    return result


merged_records = (
    original.groupby("match_key", sort=False)
    .apply(merge_group, include_groups=False)
    .reset_index(drop=True)
)

# Retain records without matching keys separately
unmatched_records = combined[combined["match_key"].isna()].copy()

final_df = pd.concat([merged_records, unmatched_records], ignore_index=True)


# 9. Remove duplicate email addresses
final_df["duplicate_email"] = (
    final_df["email"].notna()
    & final_df["email"].duplicated(keep=False)
)

# Sort email duplicates together for easier inspection
final_df = final_df.sort_values(by=["email", "name"], na_position="last")


# 10. Create final output
output_columns = [
    "name", "email", "address", "postcode", "telephone",
    "website", "source", "email_valid", "duplicate_email"
]

final_df = final_df[output_columns]

# Rename columns for business-friendly output
final_df = final_df.rename(columns={
    "name": "Agent Name",
    "email": "Email Address",
    "address": "Address",
    "postcode": "Postcode",
    "telephone": "Telephone Number",
    "website": "Website",
    "source": "Source Dataset",
    "email_valid": "Email Format Valid",
    "duplicate_email": "Duplicate Email - Review"
})

# Ensure the output directory exists before writing
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

final_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")


# 11. Summary report
print("\n" + "=" * 55)
print("TASK 5: CONSOLIDATION COMPLETE")
print("=" * 55)

print(f"Purchased records: {len(purchased_clean)}")
print(f"Validated records: {len(validated_clean)}")
print(f"Final consolidated records: {len(final_df)}")
print("Records with email:", final_df["Email Address"].notna().sum())
print("Records with valid email format:", final_df["Email Format Valid"].sum())
print("Records with telephone:", final_df["Telephone Number"].notna().sum())
print("Records with address:", final_df["Address"].notna().sum())
print("Records flagged for duplicate email review:", final_df["Duplicate Email - Review"].sum())

print(f"\nOutput saved to:\n{OUTPUT_FILE}")
print("=" * 55)


#checking the final output file

import pandas as pd

# Load the final file
df = pd.read_csv("/Users/keshavvatsa/Documents/Git-AnalyticsEngineering-Keshav/keshav-vatsa-Analytics-Engineering/output_files/Consolidated_Estate_Agents.csv")

# 1. See where the data came from
print("--- SOURCE BREAKDOWN ---")
print(df["Source Dataset"].value_counts())

# 2. Check for missing data in key columns
print("\n--- MISSING DATA ---")
print(df.isnull().sum())

# 3. View a sample of successfully merged records
merged = df[df["Source Dataset"] == "Purchased + Validated"]
if not merged.empty:
    print("\n--- SAMPLE MERGED RECORDS ---")
    display(merged.head(3))



    print("Purchased Columns:", purchased_clean.columns.tolist())
print("Validated Columns:", validated_clean.columns.tolist())