"""One-off generator for synthetic mock_data/*.json fixtures so the server
is fully testable in MOCK_MODE before any real Workday connection exists.
Re-run any time: `python scripts/generate_mock_data.py`."""

import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
OUT = Path(__file__).resolve().parent.parent / "mock_data"
OUT.mkdir(exist_ok=True)

DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Finance", "HR", "Customer Success", "Operations"]
REGIONS = ["NA", "EMEA", "APAC", "LATAM"]
JOB_FAMILIES = ["Software Engineering", "Sales", "Marketing", "Finance", "People", "Support", "Operations"]
GRADES = ["G5", "G6", "G7", "G8", "G9", "G10"]
LEVELS = ["IC1", "IC2", "IC3", "M1", "M2", "M3"]
MANAGERS = [f"Manager {c}" for c in "ABCDEFGH"]
FIRST = ["Alex", "Jordan", "Taylor", "Sam", "Casey", "Riley", "Morgan", "Jamie", "Priya", "Wei", "Fatima", "Diego"]
LAST = ["Smith", "Lee", "Garcia", "Kim", "Patel", "Chen", "Nguyen", "Brown", "Muller", "Rossi"]


def rand_date(start_year=2018, end=date(2026, 7, 4)):
    start = date(start_year, 1, 1)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def gen_workers(n=500):
    rows = []
    for i in range(1, n + 1):
        active = random.random() > 0.12  # ~12% terminated
        hire_date = rand_date(2016)
        term_date = None
        term_cat = None
        regrettable = None
        term_reason = None
        if not active:
            term_date = rand_date(2022)
            term_cat = random.choice(["Voluntary", "Voluntary", "Voluntary", "Involuntary"])
            regrettable = "Yes" if term_cat == "Voluntary" and random.random() < 0.35 else "No"
            term_reason = random.choice(["Better Opportunity", "Relocation", "Performance", "Compensation", "Retirement"])
        rows.append({
            "Worker": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Employee_ID": f"E{100000+i}",
            "Active_Status": "Active" if active else "Terminated",
            "Employee_Type": "Contractor" if random.random() < 0.08 else "Employee",
            "Full_Time_Part_Time": "Part_Time" if random.random() < 0.06 else "Full_Time",
            "Hire_Date": hire_date,
            "Original_Hire_Date": hire_date,
            "Termination_Date": term_date,
            "Termination_Reason": term_reason,
            "Termination_Category": term_cat,
            "Regrettable_Termination": regrettable,
            "Department": random.choice(DEPARTMENTS),
            "Cost_Center": f"CC-{random.randint(100,199)}",
            "Region": random.choice(REGIONS),
            "Location_Country": random.choice(["USA", "UK", "India", "Germany", "Brazil", "Singapore"]),
            "Manager": random.choice(MANAGERS),
            "Manager_Employee_ID": f"E{random.randint(100000,100010)}",
            "Job_Family": random.choice(JOB_FAMILIES),
            "Job_Profile": random.choice(JOB_FAMILIES) + " " + random.choice(["I", "II", "III", "Senior", "Lead"]),
            "Business_Title": random.choice(["Analyst", "Engineer", "Manager", "Director", "Specialist"]),
            "Management_Level": random.choice(LEVELS),
            "Compensation_Grade": random.choice(GRADES),
            "Base_Pay": random.randint(55000, 220000),
            "Bonus_Target_Pct": random.choice([0, 5, 10, 15, 20]),
            "Last_Merit_Increase_Pct": round(random.uniform(0, 8), 1),
            "Performance_Rating": random.choice(["Exceeds", "Meets", "Meets", "Meets", "Below", "Outstanding"]),
            "Performance_Rating_Date": rand_date(2025),
            "Nine_Box_Rating": random.choice(["High Performer/High Potential", "Core Player", "Emerging Talent", "Risk"]),
            "Potential_Rating": random.choice(["High", "Medium", "Low"]),
            "Time_in_Job_Profile_Days": random.randint(30, 2000),
            "Time_in_Position_Days": random.randint(30, 2000),
            "Is_Manager": "Yes" if random.random() < 0.15 else "No",
            "Direct_Report_Count": random.randint(0, 12),
            "Budgeted_Position": "Yes" if random.random() < 0.92 else "No",
        })
    return rows


