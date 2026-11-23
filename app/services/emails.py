MAX_EMAIL_LENGTH = 320


def canonicalize_email(email: str) -> str:
    return email.strip().lower()


def email_problem(canonical_email: str) -> str | None:
    if len(canonical_email) > MAX_EMAIL_LENGTH:
        return f"email exceeds {MAX_EMAIL_LENGTH} characters"
    if canonical_email.count("@") != 1 or any(ch.isspace() for ch in canonical_email):
        return "Invalid email address"
    local_part, _, domain = canonical_email.partition("@")
    domain_is_valid = (
        "." in domain
        and not domain.startswith(".")
        and not domain.endswith(".")
        and ".." not in domain
    )
    if not local_part or not domain_is_valid:
        return f"Invalid email address: {canonical_email}"
    return None
