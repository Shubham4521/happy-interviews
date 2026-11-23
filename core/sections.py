"""Single source of truth for search topics and report sections.

Search TOPICS describe what kind of web material we look for.
Report SECTIONS describe what we write, and which topics feed each one.
"""

# topic -> how many searches to run for it (total = 8)
TOPICS = {
    "company": 1,
    "news": 1,
    "process": 2,
    "questions": 2,
    "culture": 1,
    "role_skills": 1,
}

# Backup search templates, used if the AI planner fails or misses a topic
# {level} and {round} may be empty; extra spaces are cleaned up by the planner.
FALLBACK_QUERIES = {
    "company": ["{company} company overview business model"],
    "news": ["{company} latest news {year}"],
    "process": [
        "{company} {level} {role} interview process rounds",
        "{company} {role} interview experience {location}",
    ],
    "questions": [
        "{company} {level} {role} interview questions",
        "{company} {role} {round} interview questions asked",
    ],
    "culture": ["{company} work culture employee reviews {location}"],
    "role_skills": ["{company} {role} job description skills requirements"],
}

# report section -> title, retrieval query, and the topics that feed it
SECTIONS = {
    "company_snapshot": {
        "title": "Company snapshot",
        "query": "{company} business overview, products, scale, recent news, work culture",
        "topics": ["company", "news", "culture"],
    },
    "interview_process": {
        "title": "Interview process",
        "query": "{company} {role} interview process, number of rounds, stages, duration, difficulty",
        "topics": ["process"],
    },
    "likely_questions": {
        "title": "Likely questions",
        "query": "{company} {role} interview questions asked, technical, behavioral, case",
        "topics": ["questions", "process"],
    },
    "talking_points": {
        "title": "Talking points",
        "query": "{company} recent launches, strategy, growth plans, announcements",
        "topics": ["news", "company"],
    },
    "questions_to_ask": {
        "title": "Questions to ask the interviewer",
        "query": "{company} strategy, challenges, team priorities, culture, future direction",
        "topics": ["news", "culture", "company"],
    },
    "prep_checklist": {
        "title": "Prep checklist",
        "query": "{company} {role} required skills, tools, topics to prepare",
        "topics": ["role_skills", "questions"],
    },
}
