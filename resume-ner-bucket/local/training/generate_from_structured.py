"""
Generate BIO-tagged NER training data from datasetmaster/resumes structured data.
Creates diverse resume text formats + aligned BIO tags.
"""

import json
import random
from pathlib import Path

from datasets import load_dataset

try:
    from training.dataset_utils import dedupe_examples, stable_split_examples, write_dataset
    from training.labels import ID2LABEL, LABEL2ID
    from training.synthetic_assets import COMMON_CERTS, generate_email, generate_phone, load_companies, load_titles
    from training.synthetic_formats import RESUME_FORMATS
    from training.tagging import tag_exact_words
except ModuleNotFoundError:
    from dataset_utils import dedupe_examples, stable_split_examples, write_dataset
    from labels import ID2LABEL, LABEL2ID
    from synthetic_assets import COMMON_CERTS, generate_email, generate_phone, load_companies, load_titles
    from synthetic_formats import RESUME_FORMATS
    from tagging import tag_exact_words

DATA_DIR = Path(__file__).parent / "data"


def tag_skill_individually(tokens, labels, skill_name):
    skill_clean = skill_name.strip().rstrip(",.;:|")
    skill_words = skill_clean.split()
    if not skill_words:
        return
    for i in range(len(tokens)):
        if len(skill_words) == 1:
            clean_tok = tokens[i].rstrip(",.;:|").lstrip("-")
            if clean_tok.lower() == skill_clean.lower():
                if labels[i] == "O":
                    labels[i] = "B-SKILL"
                return
        else:
            match = True
            for j, sw in enumerate(skill_words):
                if i + j >= len(tokens):
                    match = False
                    break
                if tokens[i + j].rstrip(",.;:|").lower() != sw.rstrip(",.;:|").lower():
                    match = False
                    break
            if match:
                for j in range(len(skill_words)):
                    if labels[i + j] == "O":
                        labels[i + j] = "B-SKILL" if j == 0 else "I-SKILL"
                return


def extract_fields(sample):
    p = sample.get("personal_info") or {}
    if not isinstance(p, dict): return None
    name = p.get("name", "Unknown")
    if not name or name == "Unknown": return None

    loc = p.get("location") or {}
    city = loc.get("city", "") if isinstance(loc, dict) else ""
    country = loc.get("country", "") if isinstance(loc, dict) else ""
    location = f"{city}, {country}".strip(", ") if city or country else ""

    email = generate_email(name)
    phone = generate_phone()
    summary = p.get("summary", "")
    if summary == "Unknown": summary = ""

    exp_list = []
    for e in (sample.get("experience") or []):
        if not isinstance(e, dict): continue
        title = e.get("title", "")
        company = e.get("company", "")
        if not title or title == "Unknown": continue
        if company in ("Unknown", "Fresher", ""): company = ""
        dates_d = e.get("dates", {}) or {}
        start = dates_d.get("start", "") if isinstance(dates_d, dict) else ""
        end = dates_d.get("end", "") if isinstance(dates_d, dict) else ""
        if start == "Unknown": start = ""
        if end == "Unknown": end = ""
        dates = ""
        if start:
            dates = start
            if end: dates += f" - {end}"
        resps = e.get("responsibilities", [])
        desc = ""
        if isinstance(resps, list) and resps and resps[0] != "Unknown":
            desc = resps[0]

        exp_loc = ""
        company_info = e.get("company_info") or {}
        if isinstance(company_info, dict):
            exp_loc = company_info.get("location", "") or ""
            if exp_loc == "Unknown": exp_loc = ""

        # 90% chance to swap with real company names, 50% for titles
        companies = load_companies(DATA_DIR)
        titles = load_titles(DATA_DIR)
        if companies and random.random() < 0.9:
            company = random.choice(companies)
        if titles and random.random() < 0.5:
            title = random.choice(titles)

        exp_list.append({"title": title, "company": company, "location": exp_loc, "dates": dates, "desc": desc, "start": start, "end": end})

    edu_list = []
    for ed in (sample.get("education") or []):
        if not isinstance(ed, dict): continue
        degree = ed.get("degree", {}) or {}
        level = degree.get("level", "") if isinstance(degree, dict) else ""
        field = degree.get("field", "") if isinstance(degree, dict) else ""
        inst = ed.get("institution", {}) or {}
        inst_name = inst.get("name", "") if isinstance(inst, dict) else ""
        if level == "Unknown": level = ""
        if field == "Unknown": field = ""
        if inst_name == "Unknown": inst_name = ""
        if not level and not inst_name: continue
        line_parts = []
        if level: line_parts.append(level)
        if field: line_parts.append(f"in {field}")
        if inst_name: line_parts.append(f"from {inst_name}" if line_parts else inst_name)
        edu_list.append({"level": level, "field": field, "institution": inst_name, "line": " ".join(line_parts)})

    skills_data = sample.get("skills") or {}
    tech = skills_data.get("technical", {}) if isinstance(skills_data, dict) else {}
    all_skills = []
    if isinstance(tech, dict):
        for cat in tech.values():
            if isinstance(cat, list):
                for sk in cat:
                    if isinstance(sk, dict) and sk.get("name") and sk["name"] != "Unknown":
                        all_skills.append(sk["name"])

    certs = sample.get("certifications") or []
    cert_names = []
    if isinstance(certs, list):
        for c in certs:
            if isinstance(c, dict) and c.get("name") and c["name"] != "Unknown":
                cert_names.append(c["name"])

    # Add synthetic certs for variety (some resumes should have them)
    if not cert_names and random.random() < 0.3:
        cert_names = random.sample(COMMON_CERTS, random.randint(1, 2))

    return {
        "name": name, "email": email, "phone": phone, "location": location,
        "summary": summary, "exp": exp_list, "edu": edu_list,
        "skills": all_skills, "certs": cert_names,
    }


