import html
import re
from datetime import datetime


REPORT_FIELD_NAMES = (
    "Company",
    "Location",
    "Publisher",
    "Posted",
    "Employment type",
    "Salary",
    "Apply/source link",
)


def parse_report_jobs(markdown):
    sections = re.split(r"(?m)^### \d+\. ", markdown)
    parsed = []
    for section in sections[1:]:
        title, _, body = section.partition("\n")
        title = re.sub(r"\\([\\`*_{}\[\]()#+.!|>~-])", r"\1", title.strip())
        fields = {}
        for field in REPORT_FIELD_NAMES:
            match = re.search(rf"(?m)^- {re.escape(field)}: (.*)$", body)
            fields[field] = match.group(1).strip() if match else ""

        description_match = re.search(r"<pre>\s*(.*?)\s*</pre>", body, re.DOTALL)
        description = html.unescape(description_match.group(1)).strip() if description_match else ""
        if not title or not fields["Apply/source link"]:
            raise ValueError("A JSearch pilot entry is missing its title or source URL")
        parsed.append(
            {
                "title": title,
                "company": fields["Company"],
                "location": fields["Location"],
                "publisher": fields["Publisher"],
                "posted": fields["Posted"],
                "employment": fields["Employment type"],
                "salary": fields["Salary"],
                "url": fields["Apply/source link"],
                "description": description,
            }
        )
    if not parsed:
        raise ValueError("The report contains no JSearch pilot jobs")
    return parsed


def parse_report_queries(markdown):
    queries = []
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("| Search |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        match = re.match(r"^\|\s*(.*?)\s*\|\s*\d+\s*\|", line)
        if match and match.group(1) not in {"Search", "---"}:
            query = match.group(1).replace("\\|", "|").strip()
            if query not in queries:
                queries.append(query)
    return queries


def parse_posted(value):
    if not value or value == "Not supplied":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
