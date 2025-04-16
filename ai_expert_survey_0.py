import io
import random
import wave

import openai
import pandas as pd
import streamlit as st
import supabase
from supabase import create_client
from collections import Counter

# GLOBAL VARS
NUM_EXPERTS = 12
RESPONSES_PER_TASK = 2
NO_DATA_NEEDED_PAGE_NUM = 100
NO_OCCUPATION_MATCH_PAGE_NUM = 101

# SET OPEN AI TOKEN
openai.api_key = st.secrets['OPENAI_KEY']
model_name = "gpt-4o"
openai_client = openai.OpenAI(api_key=st.secrets['OPENAI_KEY'])

# SET UP DB CONNECTION
if st.secrets['MODE'] == 'dev':
    supabase_client = create_client(
        st.secrets['SUPABASE_DEV_URL'],
        st.secrets['SUPABASE_DEV_KEY'],
    )
elif st.secrets['MODE'] == 'prod':
    supabase_client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )
elif st.secrets['MODE'] == 'expert':
    supabase_client = create_client(
        st.secrets["SUPABASE_EXPERT_URL"],
        st.secrets["SUPABASE_EXPERT_KEY"],
    )
else:
    raise ValueError("Invalid mode. Please set the mode to 'dev', 'prod' or 'expert' in the secrets.toml file.")

# LOAD the O*NET Task Dataset
task_data = pd.read_csv("expert_task_0_ratings.csv")
title_list = task_data['Title'].drop_duplicates().values.tolist()
industry_to_title_table = pd.read_csv("updated_occupation_categories.csv")
occupation_descriptions = pd.read_csv("gpt_occupation_descriptions.csv")
task_descriptions = pd.read_csv("gpt_task_descriptions.csv")

# RETRIEVE OCCUPATION INFO
# retrieve list of industries
industry_list = industry_to_title_table['Industry'].drop_duplicates().tolist()
industry_list.append('Other')

all_tasks_list = task_data['Task'].to_list()
NUM_TASKS_TO_RANK = 100



def save_all_data_to_db():
    save_task_response_to_db()
    print("All responses successfully saved.")


def save_skipped_task_to_db(task_name):
    if 'user_id' not in st.session_state:
        st.error("User ID not found in session state.")
        return False
    
    response = (
        supabase_client.table("task_ratings")
        .insert({
            "user_id": st.session_state['user_id'],
            'task': task_name,
            'automation_capacity': None,
            'physical_actions': None,
            'uncertainty': None,
            'domain_expertise': None,
            'empathy': None,
            'collaboration': None,
        })
    .execute()
    )

    # Check if the response contains data (successful insert)
    if response and hasattr(response, 'data') and len(response.data) > 0:
        print(f"Skipped task response successfully saved")
        return True
    else:
        print(f"Failed to save skipped task response")
        st.error("Failed to save your response. Please try again.")
        return False
    


def save_task_response_to_db(task_response):
    if 'user_id' not in st.session_state:
        st.error("User ID not found in session state.")
        return False

    task = task_response['task']
    response = (
        supabase_client.table("task_ratings")
        .insert({
            "user_id": st.session_state['user_id'],
            'task': task_response['task'],
            'automation_capacity': int(task_response['automation_capacity'].split(":")[0]),
            'physical_actions': int(task_response['physical_actions'].split(":")[0]),
            'uncertainty': int(task_response['uncertainty'].split(":")[0]),
            'domain_expertise': int(task_response['domain_expertise'].split(":")[0]),
            'empathy': int(task_response['empathy'].split(":")[0]),
            'collaboration': int(task_response['collaboration'].split(":")[0])
        })
    .execute()
    )

    # Check if the response contains data (successful insert)
    if response and hasattr(response, 'data') and len(response.data) > 0:
        print(f"Task response successfully saved: {task_response['task']}")
        return True
    else:
        print(f"Failed to save task response: {task_response['task']}")
        st.error("Failed to save your response. Please try again.")
        return False



# Initialize session state for page tracking if not done already
if 'page' not in st.session_state:
    st.session_state['page'] = 0  # Start at the introduction page

def fetch_user_progress():
    # this function returns the next task index to include
    user_id = st.session_state.user_id
    response = supabase_client.table('task_ratings').select('task').eq('user_id', user_id).execute()
    print(response)
    if len(response.data) == NUM_TASKS_TO_RANK:
        st.session_state.page += 1
        st.rerun()
    else:
        tasks_completed = [row['task'] for row in response.data]
        print(tasks_completed)
        return tasks_completed


