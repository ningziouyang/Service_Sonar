import json
from openai import OpenAI

OPENAI_API_KEY = "sk-proj-xxxx_Hier_deinen_OpenAI_Key_einfügen"
client_openai = OpenAI(
    api_key=OPENAI_API_KEY
)

def agent_gpt_analyzer():
    """
    Agent 3: Qualitative Tiefenanalyse (JSON-Interface).
    """
    print("[Agent 3] Rufe GPT-4o via OpenAI-API auf...")
    # -----------------------------------------------------------------
    # TODO: TASK FÜR TEAMMITGLIED B (Structured Outputs & Soziale Kategorien)
    # -----------------------------------------------------------------
    pass

def agent_report_generator():
    """
    Agent 4: Aggregation & Akademische Berichterstattung (.md Export).
    """
    print("[Agent 4] Generiere finalen akademischen Evaluierungsbericht...")
    # -----------------------------------------------------------------
    # TODO: TASK FÜR TEAMMITGLIED B (Reines Python-Skript ohne KI)
    # -----------------------------------------------------------------
    pass

if __name__ == "__main__":
    agent_gpt_analyzer()
    agent_report_generator()