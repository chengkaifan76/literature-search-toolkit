import re
import time
from collections import Counter
from typing import Any, Callable

import pandas as pd
import streamlit as st
from scholarly import ProxyGenerator, scholarly
from spellchecker import SpellChecker


st.set_page_config(
    page_title="Literature Search Toolkit",
    page_icon="📚",
    layout="wide",
)


SEPARATOR_PATTERN = r"[-\u2010\u2011\u2012\u2013\u2014\u2212_/]+"
REVIEW_PATTERN = re.compile(r"\b(review|reviews|reviewed|reviewing)\b", re.IGNORECASE)

TECHNICAL_TERMS = [
    "mineralization",
    "geometallurgy",
    "geostatistics",
    "haulage",
    "decarbonization",
    "carbonation",
    "geotechnical",
    "lithium",
    "xgboost",
    "optuna",
    "ccus",
    "ccs",
    "shap",
    "geospatial",
    "metallurgical",
    "hydrometallurgy",
    "pyrometallurgy",
    "bioleaching",
    "geomechanics",
    "geochemistry",
    "mineralogy",
    "valorization",
    "tailings",
    "backfill",
    "orebody",
    "orebodies",
    "multiphysics",
    "multivariate",
    "explainability",
    "criticality",
    "mineralogical",
    "geometallurgical",
    "hydrometallurgical",
    "pyrometallurgical",
    "electrometallurgy",
    "sequestration",
    "carbonization",
    "carbonatation",
    "geochemical",
    "petrophysical",
    "geomechanical",
    "multiphase",
    "multiscale",
    "multimodal",
    "hyperparameter",
    "hyperparameters",
    "explainable",
    "transferability",
    "generalizability",
]


@st.cache_resource
def get_spell_checker() -> SpellChecker:
    checker = SpellChecker(language="en", distance=2)
    checker.word_frequency.load_words(TECHNICAL_TERMS)
    return checker


def get_optional_secret(name: str) -> str:
    try:
        value = st.secrets[name]
    except Exception:
        return ""
    return str(value).strip()


@st.cache_resource
def configure_scholarly() -> str:
    """Configure scholarly once per app process."""
    scholarly.set_timeout(30)
    scholarly.set_retries(2)

    scraper_api_key = get_optional_secret("SCRAPERAPI_KEY")
    if not scraper_api_key:
        return "Direct connection"

    proxy_generator = ProxyGenerator()
    if proxy_generator.ScraperAPI(scraper_api_key):
        scholarly.use_proxy(proxy_generator)
        return "ScraperAPI proxy"

    return "Direct connection because proxy setup failed"


def normalize_keyword_spacing(text: Any) -> str:
    text = str(text).strip()
    text = re.sub(SEPARATOR_PATTERN, " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_search_text(text: Any) -> str:
    return normalize_keyword_spacing(text).casefold()


def format_query_term(term: Any) -> str:
    normalized = normalize_search_text(term)
    if not normalized:
        return ""
    if " " in normalized:
        return f'"{normalized}"'
    return normalized


def contains_keyword(text: Any, keyword: Any) -> bool:
    normalized_text = normalize_search_text(text)
    normalized_keyword = normalize_search_text(keyword)

    if not normalized_keyword:
        return False

    pattern = rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)"
    return re.search(pattern, normalized_text) is not None


def get_spelling_suggestions(keyword_groups: list[str]) -> dict[str, str]:
    checker = get_spell_checker()
    words_to_check: list[str] = []

    for phrase in keyword_groups:
        for word in normalize_search_text(phrase).split():
            if not word.isalpha() or len(word) <= 2:
                continue
            words_to_check.append(word)

    misspelled_words = checker.unknown(words_to_check)
    suggestions: dict[str, str] = {}

    for word in sorted(misspelled_words):
        correction = checker.correction(word)
        if correction and correction != word:
            suggestions[word] = correction

    return suggestions


def build_query(keywords: list[str], remove_keywords: list[str]) -> str:
    positive_terms = [format_query_term(keyword) for keyword in keywords]
    negative_terms = [f"-{format_query_term(keyword)}" for keyword in remove_keywords]
    terms = [term for term in positive_terms + negative_terms if term and term != "-"]
    return " ".join(terms)


