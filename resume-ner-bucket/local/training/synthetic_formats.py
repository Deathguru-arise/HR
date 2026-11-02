import random

SECTION_HEADERS = {
    "exp": ["Experience", "Work Experience", "Professional Experience", "Employment History", "EXPERIENCE", "WORK EXPERIENCE"],
    "edu": ["Education", "EDUCATION", "Academic Background"],
    "skills": ["Skills", "Technical Skills", "SKILLS", "TECHNICAL SKILLS", "Core Competencies"],
    "certs": ["Certifications", "CERTIFICATIONS", "Licenses & Certifications"],
}


def build_resume_format_a(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    lines = [name]
    parts = [email]
    if phone:
        parts.append(phone)
    if location:
        parts.append(location)
    lines.append(" | ".join(parts))
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", random.choice(SECTION_HEADERS["exp"])])
        for item in exp:
            lines.append("")
            lines.append(item["title"])
            lines.append(item["company"])
            if item.get("location") and item.get("dates"):
                lines.append(f"{item['location']} | {item['dates']}")
            elif item.get("dates"):
                lines.append(item["dates"])
            elif item.get("location"):
                lines.append(item["location"])
            if item.get("desc"):
                lines.append(item["desc"])
    if edu:
        lines.extend(["", random.choice(SECTION_HEADERS["edu"])])
        for item in edu:
            lines.append(item["line"])
    if all_skills:
        lines.extend(["", random.choice(SECTION_HEADERS["skills"])])
        lines.append(", ".join(all_skills))
    if cert_names:
        lines.extend(["", random.choice(SECTION_HEADERS["certs"])])
        for cert_name in cert_names:
            lines.append(cert_name)
    return "\n".join(lines)


def build_resume_format_b(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    lines = [name, f"{email} | {phone}" + (f" | {location}" if location else "")]
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", random.choice(SECTION_HEADERS["exp"])])
        for item in exp:
            lines.append(f"{item['title']}, {item['company']}")
            date_loc = item.get("location", "") or ""
            if item.get("dates"):
                date_loc += f" | {item['dates']}" if date_loc else item["dates"]
            if date_loc:
                lines.append(date_loc)
            if item.get("desc"):
                lines.append(item["desc"])
    if edu:
        lines.extend(["", random.choice(SECTION_HEADERS["edu"])])
        for item in edu:
            lines.append(item["line"])
    if all_skills:
        lines.extend(["", random.choice(SECTION_HEADERS["skills"])])
        lines.append(", ".join(all_skills))
    if cert_names:
        lines.extend(["", random.choice(SECTION_HEADERS["certs"])])
        for cert_name in cert_names:
            lines.append(cert_name)
    return "\n".join(lines)


def build_resume_format_c(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    lines = [name]
    header = email
    if phone:
        header += f" | {phone}"
    if location:
        header += f" | {location}"
    lines.append(header)
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", random.choice(SECTION_HEADERS["exp"])])
        for item in exp:
            line = f"{item['company']} - {item['title']}"
            if item.get("dates"):
                line += f" | {item['dates']}"
            lines.append(line)
            if item.get("desc"):
                lines.append(f"  {item['desc']}")
    if edu:
        lines.extend(["", random.choice(SECTION_HEADERS["edu"])])
        for item in edu:
            lines.append(item["line"])
    if all_skills:
        lines.extend(["", random.choice(SECTION_HEADERS["skills"])])
        lines.append(", ".join(all_skills))
    return "\n".join(lines)


def build_resume_format_d(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    lines = [name]
    parts = []
    if email:
        parts.append(email)
    if phone:
        parts.append(phone)
    if location:
        parts.append(location)
    lines.append(" | ".join(parts))
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", random.choice(SECTION_HEADERS["exp"])])
        for item in exp:
            lines.append(item["company"] if item["company"] else "")
            lines.append(item["title"])
            date_loc = item.get("location", "") or ""
            if item.get("dates"):
                date_loc += f" | {item['dates']}" if date_loc else item["dates"]
            if date_loc:
                lines.append(date_loc)
            if item.get("desc"):
                lines.append(item["desc"])
            lines.append("")
    if edu:
        lines.extend(["", random.choice(SECTION_HEADERS["edu"])])
        for item in edu:
            lines.append(item["line"])
    if all_skills:
        lines.extend(["", random.choice(SECTION_HEADERS["skills"])])
        lines.append(random.choice([", ", " | ", " - ", "  "]).join(all_skills))
    return "\n".join(lines)


def build_resume_format_e(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    lines = [name, f"{email} | {phone}" + (f" | {location}" if location else "")]
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", random.choice(SECTION_HEADERS["exp"])])
        for item in exp:
            line = item["title"]
            if item["company"]:
                line += f" at {item['company']}"
            lines.append(line)
            date_loc = item.get("location", "") or ""
            if item.get("dates"):
                date_loc += f" | {item['dates']}" if date_loc else item["dates"]
            if date_loc:
                lines.append(date_loc)
            if item.get("desc"):
                lines.append(item["desc"])
    if edu:
        lines.extend(["", random.choice(SECTION_HEADERS["edu"])])
        for item in edu:
            lines.append(item["line"])
    if all_skills:
        lines.extend(["", random.choice(SECTION_HEADERS["skills"])])
        lines.append(", ".join(all_skills))
    return "\n".join(lines)


def build_resume_format_f(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    """Dense OCR-style: + separators, bullet points, uppercase headers."""
    lines = [name, ""]
    parts = [email]
    if phone:
        parts.append(phone)
    if location:
        parts.append(location)
    lines.append(" + ".join(parts))
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", "EXPERIENCE", ""])
        for item in exp:
            date_part = ""
            if item.get("dates"):
                date_part = item["dates"]
            lines.append(f"{item['title']} {date_part}".strip())
            company_line = item["company"]
            if item.get("location"):
                company_line += f" - {item['location']}"
            lines.append(company_line)
            lines.append("")
            if item.get("desc"):
                lines.append(f"- {item['desc']}")
                lines.append("")
    if edu:
        lines.extend(["EDUCATION", ""])
        for item in edu:
            lines.append(item["line"])
        lines.append("")
    if all_skills:
        lines.extend(["SKILLS", ""])
        sep = random.choice([" - ", " + ", " | "])
        lines.append(sep.join(all_skills))
    if cert_names:
        lines.extend(["", "CERTIFICATIONS", ""])
        for cert_name in cert_names:
            lines.append(cert_name)
    return "\n".join(lines)


def build_resume_format_g(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    """Dense compact: title + company on same line, dates on same line, multiple bullets per job."""
    lines = [name]
    parts = []
    if email:
        parts.append(email)
    if phone:
        parts.append(phone)
    if location:
        parts.append(location)
    lines.append(" + ".join(parts))
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", random.choice(SECTION_HEADERS["exp"]), ""])
        for item in exp:
            title_line = item["title"]
            if item.get("dates"):
                title_line += f" {item['dates']}"
            lines.append(title_line)
            company_line = item["company"]
            if item.get("location"):
                company_line += f" - {item['location']}"
            lines.append(company_line)
            if item.get("desc"):
                lines.append(f"- {item['desc']}")
            lines.append("")
    if edu:
        lines.extend([random.choice(SECTION_HEADERS["edu"]), ""])
        for item in edu:
            lines.append(item["line"])
        lines.append("")
    if all_skills:
        cat = random.choice(["Technical Skills", "TECHNICAL SKILLS", "Core Competencies"])
        lines.append(cat + ": " + random.choice([", ", " - "]).join(all_skills))
    if cert_names:
        lines.extend(["", random.choice(SECTION_HEADERS["certs"])])
        for cert_name in cert_names:
            lines.append(cert_name)
    return "\n".join(lines)


def build_resume_format_h(name, email, phone, location, summary, exp, edu, all_skills, cert_names):
    """Verbose: full descriptions with multiple bullet points, PROJECTS-like section."""
    lines = [name, ""]
    header = email
    if phone:
        header += f" | {phone}"
    if location:
        header += f" | {location}"
    lines.append(header)
    if summary:
        lines.extend(["", summary])
    if exp:
        lines.extend(["", "EXPERIENCE", ""])
        for item in exp:
            lines.append(f"{item['title']}")
            company_line = item["company"]
            if item.get("location"):
                company_line += f", {item['location']}"
            if item.get("dates"):
                company_line += f" | {item['dates']}"
            lines.append(company_line)
            if item.get("desc"):
                lines.append(f"\n- {item['desc']}")
                lines.append(f"- Collaborated with cross-functional teams to deliver key project milestones")
                lines.append(f"- Improved system performance and reliability through optimization initiatives")
            lines.append("")
    if edu:
        lines.extend(["EDUCATION", ""])
        for item in edu:
            lines.append(item["line"])
        lines.append("")
    if all_skills:
        lines.extend(["SKILLS", ""])
        mid = len(all_skills) // 2
        if mid > 0:
            lines.append("Technical: " + " - ".join(all_skills[:mid]))
            lines.append("Tools: " + " - ".join(all_skills[mid:]))
        else:
            lines.append(", ".join(all_skills))
    if cert_names:
        lines.extend(["", "CERTIFICATIONS"])
        for cert_name in cert_names:
            lines.append(cert_name)
    return "\n".join(lines)


RESUME_FORMATS = [
    build_resume_format_a,
    build_resume_format_b,
    build_resume_format_c,
    build_resume_format_d,
    build_resume_format_e,
    build_resume_format_f,
    build_resume_format_g,
    build_resume_format_h,
]
