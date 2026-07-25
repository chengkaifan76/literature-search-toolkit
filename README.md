# Literature Search Toolkit Web App

This folder contains a Streamlit web version of the Tkinter Literature Search Toolkit.

## Files

- `streamlit_app.py`: web application
- `requirements.txt`: Python dependencies
- `.streamlit/config.toml`: dark theme configuration
- `.gitignore`: prevents local secrets from being uploaded

## Test locally

Use Python 3.11 if possible.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS or Linux:

```bash
source .venv/bin/activate
```

Install and run:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app will open in a browser, normally at `http://localhost:8501`.

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload all files in this folder. Keep `.streamlit/config.toml` in the `.streamlit` folder.
3. Sign in to Streamlit Community Cloud with GitHub.
4. Select **Create app**.
5. Select the GitHub repository and branch.
6. Set the entrypoint file to `streamlit_app.py`.
7. In Advanced settings, choose Python 3.11.
8. Select **Deploy**.

Streamlit will create a public URL ending in `streamlit.app`.

## Optional proxy for more reliable Google Scholar access

Google Scholar may block automated searches from shared cloud IP addresses. This app supports ScraperAPI through a Streamlit secret.

In the Streamlit app settings, add:

```toml
SCRAPERAPI_KEY = "your_api_key_here"
```

Do not commit `.streamlit/secrets.toml` or an API key to a public GitHub repository.

## Important limitation

The web interface can be deployed reliably, but the Google Scholar data connection is based on the unofficial `scholarly` scraper. A public app may therefore encounter CAPTCHA, rate limiting, or temporary blocks. For a production-grade service, consider replacing the search backend with an academic search API such as OpenAlex or Semantic Scholar, or use a supported proxy service.
