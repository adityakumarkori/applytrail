"""Phase 2 — curated skill vocabulary and recognition helpers.

Stdlib only (`re`). No Streamlit / network / file I/O so the module stays
reusable from a future backend.

Ordering rule: Java / Spring Boot / backend technologies first,
Python / FastAPI second, general tooling last. `find_skills` returns
matches in this priority order.
"""

import re

# 60 canonical skills, priority-ordered. Keep lower-case, human-readable.
SKILL_CANONICAL = (
    # A. Java / Spring / backend primary (20)
    "java",
    "spring boot",
    "spring",
    "spring mvc",
    "spring data jpa",
    "spring security",
    "hibernate",
    "jpa",
    "microservices",
    "rest api",
    "maven",
    "gradle",
    "junit",
    "mockito",
    "kafka",
    "redis",
    "docker",
    "kubernetes",
    "mysql",
    "postgresql",
    # B. Python / FastAPI secondary (10)
    "python",
    "fastapi",
    "django",
    "flask",
    "sqlalchemy",
    "pytest",
    "pandas",
    "numpy",
    "celery",
    "gunicorn",
    # C. General backend / tooling (30)
    "git",
    "github",
    "sql",
    "mongodb",
    "elasticsearch",
    "rabbitmq",
    "aws",
    "azure",
    "gcp",
    "linux",
    "nginx",
    "jenkins",
    "ci/cd",
    "oauth",
    "jwt",
    "json",
    "xml",
    "oop",
    "data structures",
    "algorithms",
    "multithreading",
    "design patterns",
    "unit testing",
    "integration testing",
    "postman",
    "swagger",
    "openapi",
    "tomcat",
    "sqlite",
    "javascript",
)

assert len(SKILL_CANONICAL) == 60, f"expected 60 skills, got {len(SKILL_CANONICAL)}"
assert len(set(SKILL_CANONICAL)) == 60, "duplicate canonical skills"

# Aliases: canonical -> alternative spellings found in resumes.
# Deliberately excludes ambiguous `py` -> `python`.
SKILL_ALIASES = {
    "spring boot": ("springboot", "spring-boot"),
    "spring": ("spring framework", "springframework"),
    "spring mvc": ("spring-mvc", "springmvc"),
    "spring data jpa": ("spring-data-jpa", "springdatajpa"),
    "spring security": ("spring-security", "springsecurity"),
    "hibernate": ("hibernate orm",),
    "microservices": ("microservice", "micro-service", "micro-services"),
    "rest api": ("restapi", "rest-api", "restful api", "restful"),
    "junit": ("junit5", "junit 5"),
    "kafka": ("apache kafka",),
    "redis": ("redis cache",),
    "kubernetes": ("k8s",),
    "mysql": ("my-sql",),
    "postgresql": ("postgres", "psql", "postgre-sql"),
    "python": ("python3", "python 3", "cpython"),
    "fastapi": ("fast api", "fast-api"),
    "sqlalchemy": ("sql-alchemy",),
    "pandas": ("pandas library",),
    "celery": ("celery beat",),
    "github": ("git hub",),
    "mongodb": ("mongo db", "mongo-db", "mongo"),
    "elasticsearch": ("elastic search", "elastic-search"),
    "rabbitmq": ("rabbit mq", "rabbit-mq"),
    "aws": ("amazon web services",),
    "gcp": ("google cloud platform", "google cloud"),
    "ci/cd": ("cicd", "ci cd", "continuous integration"),
    "oauth": ("oauth2", "oauth 2"),
    "jwt": ("json web token",),
    "oop": ("object oriented programming", "oops"),
    "data structures": ("data-structures",),
    "multithreading": ("multi-threading", "multithreaded"),
    "design patterns": ("design-patterns",),
    "unit testing": ("unit-tests", "unittest"),
    "integration testing": ("integration-tests",),
    "postman": ("postman api",),
    "swagger": ("swagger ui",),
    "openapi": ("openapi 3", "open api"),
    "tomcat": ("apache tomcat",),
    "sqlite": ("sqllite",),
    "javascript": ("js", "ecmascript"),
    "jenkins": ("jenkins ci",),
    "nginx": ("nginx server",),
    "linux": ("gnu/linux",),
    "docker": ("docker compose", "docker-compose"),
    "gradle": ("gradle build",),
    "maven": ("maven build",),
    "gunicorn": ("gunicorn server",),
    "flask": ("flask api",),
    "django": ("django rest framework", "django-rest-framework"),
}

# Skills whose match counts toward a Java/Spring vs Python/FastAPI role hint.
JAVA_ROLE_SKILLS = frozenset(
    {
        "java",
        "spring boot",
        "spring",
        "spring mvc",
        "spring data jpa",
        "spring security",
        "hibernate",
        "jpa",
        "maven",
        "gradle",
        "junit",
        "mockito",
    }
)
PYTHON_ROLE_SKILLS = frozenset(
    {"python", "fastapi", "django", "flask", "sqlalchemy"}
)


def _normalize_variant(value):
    """Lower-case, turn hyphens/underscores into spaces, collapse whitespace."""
    value = value.lower().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(text):
    """Normalize free text for matching (never raises on bad input)."""
    if not isinstance(text, str):
        return ""
    return _normalize_variant(text)


def _word_pattern(variant):
    """Regex matching a normalized variant on word boundaries.

    Uses lookarounds instead of \\b so skills containing non-word
    characters (e.g. `ci/cd`) still match, while `java` never matches
    inside `javascript`.
    """
    return re.compile(r"(?<!\w)" + re.escape(_normalize_variant(variant)) + r"(?!\w)")


def skill_evidence(text, skills=None):
    """Map each detected canonical skill to its total match count.

    Counts the canonical form plus all aliases. `skills` optionally
    restricts which canonical skills are searched.
    """
    normalized = normalize_text(text)
    if not normalized:
        return {}
    wanted = set(skills) if skills is not None else None
    evidence = {}
    for canonical in SKILL_CANONICAL:
        if wanted is not None and canonical not in wanted:
            continue
        variants = (canonical,) + SKILL_ALIASES.get(canonical, ())
        count = 0
        for variant in variants:
            pattern = _word_pattern(variant)
            count += len(pattern.findall(normalized))
        if count:
            evidence[canonical] = count
    return evidence


def order_by_priority(skills):
    """Order canonical skills by SKILL_CANONICAL priority, deduped."""
    rank = {name: i for i, name in enumerate(SKILL_CANONICAL)}
    unique = [s for s in dict.fromkeys(skills) if s in rank]
    return sorted(unique, key=lambda s: rank[s])


def find_skills(text, vocabulary=None):
    """Return detected canonical skills, priority-ordered and deduped."""
    return order_by_priority(skill_evidence(text, skills=vocabulary).keys())