def build_resume_and_tags(sample):
    fields = extract_fields(sample)
    if not fields or len(fields["skills"]) < 2:
        return None

    fmt = random.choice(RESUME_FORMATS)
    text = fmt(
        fields["name"], fields["email"], fields["phone"], fields["location"],
        fields["summary"], fields["exp"], fields["edu"], fields["skills"], fields["certs"],
    )

    tokens = text.split()
    if len(tokens) < 15:
        return None
    labels = ["O"] * len(tokens)

    tag_exact_words(tokens, labels, fields["name"], "NAME")
    tag_exact_words(tokens, labels, fields["email"], "EMAIL")
    tag_exact_words(tokens, labels, fields["phone"], "PHONE")
    if fields["location"]:
        tag_exact_words(tokens, labels, fields["location"], "LOCATION")

    for e in fields["exp"]:
        if e["title"]:
            tag_exact_words(tokens, labels, e["title"], "TITLE")
        if e["company"]:
            tag_exact_words(tokens, labels, e["company"], "COMPANY")
        if e["start"]:
            tag_exact_words(tokens, labels, e["start"], "DATE")
        if e["end"] and e["end"] != "Present":
            tag_exact_words(tokens, labels, e["end"], "DATE")
        if e["end"] == "Present":
            tag_exact_words(tokens, labels, "Present", "DATE")

    for ed in fields["edu"]:
        if ed["level"]:
            tag_exact_words(tokens, labels, ed["level"], "DEGREE")
        if ed["field"]:
            tag_exact_words(tokens, labels, ed["field"], "FIELD")
        if ed["institution"]:
            tag_exact_words(tokens, labels, ed["institution"], "INSTITUTION")

    for sk in fields["skills"]:
        tag_skill_individually(tokens, labels, sk)

    for cn in fields["certs"]:
        tag_exact_words(tokens, labels, cn, "CERT")

    tagged = sum(1 for l in labels if l != "O")
    if tagged < 5:
        return None

    return {"tokens": tokens, "ner_tags": [LABEL2ID.get(l, 0) for l in labels]}


def main():
    print("Loading datasetmaster/resumes...")
    ds = load_dataset("datasetmaster/resumes", split="train")
    print(f"Total: {len(ds)}")

    random.seed(42)
    converted = []
    for idx, sample in enumerate(ds):
        result = build_resume_and_tags(sample)
        if result:
            result["metadata"] = {
                "source": "datasetmaster_resumes",
                "source_id": f"generated:{idx}",
                "group_id": f"generated:{idx}",
            }
            converted.append(result)

    print(f"Converted: {len(converted)}")

    random.shuffle(converted)
    selected = converted[:4000]

    try:
        from training.convert_dataturks import convert_dataturks_sample
        from training.manual_resumes import build_manual_examples
        from training.build_long_resumes import build_examples as build_long_examples
    except ModuleNotFoundError:
        from convert_dataturks import convert_dataturks_sample
        from manual_resumes import build_manual_examples
        from build_long_resumes import build_examples as build_long_examples

    dataturks = []
    with open(DATA_DIR / "sources" / "dataturks_raw.json") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    item = json.loads(line)
                    result = convert_dataturks_sample(item, source_id=f"dataturks:{len(dataturks)}")
                    if result:
                        dataturks.append(result)
                except json.JSONDecodeError:
                    print("Skipped invalid DataTurks JSON line")

    manual = build_manual_examples()
    long_resumes = build_long_examples()

    resume_resource = []
    rr_path = DATA_DIR / "gold" / "resume_resource_gold.json"
    if rr_path.exists():
        with open(rr_path) as f:
            resume_resource = json.load(f)["data"]

    print(f"DataTurks: {len(dataturks)}")
    print(f"Generated: {len(selected)}")
    print(f"Manual templates: {len(manual)}")
    print(f"Long resumes: {len(long_resumes)}")
    print(f"Resume resource: {len(resume_resource)}")

    all_data = dataturks + selected + manual + long_resumes + resume_resource

    clean = []
    for e in all_data:
        name_tokens = [t for t, tag in zip(e["tokens"], e["ner_tags"]) if ID2LABEL[tag] in ("B-NAME", "I-NAME")]
        name = " ".join(name_tokens).lower()
        if name in ("not provided", "unknown", "", "n/a"):
            continue
        if sum(1 for t in e["ner_tags"] if t != 0) < 5:
            continue
        clean.append(e)

    clean, duplicates_removed = dedupe_examples(clean)
    train, val = stable_split_examples(clean, train_ratio=0.85)

    try:
        from training.noise_augment import augment_examples
    except ModuleNotFoundError:
        from noise_augment import augment_examples

    augmented = augment_examples(train, multiplier=2, seed=42)
    print(f"Noise augmented: {len(augmented)} (from {len(train)} train examples)")
    train = train + augmented
    write_dataset(
        train,
        val,
        DATA_DIR,
        manifest={
            "builder": "generate_from_structured.py",
            "sources": {
                "dataturks": len(dataturks),
                "generated": len(selected),
                "manual_templates": len(manual),
                "long_resumes": len(long_resumes),
                "resume_resource": len(resume_resource),
                "noise_augmented": len(augmented),
                "duplicates_removed": duplicates_removed,
            },
        },
    )

    print(f"\nFinal: Train={len(train)}, Val={len(val)}")

    from collections import Counter
    counts = Counter()
    for e in clean:
        for tag in e["ner_tags"]:
            label = ID2LABEL[tag]
            if label != "O":
                counts[label[2:]] += 1
    print("\nLabels:")
    for l, c in counts.most_common():
        print(f"  {l:15s}: {c}")


if __name__ == "__main__":
    main()
