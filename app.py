import streamlit as st

st.set_page_config(page_title="HappyInterviews", page_icon="🎯", layout="centered")

st.title("🎯 HappyInterviews")
st.subheader("Your AI interview prep assistant")
st.write(
    "Enter a company, role and location, and get a researched prep report: "
    "company snapshot, interview process, likely questions, talking points and more, "
    "with sources for everything."
)
st.info("🚧 Under construction. Phase 0: setup check.")

st.divider()
st.markdown("#### System check")
st.caption("Confirms that all three services are connected. Keys stay private in Streamlit Secrets.")


def check_tavily():
    from tavily import TavilyClient
    client = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    result = client.search("Swiggy company overview", max_results=1)
    return f"Search works ({len(result.get('results', []))} result returned)"


def check_groq():
    from groq import Groq
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    models = client.models.list()
    return f"Connected ({len(models.data)} models available)"


def check_gemini():
    from google import genai
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    models = list(client.models.list())
    return f"Connected ({len(models)} models available)"


if st.button("Run system check", type="primary"):
    for name, check in [("Tavily (web search)", check_tavily),
                        ("Groq (free LLM)", check_groq),
                        ("Gemini (backup LLM)", check_gemini)]:
        with st.spinner(f"Checking {name}..."):
            try:
                st.success(f"✅ {name}: {check()}")
            except KeyError:
                st.error(f"❌ {name}: API key missing in Secrets")
            except Exception as e:
                st.error(f"❌ {name}: {type(e).__name__}: {e}")
