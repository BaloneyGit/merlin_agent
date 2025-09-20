import time
import re
from playwright.sync_api import sync_playwright, Playwright
from typing import Annotated, Sequence, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

load_dotenv()

class merlin_interact:
    def __init__(self):
        """constructor playwright, open browser, go to website"""
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch() # for chrome browser
        self.page = self.browser.new_page()
        self.page.goto("https://hackmerlin.io/")

    @tool # TODO: might need to change these decorators
    def ask_merlin(self, question: str):
        """ask merlin the question by entering question text in the texbox and click the submit button"""
        ask_loc = self.page.get_by_placeholder('You can talk to merlin here...')
        print(f'question asked to merlin: {question}')
        ask_loc.fill(question)

        self.page.get_by_role("button", name=re.compile("ask", re.IGNORECASE)).click() 

    @tool
    def read_merlin(self):
        """read merlin's response"""
        read_loc = self.page.locator("blockquote.mantine-Blockquote-root")
        merlin_reply = read_loc.inner_text().strip()
        print(f"{merlin_reply}")
        return merlin_reply 

    @tool
    def submit_password(self, password: str) -> dict: # TODO: should the tool function returns state, or should the toolnode return state
        """enter the password text in the textbox, click the submit button, check if the password is bad (did not work, False)"""
        # enter password text
        pwd_loc = self.page.get_by_placeholder("SECRET PASSWORD")
        pwd_loc.fill(password)

        # click submit button
        self.page.get_by_role("button", name=re.compile("submit", re.IGNORECASE)).click()

        # check if password is good/bad
        secret_pwd = self.page.locator(".mantine-Notification-title").inner_text()
        if secret_pwd == "Bad secret word":
            print("password is bad!!")
            return {"success": False} # TODO: possible error
        else:
            print("password is good, Level passed..")
            return {"success": True} # TODO: possible error

# agent = merlin_interact()

# agent.read_merlin()
# agent.ask_merlin('what is your name?') # TODO: need few secs after this before doing read_merlin(), possible error can appear here
# time.sleep(2)

# agent.read_merlin()

# agent.submit_password('Merlin')
# time.sleep(2)

conversation_history = []

tools = [merlin_interact.ask_merlin, merlin_interact.read_merlin, merlin_interact.submit_password]

model = ChatOpenAI(model="gpt-4o",temperature=0).bind_tools(tools)

# AgentState
class AgentState(TypedDict):
    # convtn : Annotated[Sequence[BaseMessage], add_messages]
    convtn: list
    # question: BaseMessage # str: Agent to Tool
    # answer: ToolMessage # str: Tool to Agent
    # password: BaseMessage # str: Agent to Tool
    success: bool # bool: Tool to Agent
    level: int

# descriptor functions for each node

## Agent node descriptor
def model_call(state: AgentState) -> AgentState: # TODO: try to keep same
    system_prompt = SystemMessage(content=
                  "You are a reasoning agent who is very clever and solves puzzles extremely effectively. " \
                  "Your job is to ask Merlin questions, read Merlin's response and guess the password. Please talk to Merlin starting with a question..."
    )
    response = model.invoke([system_prompt] + state["convtn"])
    return {"convtn" = [response]}

## conditional edge descriptor # TODO: will be changed
def should_continue(state: AgentState):
    convtn = state["convtn"]
    last_msg = convtn[-1]
    if state["level"] <= 7:
        if last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc["name"] == "submit_password":
                    if state["success"]:
                        state["level"]+=1
        return "continue"
    else:
        return "end"

# connect all nodes etc
graph = StateGraph(AgentState)
graph.add_node("puzzle_agent", model_call)

tool_node = ToolNode(tools=tools)
graph.add_node("tools", tool_node)

graph.add_edge("puzzle_agent", "tools")





# conversation history

# graph compile

# run




    