def get_task_list():

    all_tasks_list = task_data['Task'].to_list()
    id = st.session_state.user_id
    tasks_completed = st.session_state.completed_tasks

    # 0 is for testing
    # note: NUM_TASKS_TO_RANK is 320
    id_to_indices = {'test': (0, NUM_TASKS_TO_RANK), '1a': (0, NUM_TASKS_TO_RANK),
                     '1b': (0, NUM_TASKS_TO_RANK),
                     '2a': (NUM_TASKS_TO_RANK, NUM_TASKS_TO_RANK * 2),
                     '2b': (NUM_TASKS_TO_RANK, NUM_TASKS_TO_RANK * 2),
                     '3a': (NUM_TASKS_TO_RANK * 2, NUM_TASKS_TO_RANK * 3),
                     '3b': (NUM_TASKS_TO_RANK * 2, NUM_TASKS_TO_RANK * 3),
                     '4a': (NUM_TASKS_TO_RANK * 3, NUM_TASKS_TO_RANK * 4),
                     '4b': (NUM_TASKS_TO_RANK * 3, NUM_TASKS_TO_RANK * 4),
                     '5a': (NUM_TASKS_TO_RANK * 4, NUM_TASKS_TO_RANK * 5),
                     '5b': (NUM_TASKS_TO_RANK * 4, NUM_TASKS_TO_RANK * 5),
                     # 120 workflows
                     '6a': (NUM_TASKS_TO_RANK * 5, len(all_tasks_list)),
                     '6b': (NUM_TASKS_TO_RANK * 5, len(all_tasks_list))}

    start_index, end_index = id_to_indices[id]
    all_tasks = set(all_tasks_list[start_index:end_index])
    for done_task in tasks_completed:
        all_tasks.remove(done_task)
    tasks_remaining = list(all_tasks)
    return tasks_remaining


def next_page():
    st.session_state['page'] += 1
    st.rerun()

def previous_page():
    st.session_state['page'] -= 1
    st.rerun()


