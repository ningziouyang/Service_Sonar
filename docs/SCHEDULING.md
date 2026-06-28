# Service Sonar Scheduled Refresh

Service Sonar does not require full live-stream processing for the prototype.
Instead, the pipeline can be refreshed automatically on a schedule, for example once per night outside office hours.

The scheduled refresh runs:

```text
Agent 1 scraper
→ Agent 2 cleaner
→ Agent 3 analyzer
→ Agent 4 innovator
→ updated SQLite database
→ Streamlit dashboard reads the updated data
```