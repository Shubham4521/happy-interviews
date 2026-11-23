"""The evaluation test set: 15 cases across industries, levels and interview rounds.

`small=True` marks companies with little public information, where the app
should say "limited information" instead of inventing details.
"""

CASES = [
    {"id": 1, "company": "Google", "role": "Data Scientist", "location": "Bengaluru", "level": "3-6 years", "round": "Technical"},
    {"id": 2, "company": "Swiggy", "role": "Data Analyst", "location": "Bengaluru", "level": "Fresher", "round": "All rounds"},
    {"id": 3, "company": "McKinsey & Company", "role": "Business Analyst", "location": "Gurugram", "level": "Fresher", "round": "Case study"},
    {"id": 4, "company": "HDFC Bank", "role": "Data Scientist", "location": "Mumbai", "level": "3-6 years", "round": "All rounds"},
    {"id": 5, "company": "Sigmoid", "role": "Data Engineer", "location": "Bengaluru", "level": "Intern", "round": "Technical", "small": True},
    {"id": 6, "company": "Flipkart", "role": "Data Analyst", "location": "Bengaluru", "level": "Fresher", "round": "Technical"},
    {"id": 7, "company": "Deloitte", "role": "Business Analyst", "location": "Hyderabad", "level": "Fresher", "round": "Case study"},
    {"id": 8, "company": "Zomato", "role": "Product Analyst", "location": "Gurugram", "level": "1-3 years", "round": "All rounds"},
    {"id": 9, "company": "Amazon", "role": "Business Intelligence Engineer", "location": "Hyderabad", "level": "1-3 years", "round": "Technical"},
    {"id": 10, "company": "Infosys", "role": "Data Analyst", "location": "Pune", "level": "Fresher", "round": "HR"},
    {"id": 11, "company": "Microsoft", "role": "Data Scientist", "location": "Hyderabad", "level": "6+ years", "round": "Managerial"},
    {"id": 12, "company": "Razorpay", "role": "Data Analyst", "location": "Bengaluru", "level": "1-3 years", "round": "All rounds"},
    {"id": 13, "company": "Tiger Analytics", "role": "Data Scientist", "location": "Chennai", "level": "Fresher", "round": "Technical"},
    {"id": 14, "company": "Accenture", "role": "Analytics Consultant", "location": "Bengaluru", "level": "3-6 years", "round": "Case study"},
    {"id": 15, "company": "Lentra", "role": "Data Analyst", "location": "Pune", "level": "Fresher", "round": "All rounds", "small": True},
]


def case_label(case: dict) -> str:
    return f"{case['company']}, {case['role']} ({case['level']}, {case['round']})"
