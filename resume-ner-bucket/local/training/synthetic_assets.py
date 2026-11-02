import json
import random
from pathlib import Path

FAKE_EMAILS = ["gmail.com", "outlook.com", "yahoo.com", "protonmail.com", "hotmail.com", "icloud.com"]
COMMON_CERTS = [
    "AWS Solutions Architect", "PMP", "Certified Scrum Master",
    "Google Analytics Certified", "CPA", "CISSP", "CompTIA Security+",
    "Certified Kubernetes Administrator", "ITIL Foundation",
    "Six Sigma Green Belt", "Microsoft Azure Administrator",
]

_COMPANIES = None
_TITLES = None


def load_companies(data_dir: Path) -> list[str]:
    global _COMPANIES
    if _COMPANIES is None:
        try:
            with open(data_dir / "companies.json") as f:
                data = json.load(f)
            _COMPANIES = [company for companies in data.values() for company in companies if company and len(company) > 1]
        except FileNotFoundError:
            _COMPANIES = []
    return _COMPANIES


def load_titles(data_dir: Path) -> list[str]:
    global _TITLES
    if _TITLES is None:
        try:
            with open(data_dir / "titles.json") as f:
                data = json.load(f)
            _TITLES = [title for titles in data.values() for title in titles if title]
        except FileNotFoundError:
            _TITLES = []
    return _TITLES


def generate_email(name: str) -> str:
    parts = [part for part in name.lower().split() if part.isalpha()]
    if not parts:
        return f"user{random.randint(100, 999)}@{random.choice(FAKE_EMAILS)}"
    if len(parts) >= 2:
        variants = [f"{parts[0]}.{parts[1]}", f"{parts[0]}{parts[1][0]}", f"{parts[0]}_{parts[1]}", f"{parts[0][0]}{parts[1]}"]
        user = random.choice(variants)
    else:
        user = parts[0] + str(random.randint(1, 99))
    return f"{user}@{random.choice(FAKE_EMAILS)}"


def generate_phone() -> str:
    formats = ["({}) {}-{}", "+1 ({}) {}-{}", "+91 {} {}", "+44 {} {}", "{}-{}-{}"]
    fmt = random.choice(formats)
    return fmt.format(random.randint(100, 999), random.randint(100, 999), random.randint(1000, 9999))
