import re

import fitz


def extract_safe_harbor():
    doc = fitz.open("docs/45 CFR 164.514 (up to date as of 12-29-2025).pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text()

    # Normalize whitespace
    full_text = re.sub(r"\s+", " ", full_text)

    # Locate Safe Harbor section (b)
    # Looking for "(b) Standard: De-identification"
    start_pattern = r"\(b\) Standard: De-identification of protected health information"
    end_pattern = r"\(c\) Standard: Re-identification"

    match = re.search(f"({start_pattern}.*?){end_pattern}", full_text, re.IGNORECASE)

    if match:
        content = match.group(1)
        print("FOUND SAFE HARBOR TEXT:")
        print("-----------------------")
        # Format for readability
        formatted = content.replace(
            " (2) Implementation specifications", "\n\n(2) Implementation specifications"
        )
        formatted = formatted.replace(" (i)", "\n(i)").replace(" (ii)", "\n(ii)")
        # Add basic formatting for list items
        for i in range(1, 19):
            roman = [
                "i",
                "ii",
                "iii",
                "iv",
                "v",
                "vi",
                "vii",
                "viii",
                "ix",
                "x",
                "xi",
                "xii",
                "xiii",
                "xiv",
                "xv",
                "xvi",
                "xvii",
                "xviii",
            ][i - 1]
            formatted = formatted.replace(f" ({roman})", f"\n({roman})")

        print(formatted[:2000] + "..." if len(formatted) > 2000 else formatted)
        return formatted
    else:
        print("Could not locate Safe Harbor section")


if __name__ == "__main__":
    extract_safe_harbor()
