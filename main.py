from openai import OpenAI

GROQ_API_KEY = "gsk_xxxx_Hier_deinen_Groq_Key_einfügen"
client_groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

def agent_groq_cleaner():
    """
    Agent 2: Textbereinigung, Anonymisierung & Relevanzprüfung.
    """
    print("[Agent 2] Rufe Llama 3.2 via Groq-API auf...")
    # -----------------------------------------------------------------
    # TODO: TASK FÜR TEAMMITGLIED A (Prompt Engineering & API-Aufruf)
    # -----------------------------------------------------------------
    pass

if __name__ == "__main__":
    agent_groq_cleaner()