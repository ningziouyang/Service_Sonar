# Service Sonar

## Streamlit Community Cloud

Use the following deployment settings:

- Repository: this GitHub repository
- Branch: the branch containing the dashboard
- Main file path: `streamlit_app.py`
- Python version: 3.12

The dashboard reads `service_sonar.db` from the repository. Generate or update
the database locally, then commit and push the database when the published data
should change.

Do not commit `.env` or API keys. If the deployed app later needs credentials,
add them through Streamlit Community Cloud's **Advanced settings > Secrets**.

Activate VENV
source .venv/bin/activate

Activate Streamlit
python -m streamlit run dashboard.py
