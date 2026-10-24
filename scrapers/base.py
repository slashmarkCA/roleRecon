from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class JobRecord:
    source_job_id: str
    url: str
    title: str
    location: str = ""
    work_mode: str = ""
    employment_type: str = ""
    salary_text: str = ""
    posted_at: Optional[datetime] = None
    description: str = ""
    company: str = ""  # only for sources that list many employers (e.g. Job Bank)