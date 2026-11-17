# AI Business Intelligence Assistant

A **dynamic GenAI CSV business analyst** built with Streamlit, Python/pandas, SQLite (already built into Python), Plotly, and the Google Gemini API.

## What it does

1. Upload a business CSV (sales, HR, banking, inventory, finance, marketing, etc.).
2. Explore the uploaded columns, data types, missing values, and a grouped dashboard.
3. Ask a natural-language question, e.g. "Which region has the highest total revenue?"
4. Gemini generates a read-only SQLite query based on **the current file's columns**.
5. SQLite calculates the answer from the CSV; the app displays actual results, a chart, and a brief explanation.
6. Download the query result as CSV; inspect the SQL for transparency.

**It does not need model training, a fixed CSV schema, or an `.env` file.** It requires your own Gemini API key and internet access for AI questions.

## Easiest way to run on Windows

Extract the ZIP. Double-click `start_windows.bat` in the extracted folder. It creates a virtual environment, installs required Python packages, and starts Streamlit. Python 3.11+ and internet are required for first-time installation.

## Run on Windows (PowerShell or VS Code terminal)

```powershell
cd path\to\ai_bi_assistant
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

If `py` is not recognized, use `python` for the virtual environment command.

Open the local URL shown in the terminal (usually http://localhost:8501). Upload `sample_data.csv`. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey), paste it in the app sidebar (the key is not written to a project file). Confirm the Gemini model name currently available to your account; you can change it in the sidebar.

Suggested demo questions:

- What is the total revenue?
- Which region has the highest revenue?
- Give monthly revenue trend using order_date.
- Show the 5 products with the most profit.
- What is average order quantity by customer_segment?

## How dataset independence works

Only the current CSV schema (its column names and detected types), and the question, are used to **generate** SQL. The SQL is run on a temporary, in-memory SQLite table called `data`. The app does not rely on pre-programmed `revenue`, `profit`, or `region` columns. Dataframes are not used to train a model.

## Privacy and safe use

- The uploaded CSV is loaded into the Streamlit app's Python process. No raw CSV file is uploaded to Gemini.
- **Gemini receives column names, the typed question, and up to 15 rows of the resulting query output** for its written explanation. These may contain private information; only analyze data you have permission to share with the selected API.
- SQLite's read-only authorizer rejects modifications and disallows file operations and external functions. AI-generated SQL can still be incorrect: review the generated query and validate important results.
- The starter limits input files to 20MB, caps displayed query results to 100 rows, and attempts to interrupt slow SQL after six seconds.
- It uses a single CSV at a time. Multi-table joins, auto-cleaning, ambiguous business terms, and complex forecasting are not guaranteed.
- Even a valid answer depends on correct data types and your dataset's definitions of revenue/profit/etc. This is **not a universal error-free analyst**.

## Folder structure

```text
ai_bi_assistant/
  app.py                 # Streamlit user interface + Gemini calls
  engine.py              # CSV reader and restricted SQLite query runner
  requirements.txt       # Packages to install
  start_windows.bat      # Optional one-click startup
  sample_data.csv        # Synthetic example data
  tests/test_engine.py   # Basic SQL safety/functionality tests
  README.md              # Instructions
```

## Test the core engine

Install `pytest` if you want to run tests, then execute:

```powershell
python -m pip install pytest
python -m pytest -q
```

## Troubleshooting

- **ModuleNotFoundError**: activate your environment and run `python -m pip install -r requirements.txt`.
- **Gemini model not found**: change the model field to a supported Gemini text model.
- **API error/quota**: check your key, internet connection, and API usage limits.
- **Wrong columns/types**: check the CSV header, delimiter selection, and original data encoding.
- **Incorrect AI query**: open "Show generated SQL" to see the exact calculation, and ask a more specific question.