def format_authors(authors: Any) -> str:
    if isinstance(authors, (list, tuple)):
        return ", ".join(str(author) for author in authors)
    return str(authors or "No author")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def search_literature(
    params: dict[str, Any],
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> dict[str, Any]:
    start_time = time.time()
    query = build_query(params["keywords"], params["remove_keywords"])

    search_query = scholarly.search_pubs(
        query,
        year_low=params["start_year"],
        year_high=params["end_year"],
    )

    target_count = params["results_to_fetch"]
    max_candidates_to_check = max(target_count * 5, 50)

    results: list[dict[str, Any]] = []
    candidates_checked = 0
    consecutive_errors = 0
    last_error = ""

    while len(results) < target_count and candidates_checked < max_candidates_to_check:
        try:
            publication = next(search_query)
            candidates_checked += 1
            consecutive_errors = 0
        except StopIteration:
            break
        except Exception as exc:
            consecutive_errors += 1
            last_error = str(exc)
            if consecutive_errors >= 3:
                break
            time.sleep(2)
            continue

        bib_info = publication.get("bib", {})
        pub_year = str(bib_info.get("pub_year", "N/A"))
        pub_title = str(bib_info.get("title", "No title") or "No title")
        pub_abstract = str(bib_info.get("abstract", "") or "")
        pub_authors = format_authors(bib_info.get("author", "No author"))
        pub_url = str(publication.get("pub_url", "") or "")
        citation_count = safe_int(publication.get("num_citations", 0))

        document_text = f"{pub_title} {pub_abstract}"

        if any(
            contains_keyword(document_text, keyword)
            for keyword in params["remove_keywords"]
        ):
            if progress_callback:
                progress_callback(len(results), target_count, candidates_checked)
            continue

        if not pub_year.isdigit():
            if progress_callback:
                progress_callback(len(results), target_count, candidates_checked)
            continue

        year_value = int(pub_year)
        if not params["start_year"] <= year_value <= params["end_year"]:
            if progress_callback:
                progress_callback(len(results), target_count, candidates_checked)
            continue

        if params["review_only"] and not REVIEW_PATTERN.search(document_text):
            if progress_callback:
                progress_callback(len(results), target_count, candidates_checked)
            continue

        results.append(
            {
                "No.": len(results) + 1,
                "Title": pub_title,
                "Authors": pub_authors,
                "Year": year_value,
                "Citations": citation_count,
                "URL": pub_url,
            }
        )

        if progress_callback:
            progress_callback(len(results), target_count, candidates_checked)

    return {
        "query": query,
        "results": results,
        "candidates_checked": candidates_checked,
        "elapsed_seconds": time.time() - start_time,
        "last_error": last_error,
        "target_count": target_count,
    }


def execute_search(params: dict[str, Any]) -> None:
    connection_status = configure_scholarly()
    progress_bar = st.progress(0)
    status = st.empty()

    def update_progress(accepted: int, target: int, checked: int) -> None:
        fraction = min(accepted / max(target, 1), 0.99)
        progress_bar.progress(fraction)
        status.info(
            f"Searching: {accepted}/{target} accepted papers, "
            f"{checked} candidates checked."
        )

    try:
        output = search_literature(params, update_progress)
    except Exception as exc:
        progress_bar.empty()
        status.empty()
        st.session_state.search_output = None
        st.error(f"Search failed: {exc}")
        return

    progress_bar.progress(1.0)
    status.success(
        f"Search completed using {connection_status} in "
        f"{output['elapsed_seconds']:.2f} seconds."
    )
    st.session_state.search_output = output


def clear_pending_confirmation() -> None:
    st.session_state.awaiting_spelling_confirmation = False
    st.session_state.pending_params = None
    st.session_state.pending_suggestions = {}


def display_results(output: dict[str, Any]) -> None:
    st.divider()
    st.subheader("Search results")
    st.caption("Final query submitted to Google Scholar")
    st.code(output["query"], language=None)

    results = output["results"]
    accepted_count = len(results)

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Accepted papers", accepted_count)
    metric_2.metric("Candidates checked", output["candidates_checked"])
    metric_3.metric("Response time", f"{output['elapsed_seconds']:.2f} s")

    if not results:
        st.warning("No publications matched all search conditions.")
        if output["last_error"]:
            st.caption(f"Last search error: {output['last_error']}")
        return

    if accepted_count < output["target_count"]:
        st.warning(
            f"Only {accepted_count} publications matched all conditions after "
            f"checking {output['candidates_checked']} candidates."
        )

    dataframe = pd.DataFrame(results)

    st.dataframe(
        dataframe,
        hide_index=True,
        use_container_width=True,
        column_config={
            "No.": st.column_config.NumberColumn(width="small"),
            "Title": st.column_config.TextColumn(width="large"),
            "Authors": st.column_config.TextColumn(width="large"),
            "Year": st.column_config.NumberColumn(format="%d", width="small"),
            "Citations": st.column_config.NumberColumn(format="%d", width="small"),
            "URL": st.column_config.LinkColumn("Publication link", display_text="Open"),
        },
    )

    csv_data = dataframe.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Download results as CSV",
        data=csv_data,
        file_name="literature_search_results.csv",
        mime="text/csv",
    )

    left_column, right_column = st.columns([1, 1.4])

    with left_column:
        st.subheader("Top 3 most-cited papers")
        top_cited = dataframe.nlargest(3, "Citations")[
            ["No.", "Title", "Year", "Citations", "URL"]
        ]
        st.dataframe(
            top_cited,
            hide_index=True,
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("Link", display_text="Open"),
            },
        )

    with right_column:
        st.subheader("Publications per year")
        year_counts = Counter(dataframe["Year"].tolist())
        chart_data = pd.DataFrame(
            {
                "Year": sorted(year_counts),
                "Publications": [year_counts[year] for year in sorted(year_counts)],
            }
        ).set_index("Year")
        st.bar_chart(chart_data)