def consent_page():
    st.header("Share your thoughts on AI assistance in your work!")
    st.markdown("<p style='font-size:20px'>"
                "Thank you for considering participating in our study! <strong>We are researchers from "
                "Stanford University studying Artificial Intelligence</strong>, and your insights are invaluable "
                "to us. By sharing your unique thoughts, you’ll help us better understand how to develop AI agents "
                "that effectively support human work.</p>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:20px'>⌛ In this survey, we will show you about 300 tasks and ask a few questions about each one."
                "You can stop and restart at any time, and the survey will save your progress. This survey will take approximately 4 hours,"
                "and please complete it by the end of April.</p>",
                unsafe_allow_html=True)
    st.markdown("<p style='font-size:20px'>🔒 This study is not affiliated with any companies or government agencies, "
                "and your responses will be kept fully anonymous and confidential. It has been approved by "
                "the Stanford University IRB. You can review the study consent form <a href="
                "\"https://docs.google.com/document/d/15Zg7tcMWPQS8Z9EgTpe59maVzEeLmQDk/edit?usp=sharing&ouid=106436329658557310217&rtpof=true&sd=true\">"
                "here</a>.</p>", unsafe_allow_html=True)

    st.markdown(
        """
        <style>
        .stButton > button {
            font-size: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    if st.button("I am at least 18 years old and I agree to participate in this study."):
        next_page()


def task_transition_page():

    st.subheader("What is your user id?")
    user_id = st.text_input("Please enter here:")
    st.session_state['user_id'] = user_id

    st.header("Introduction", divider=True)

    st.markdown("""

        <p style='font-size:18px;'> An artificial intelligence (AI) agent refers to a system or program that is capable of autonomously performing certain tasks on behalf of a user or another system by designing its workflow and utilizing available tools (IBM).

        <p style='font-size:18px;'> Next, we will show you a series of tasks performed by different occupations. Please answer the following questions about how much current AI systems can assist with the following tasks. 
        
        <p style='font-size:18px;'> We provide a summary of the occupation and task, but feel free to use Google search if you need more information. Ready to start?

        """, unsafe_allow_html=True)

    if st.button("Let's go!"):
        if user_id:
            # Initialize session state for tracking tasks and answers
            st.session_state.task_page = 0  # Track task index (for the survey)
            st.session_state.completed_tasks = fetch_user_progress()
            st.session_state.selected_tasks = get_task_list()
            next_page()
        else:
            st.error("Please enter your user id.")


def task_survey():

    if 'task_responses' not in st.session_state:
        st.session_state['task_responses'] = []

    if 'completed_tasks' not in st.session_state:
        st.session_state.completed_tasks = fetch_user_progress()

    # Check if the user has completed enough familiar tasks
    if st.session_state.task_page < len(st.session_state.selected_tasks):
        progress = st.session_state.task_page / len(st.session_state.selected_tasks)
        print(len(st.session_state.selected_tasks))
        st.progress(progress, f"Progress:{st.session_state.task_page}/{len(st.session_state.selected_tasks)}")


        # Get the current task
        current_task = st.session_state.selected_tasks[st.session_state.task_page]
        relevant_title = task_data.loc[task_data['Task'] == current_task]['Title'].tolist()[0]
        # Show the current task
        st.subheader(f"Task: {current_task}")
        st.write(f"This belongs to the occupation: **{relevant_title}**")

        st.write("If this task is a conflict of interest for you, you can skip:")
        skip = st.button("Skip")
        if skip:
            saved = save_skipped_task_to_db(current_task)
            if saved:
                st.success("Task response successfully saved.")
                st.session_state.completed_tasks.append(current_task)
                st.session_state.task_page += 1
                st.rerun()
            else:
                st.error("Task response not saved. Please click 'Skip' again.")
        
        st.divider()
        st.subheader("Occupation and Task Summaries")
        # retrieve occupation summary
        occ_description = occupation_descriptions.loc[occupation_descriptions['Title'] == relevant_title]['Description'].tolist()[0]
        task_description = task_descriptions.loc[task_descriptions['Task'] == current_task]['Description'].tolist()[0]

        with st.expander(f"Occupation Description", expanded=False):
            st.write(f"This task is performed by **{relevant_title}**. To assist you, here is their job description:")
            st.write(occ_description)

        with st.expander(f"Task Description", expanded=False):
            st.write(task_description)


        st.divider()
        st.subheader("Task Questions")
        st.markdown(
            """
            <style>
            p {
                font-size: 18px !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        task_physical_actions = st.select_slider(
        label="""**To what extent does this task require physical actions or manual labor that cannot be performed on a computer? (1 - 5 scale)** \\
            *Recall that digital AI agents can only complete actions on a computer. For example, an AI could run software and draft emails, but could not operate machinery, handle physical objects, or interact with the physical environment.*
            """,
        options=[
            "Not selected",
            "1: Not at all",
            "2: Slightly",
            "3: Moderately",
            "4: A lot",
            "5: Entirely",
        ],
        value="Not selected",
        key=f"{st.session_state.task_page}_physical_actions",
        )

        task_uncertainty_decisions = st.select_slider(
            label="**How much does this task require dealing with uncertainty or making high-stake decisions? (1 - 5 scale)**",
            options=[
                "Not selected",
                "1: Not at all",
                "2: Slightly",
                "3: Moderately",
                "4: A lot",
                "5: Entirely",
            ],
            value="Not selected",
            key=f"{st.session_state.task_page}_uncertainty_decisions",
        )

        task_domain_expertise = st.select_slider(
            label="**How much does this task require specific domain expertise (such as specialized knowledge, unspoken wisdom, or insights gained through experience)? (1 - 5 scale)**",
            options=[
                "Not selected",
                "1: Not at all",
                "2: Slightly",
                "3: Moderately",
                "4: A lot",
                "5: Entirely",
            ],
            value="Not selected",
            key=f"{st.session_state.task_page}_domain_expertise",
        )

        task_interpersonal_empathy = st.select_slider(
            label="""**How much does this task depend on interpersonal communication? (1 - 5 scale)** \\
            *Recall that digital AI agents can send online messages and use online communication tools, but can not replicate face-to-face interaction or meetings.*""",
            options=[
                "Not selected",
                "1: Not at all",
                "2: Slightly",
                "3: Moderately",
                "4: A lot",
                "5: Entirely",
            ],
            value="Not selected",
            key=f"{st.session_state.task_page}_interpersonal_empathy",
        )

        task_automation_capacity = st.select_slider(
            label="**To what extent do current AI systems support automating this task? (1 - 5 scale)**",
            options=[
                "Not selected",
                "1: Not at all",
                "2: Slightly",
                "3: Moderately",
                "4: A lot",
                "5: Entirely"],
            value="Not selected",
            key=f"{st.session_state.task_page}_automation_capacity"
        )

        st.markdown("**If current AI systems were to assist in this task, how much collaboration between the worker and AI would be needed to complete this task effectively? (1 - 5 scale)**")

        with st.expander("References of collaboration levels", expanded=False):
            st.markdown("""
Even though we envision the AI agent as highly competent, your collaboration may be needed due to task complexity, specialized expertise, or unclear task parameters. Use the references below to rate the collaboration level:
1. **No Collaboration Needed**
- **The AI agent can handle the task entirely on its own.** After describing the task, the AI agent can complete everything independently, with additional involvement from you unlikely to improve the outcome.
2. **Limited Collaboration Needed**
- **The AI agent needs your input at a few key points.** The task requires your feedback or actions at a few specific checkpoints during the task completion.
3. **Moderate Collaboration Needed**
- **You and the AI agent need to work as partners.** The AI agent and you need to combine your unique strengths at regular intervals, as neither can achieve optimal results alone.
4. **Considerable Collaboration Needed**
- **The AI agent needs your frequent involvement to succeed.** The AI agent must be frequently complemented by your expertise and actions to achieve desired outcomes.
5. **Essential Collaboration Needed**
- **The AI agent cannot function without your continuous collaboration.** The AI agent cannot proceed without your actions and expertise, though it can significantly enhance your performance on the task.""")

        st.image('Collaboration levels figure.png', width=800)

        task_collaboration = st.select_slider(label="**Please give your rating based on the references:**",
                                                options=(
                                                    "Not selected",
                                                    "1: No collaboration needed",
                                                    "2: Limited collaboration needed",
                                                    "3: Moderate collaboration needed",
                                                    "4: Considerable collaboration needed",
                                                    "5: Essential collaboration needed"
                                                ), value="Not selected",
                                                key=f"{st.session_state.task_page}_collaboration"
                                                )
            
        # When the user submits, process their response
        if st.button("Submit"):

            if "Not selected" not in task_automation_capacity and \
                "Not selected" not in task_physical_actions and \
                "Not selected" not in task_uncertainty_decisions and \
                "Not selected" not in task_domain_expertise and \
                "Not selected" not in task_interpersonal_empathy and \
                "Not selected" not in task_collaboration:

                task_response = {
                    'task': current_task,
                    'automation_capacity': task_automation_capacity,
                    'physical_actions': task_physical_actions,
                    'uncertainty': task_uncertainty_decisions,
                    'domain_expertise': task_domain_expertise,
                    'empathy': task_interpersonal_empathy,
                    'collaboration': task_collaboration
                }

                task_saved = save_task_response_to_db(task_response)
                if task_saved:
                    st.session_state['task_responses'].append(task_response)
                    print(task_response)
                    st.session_state.completed_tasks.append(current_task)
                    st.success("Your response to this task has been successfully saved.")
                    st.session_state.task_page += 1
                    st.rerun()
                else:
                    st.error("Your response was not saved. Please click 'Submit' again.")

            else:
                st.warning("Please fill out every question before submitting.")

    else:
        # Survey is complete
        st.subheader("Thank you for answering questions about those tasks!")
        if st.button("Continue"):
            next_page()  # Go to the next section



# Main page navigation logic
def main():
    if st.session_state['page'] == 0:
        consent_page()
    elif st.session_state['page'] == 1:
        task_transition_page()
    elif st.session_state['page'] == 2:
        task_survey()
    elif st.session_state['page'] == 3:
        # save_all_data_to_db()
        st.subheader("Thank you for your participation!")
    elif st.session_state['page'] == NO_DATA_NEEDED_PAGE_NUM:
        st.subheader("Sorry, we have already collected enough data for your occupation. Thanks for your interest!")
    elif st.session_state['page'] == NO_OCCUPATION_MATCH_PAGE_NUM:
        st.subheader("Sorry, we don't need data for your occupation. Thank you for your interest!")




# Run the app
main()
