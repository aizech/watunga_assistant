# Imports
import json
import streamlit as st
import time
from openai import OpenAI
from dotenv import load_dotenv
import os

# load .env
load_dotenv()

# Fetching variables from the environment
openai_key = os.getenv("OPENAI_API_KEY")
base_path = os.getenv("BASE_PATH")
default_temperature = float(os.getenv("DEFAULT_TEMPERATURE"))
title = os.getenv("TITLE")
logo = os.getenv("LOGO")
default_model = os.getenv("DEFAULT_MODEL")
avatar_assistant = os.getenv("AVATAR_ASSISTANT")
avatar_user = os.getenv("AVATAR_USER")
vectorstore_id = os.getenv("VECTORSTORE_ID")

# Read instructions.md for assistant
instruction_text = open("instructions.md").read()

# Initialization
if "loaded" not in st.session_state:
    st.session_state["client"] = OpenAI(api_key=openai_key)
    st.session_state["assistant"] = st.session_state["client"].beta.assistants.create(
        name=title,
        model=default_model,
        instructions=instruction_text,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vectorstore_id]}}
    )
    st.session_state["assistant_thread"] = st.session_state["client"].beta.threads.create()

    # Load models configuration
    with open(f"{base_path}/aimodels.json", "r") as file:
        st.session_state["models"] = json.load(file)

    # Initialize session state variables
    st.session_state["messages"] = []
    st.session_state["prompt_tokens"] = 0
    st.session_state["completion_tokens"] = 0
    st.session_state["costs"] = 0
    st.session_state["loaded"] = True

# User Interface Setup
st.set_page_config(page_title=title)
if logo:
    st.image(f"{base_path}/{logo}", width=200)
st.title(title)

query = st.chat_input("Enter your question/prompt:")

# Sidebar for settings and debugging
st.sidebar.title("Settings & Debugging")
st.sidebar.header("Settings")

choice_model = st.sidebar.selectbox("Model", options=list(st.session_state["models"].keys()), index=0)
choice_temp = st.sidebar.slider("Temperature", value=default_temperature, min_value=0.0, max_value=2.0, step=0.1)
instruction_text = st.sidebar.text_area(label="System Message", value=instruction_text)

st.sidebar.divider()
st.sidebar.header("Debugging")
debug = st.sidebar.checkbox("Debug Mode", value=False)

# Helper function to calculate costs
def calculate_costs(tokens_prompt: int, tokens_completion: int, model: str) -> float:
    model_info = st.session_state["models"][model]
    price_prompt = model_info["input"]["price"] / model_info["input"]["tokens"]
    price_completion = model_info["output"]["price"] / model_info["output"]["tokens"]
    return (tokens_prompt * price_prompt + tokens_completion * price_completion)

# Display chat history
for m in st.session_state["messages"]:
    avatar = None
    if m["role"] == "user" and avatar_user:
        avatar = f"{base_path}/{avatar_user}"
    elif m["role"] == "assistant" and avatar_assistant:
        avatar = f"{base_path}/{avatar_assistant}"
    with st.chat_message(name=m["role"], avatar=avatar):
        st.write(m["content"])

# Event handler for new queries
if query:
    with st.chat_message(name="user", avatar=f"{base_path}/{avatar_user}"):
        st.write(query)
    
    status = st.status("Fetching response...", expanded=False)

    msg = st.session_state["client"].beta.threads.messages.create(
        st.session_state["assistant_thread"].id,
        role="user",
        content=query
    )
    assistant_run = st.session_state["client"].beta.threads.runs.create(
        thread_id=st.session_state["assistant_thread"].id,
        assistant_id=st.session_state["assistant"].id,
        model=choice_model,
        temperature=choice_temp,
        stream=False
    )

    assistant_run_retrieved = st.session_state["client"].beta.threads.runs.retrieve(
        thread_id=st.session_state["assistant_thread"].id,
        run_id=assistant_run.id
    )

    while assistant_run_retrieved.status not in ["cancelled", "failed", "expired", "completed"]:
        time.sleep(0.5)
        assistant_run_retrieved = st.session_state["client"].beta.threads.runs.retrieve(
            thread_id=st.session_state["assistant_thread"].id,
            run_id=assistant_run.id
        )

    status.update(label="Complete", state="complete", expanded=False)

    if assistant_run_retrieved.status == "completed":
        result = st.session_state["client"].beta.threads.messages.list(
            thread_id=st.session_state["assistant_thread"].id
        )
        answer = result.data[0].content[0].text.value

        with st.chat_message(name="assistant", avatar=f"{base_path}/{avatar_assistant}"):
            st.write(answer)

        st.session_state["messages"].append({"role": "user", "content": query, "tokens": assistant_run_retrieved.usage.prompt_tokens})
        st.session_state["messages"].append({"role": "assistant", "content": answer, "tokens": assistant_run_retrieved.usage.completion_tokens})
        st.session_state["prompt_tokens"] += assistant_run_retrieved.usage.prompt_tokens
        st.session_state["completion_tokens"] += assistant_run_retrieved.usage.completion_tokens
        costs = calculate_costs(assistant_run_retrieved.usage.prompt_tokens, assistant_run_retrieved.usage.completion_tokens, choice_model)
        st.session_state["costs"] += costs


        if debug:
            st.sidebar.subheader("Usage")
            st.sidebar.write("Prompt Tokens (last prompt):", assistant_run_retrieved.usage.prompt_tokens)
            st.sidebar.write("Completion Tokens (last prompt):", assistant_run_retrieved.usage.completion_tokens)
            st.sidebar.write("Total Tokens (last prompt):", assistant_run_retrieved.usage.total_tokens)
            st.sidebar.write("Prompt Tokens (total session):", st.session_state["prompt_tokens"])
            st.sidebar.write("Completion Tokens (total session):", st.session_state["completion_tokens"])
            st.sidebar.write("Total Tokens (total session):", st.session_state["prompt_tokens"] + st.session_state["completion_tokens"])
            st.sidebar.subheader("Costs")
            st.sidebar.write("Cost (last prompt, estimated):", costs)
            st.sidebar.write("Cost (total session, estimated):", st.session_state["costs"])

            st.sidebar.subheader("Assistant API Run")
            st.sidebar.write(assistant_run_retrieved)

            st.sidebar.subheader("Assistant API Messages")
            
            # Check if result is formatted as expected
            if hasattr(result, 'data') and isinstance(result.data, list):
                for message in result.data:
                    st.sidebar.write(message.content)  # Adjust based on actual structure
            else:
                st.sidebar.write("Unexpected result format:", result)
