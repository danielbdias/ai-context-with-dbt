"""Fixed submissions shared by `task seed` and the e2e stages.

The messages are chosen so later stages can assert word frequencies:
"dados" appears 3 times, "café" and "cafe" once each (they fold together),
and "the", "de" and "que" are stopwords that must not reach the marts.
"""

from typing import NamedTuple

CHROME_MAC_A = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
CHROME_MAC_B = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
SAFARI_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)

PT_LANGUAGE = "pt-BR,pt;q=0.9,en;q=0.8"
EN_LANGUAGE = "en-US,en;q=0.9"


class Sample(NamedTuple):
    """One good submission and the families ua-parser must report for it."""

    message: str
    user_agent: str
    accept_language: str
    browser_family: str
    os_family: str


SAMPLES: tuple[Sample, ...] = (
    Sample(
        "Adoro café com dados abertos, que bom",
        CHROME_MAC_A,
        PT_LANGUAGE,
        "Chrome",
        "Mac OS X",
    ),
    Sample(
        "The cafe near the office has great coffee",
        CHROME_MAC_B,
        EN_LANGUAGE,
        "Chrome",
        "Mac OS X",
    ),
    Sample(
        "Os dados de hoje mostram que o tempo muda",
        CHROME_MAC_A,
        PT_LANGUAGE,
        "Chrome",
        "Mac OS X",
    ),
    Sample(
        "Data quality matters, the pipeline needs good dados",
        FIREFOX_LINUX,
        EN_LANGUAGE,
        "Firefox",
        "Linux",
    ),
    Sample(
        "Qualidade importa mais do que velocidade",
        FIREFOX_LINUX,
        PT_LANGUAGE,
        "Firefox",
        "Linux",
    ),
    Sample(
        "Loving this demo, the dashboard looks great",
        SAFARI_IOS,
        EN_LANGUAGE,
        "Mobile Safari",
        "iOS",
    ),
)

# Folded words (lowercase, accents stripped) and their expected totals.
EXPECTED_WORD_COUNTS = {"cafe": 2, "dados": 3, "great": 2, "pipeline": 1}
STOPWORDS_PRESENT = ("the", "de", "que")