for key, default_value in {
    "search_output": None,
    "awaiting_spelling_confirmation": False,
    "pending_params": None,
    "pending_suggestions": {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


st.title("Literature Search Toolkit")
st.caption("Designed by Dr. Chengkai Fan at Université Laval")

with st.expander("Important note about Google Scholar access", expanded=False):
    st.write(
        "This app uses the scholarly Python package to retrieve Google Scholar "
        "results. Google Scholar may block automated requests, especially from "
        "shared cloud IP addresses. The app supports an optional ScraperAPI key "
        "through Streamlit secrets for more reliable access."
    )

with st.form("literature_search_form"):
    st.subheader("Enter Keywords")
    keyword_columns = st.columns(5)
    keywords = [
        column.text_input(f"Keyword {index + 1}", key=f"keyword_{index}")
        for index, column in enumerate(keyword_columns)
    ]

    st.subheader("Remove Keywords")
    remove_columns = st.columns(5)
    remove_keywords = [
        column.text_input(
            f"Remove keyword {index + 1}",
            key=f"remove_keyword_{index}",
        )
        for index, column in enumerate(remove_columns)
    ]

    option_1, option_2, option_3, option_4 = st.columns([1, 1, 1.2, 1])

    with option_1:
        start_year = st.number_input(
            "Start year",
            min_value=1800,
            max_value=2100,
            value=2000,
            step=1,
        )

    with option_2:
        end_year = st.number_input(
            "End year",
            min_value=1800,
            max_value=2100,
            value=2026,
            step=1,
        )

    with option_3:
        results_to_fetch = st.selectbox(
            "Number of results",
            options=[5, 10, 20, 30, 40, 50, 100, 200],
            index=1,
        )

    with option_4:
        review_only = st.checkbox("Review papers only")

    submitted = st.form_submit_button("Search", type="primary", use_container_width=True)


if submitted:
    cleaned_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
    cleaned_remove_keywords = [
        keyword.strip() for keyword in remove_keywords if keyword.strip()
    ]

    if not cleaned_keywords:
        st.error("Please enter at least one keyword.")
    elif int(start_year) > int(end_year):
        st.error("Start year cannot be greater than end year.")
    else:
        params = {
            "keywords": cleaned_keywords,
            "remove_keywords": cleaned_remove_keywords,
            "start_year": int(start_year),
            "end_year": int(end_year),
            "review_only": bool(review_only),
            "results_to_fetch": int(results_to_fetch),
        }

        suggestions = get_spelling_suggestions(
            cleaned_keywords + cleaned_remove_keywords
        )

        st.session_state.search_output = None

        if suggestions:
            st.session_state.awaiting_spelling_confirmation = True
            st.session_state.pending_params = params
            st.session_state.pending_suggestions = suggestions
        else:
            clear_pending_confirmation()
            execute_search(params)


if st.session_state.awaiting_spelling_confirmation:
    suggestions = st.session_state.pending_suggestions
    suggestion_text = "\n".join(
        f"- `{word}` -> `{suggestion}`"
        for word, suggestion in suggestions.items()
    )

    st.warning(
        "Possible spelling errors were detected. The keywords will not be "
        "changed automatically.\n\n" + suggestion_text
    )

    confirmation_column, cancel_column = st.columns(2)

    with confirmation_column:
        if st.button(
            "Continue with current spelling",
            type="primary",
            use_container_width=True,
        ):
            pending_params = st.session_state.pending_params
            clear_pending_confirmation()
            if pending_params:
                execute_search(pending_params)

    with cancel_column:
        if st.button("Return and revise", use_container_width=True):
            clear_pending_confirmation()
            st.info("Revise the keywords above, then select Search again.")


if st.session_state.search_output:
    display_results(st.session_state.search_output)