def gen_requisitions(n=60):
    rows = []
    for i in range(1, n + 1):
        opened = rand_date(2025)
        filled = random.random() < 0.7
        days_open = random.randint(10, 120)
        rows.append({
            "Requisition_ID": f"R{2000+i}",
            "Job_Requisition_Status": "Filled" if filled else random.choice(["Open", "Closed"]),
            "Department": random.choice(DEPARTMENTS),
            "Region": random.choice(REGIONS),
            "Recruiter": random.choice(["Recruiter 1", "Recruiter 2", "Recruiter 3"]),
            "Hiring_Manager": random.choice(MANAGERS),
            "Date_Opened": opened,
            "Date_Filled": (date.fromisoformat(opened) + timedelta(days=days_open)).isoformat() if filled else None,
            "Days_Open": days_open,
            "Source_of_Hire": random.choice(["Referral", "Job Board", "LinkedIn", "Agency", "Internal"]),
            "Internal_External": "Internal" if random.random() < 0.2 else "External",
            "Candidate_Stage": random.choice(["Sourced", "Screening", "Interview", "Offer", "Hired"]),
            "Offer_Status": random.choice(["Accepted", "Declined", "Pending", None]),
            "Critical_Role": "Yes" if random.random() < 0.15 else "No",
        })
    return rows


def gen_nine_box(n=200):
    rows = []
    for i in range(n):
        rows.append({
            "Worker": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Department": random.choice(DEPARTMENTS),
            "Manager": random.choice(MANAGERS),
            "Region": random.choice(REGIONS),
            "Nine_Box_Category": random.choice([
                "High Performer/High Potential", "Core Player", "Emerging Talent",
                "Trusted Professional", "Risk", "Inconsistent Player",
            ]),
            "Review_Cycle": "2026-H1",
            "Successor_Readiness": random.choice(["Ready Now", "1-2 Years", "3-5 Years", "None"]),
            "Critical_Role_Flag": "Yes" if random.random() < 0.2 else "No",
        })
    return rows


def gen_mobility(n=80):
    rows = []
    for i in range(n):
        rows.append({
            "Worker": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Department": random.choice(DEPARTMENTS),
            "Manager": random.choice(MANAGERS),
            "Region": random.choice(REGIONS),
            "Event_Type": random.choice(["Promotion", "Lateral Move", "Transfer"]),
            "Event_Date": rand_date(2024),
            "Prior_Job_Profile": random.choice(JOB_FAMILIES),
            "New_Job_Profile": random.choice(JOB_FAMILIES),
            "Prior_Compensation_Grade": random.choice(GRADES),
            "New_Compensation_Grade": random.choice(GRADES),
            "Internal_Candidate": "Yes",
        })
    return rows


def gen_learning(n=300):
    rows = []
    for i in range(n):
        rows.append({
            "Worker": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Department": random.choice(DEPARTMENTS),
            "Region": random.choice(REGIONS),
            "Learning_Hours": round(random.uniform(0, 40), 1),
            "Compliance_Training_Status": "Complete" if random.random() < 0.85 else "Incomplete",
            "Certifications_Earned": random.randint(0, 4),
            "Certification_Expiration_Date": rand_date(2026, date(2027, 12, 31)),
            "Leadership_Program_Enrolled": "Yes" if random.random() < 0.1 else "No",
        })
    return rows


def gen_skills(n=400):
    skills = ["Python", "Data Analysis", "Cloud Architecture", "Project Management", "Sales Negotiation", "SQL", "Leadership"]
    rows = []
    for i in range(n):
        rows.append({
            "Worker": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Department": random.choice(DEPARTMENTS),
            "Region": random.choice(REGIONS),
            "Skill_Name": random.choice(skills),
            "Skill_Proficiency_Level": random.choice(["Beginner", "Intermediate", "Advanced", "Expert"]),
            "Skill_Category": random.choice(["Critical", "Emerging", "Core"]),
            "Verified": "Yes" if random.random() < 0.6 else "No",
        })
    return rows


def gen_engagement(n=300):
    rows = []
    for i in range(n):
        rows.append({
            "Worker": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "Department": random.choice(DEPARTMENTS),
            "Manager": random.choice(MANAGERS),
            "Region": random.choice(REGIONS),
            "Survey_Cycle": "2026-Q2",
            "Participated": "Yes" if random.random() < 0.78 else "No",
            "Engagement_Score": random.randint(1, 5),
            "Manager_Effectiveness_Score": random.randint(1, 5),
            "Burnout_Risk_Flag": "Yes" if random.random() < 0.1 else "No",
        })
    return rows


GENERATORS = {
    "workers_report.json": gen_workers,
    "requisitions_report.json": gen_requisitions,
    "nine_box_report.json": gen_nine_box,
    "mobility_report.json": gen_mobility,
    "learning_report.json": gen_learning,
    "skills_report.json": gen_skills,
    "engagement_report.json": gen_engagement,
}

if __name__ == "__main__":
    for filename, gen_fn in GENERATORS.items():
        rows = gen_fn()
        with open(OUT / filename, "w", encoding="utf-8") as f:
            json.dump({"Report_Entry": rows}, f, indent=2)
        print(f"wrote {len(rows)} rows -> mock_data/{filename}")
