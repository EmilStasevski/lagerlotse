"""Ask the agent one question from the terminal: `task ask -- "Welche Kunden ...?"`.

Prints the answer, the number check and the token usage with estimated cost.
"""

import sys

from sqlalchemy import create_engine

from lagerlotse.agent.agent import Agent
from lagerlotse.config import get_settings

STATUS_LABEL = {
    "verified": "geprüft",
    "unverified": "UNGEPRÜFT",
    "no_numbers": "keine Zahlen",
}


def main() -> None:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        sys.exit('Aufruf: task ask -- "Ihre Frage"')
    settings = get_settings()
    agent = Agent(create_engine(settings.reader_database_url), settings=settings)
    result = agent.ask(question)

    print(result.answer)
    print("\n---")
    print(f"Status: {result.status}, Tools: {', '.join(c.name for c in result.tool_calls) or '-'}")
    checks = result.verification.checks
    print(
        f"Zahlenprüfung: {STATUS_LABEL[result.verification.status]} "
        f"({sum(c.matched for c in checks)}/{len(checks)} belegt)"
    )
    for miss in result.verification.mismatches:
        print(f"  nicht belegt: {miss.text}")
    u = result.usage
    print(
        f"Modell {result.model}: {u.requests} Anfragen, {u.input_tokens} Input-, "
        f"{u.output_tokens} Output-Tokens, {u.cache_read_input_tokens} aus Cache, "
        f"{u.cache_creation_input_tokens} in Cache geschrieben, "
        f"ca. ${u.cost_usd(settings):.4f}"
    )


if __name__ == "__main__":
    main()
