import re
import json
import uuid
from playwright.sync_api import sync_playwright, Playwright
from playwright.sync_api import TimeoutError as PWTimeout
from typing import Annotated, Sequence, TypedDict, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from functools import partial
from langchain_core.tools import tool, Tool
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pathlib import Path


load_dotenv()

class merlin_interact:
    def __init__(self):
        """constructor playwright, open browser, go to website"""
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch() # chrome
        self.page = self.browser.new_page()
        self.page.goto("https://hackmerlin.io/")

    def ask_merlin(self, question: str) -> dict:
        """ask merlin the question by entering question text in the texbox and click the submit button"""
        ask_loc = self.page.get_by_placeholder('You can talk to merlin here...')
        print(f'question asked to merlin: {question}')
        ask_loc.fill(question)

        self.page.get_by_role("button", name=re.compile("ask", re.IGNORECASE)).click()
        return {"status": "OK", "question": question} 

    def read_merlin(self) -> str: # TODO: reading entire blockquote rn, change if errors: only has -Merlin or node not ready yet
        """read merlin's response"""
        timeout_ms = 5000

        try:
            read_loc = self.page.locator("blockquote.mantine-Blockquote-root")
            read_loc.wait_for(state="visible", timeout=timeout_ms) # waiting until reply exists

            merlin_reply = read_loc.inner_text().strip()
            print(f"{merlin_reply}")
            return merlin_reply
        except PWTimeout:
            print("Timeout reading merlin's reply")
            return "timeout_error"
        except Exception as e:
            print(f"Error reading Merlin: {e}")
            return f"Read Error: {str(e)}"

    def submit_password(self, password: str) -> dict:
        """enter the password text in the textbox, click the submit button, check if the password is bad (did not work, False)"""
        timeout_ms = 1500
        # enter password text
        pwd_loc = self.page.get_by_placeholder("SECRET PASSWORD")
        pwd_loc.fill(password.upper())

        # click submit button
        self.page.get_by_role("button", name=re.compile("submit", re.IGNORECASE)).click()

        # check if password is good/bad
        secret_pwd_notif = self.page.locator(".mantine-Notification-title")
        try:
            # wait for notif until timeout
            secret_pwd_notif.wait_for(state="visible", timeout=timeout_ms)
            msg = secret_pwd_notif.inner_text().strip()
            return {"success": False, "message": msg}
        except PWTimeout:
            # if not notif, success # TODO: maybe verify with another success signal (eg: Level text change)
            return {"success": True}
        
        
def build_tools(merlin: merlin_interact):
    return [
        Tool.from_function(func=merlin.ask_merlin, 
                           name="ask_merlin", 
                           description="ask merlin the question by entering question text in the texbox and click the submit button"),
        Tool.from_function(func=merlin.read_merlin,
                           name="read_merlin",
                           description="read merlin's response"),
        Tool.from_function(func=merlin.submit_password,
                           name="submit_password",
                           description="enter the password text in the textbox, click the submit button, check if the password is bad (did not work, False)")
    ]


merlin = merlin_interact()
tools = build_tools(merlin)

model = ChatOpenAI(model="gpt-4o",temperature=0).bind_tools(tools, tool_choice="required", parallel_tool_calls=False)


# AgentState
class AgentState(TypedDict):
    messages : Annotated[Sequence[BaseMessage], add_messages]
    level: int # current level
    last_reply: Optional[str] # merlin's last reply
    success: Optional[bool] # password correct/wrong
    last_tool_name: Optional[str] # last tool used by tools node
    last_tool_result: Optional[dict] # result of last tool used by tools node


# descriptor functions for each node

## Agent node descriptor
def model_call(state: AgentState) -> dict:
    system_prompt = SystemMessage(content=
                  "You are a reasoning agent who is very clever and solves puzzles extremely effectively. " \
                  "You are solving Merlin's riddle levels."
                  "You must interact with Merlin ONLY via tools: ask_merlin(question), read_merlin(), submit_password(password). " \
                  "Never produce plain assistant text." \
                  "Make sure you use a read_merlin() after doing an ask_merlin()"
    )
    msgs = [system_prompt] + list(state["messages"])
    response = model.invoke(msgs)

    # guarantees tool call if agent fails 
    if not getattr(response, "tool_calls", None): # TODO: possible error: missing tool call id, inject if raised
        response = AIMessage(
            content="",
            tool_calls=[{"name": "ask_merlin", "args": {"question": "Does the password contain the letter 'e'?"}}]
        ) 
    return {"messages": [response]}

## post tool router descriptor function
def handle_tool_result(state: AgentState):
    updates = {}
    msg = state["messages"]
    last_msg = msg[-1]

    if isinstance(last_msg, ToolMessage):
        # get last tool used
        updates["last_tool_name"] = last_msg.name

        # get last tool result and ToolMessage handling (returns dict|str)
        raw = last_msg.content
        parsed = None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
        else:
            parsed = raw

        updates["last_tool_result"] = parsed

        # get last merlin reply or get password success [also respective ToolMessage handling (returns dict|str)]
        if last_msg.name == "read_merlin":
            if isinstance(parsed, str):
                updates["last_reply"] = parsed.strip()
        elif last_msg.name == "submit_password":
            if isinstance(parsed, dict):
                updates["success"] = bool(parsed.get("success", False))
                if updates["success"]:
                    updates["level"] = state["level"] + 1
        
    return updates

## conditional edge descriptor function: router node to agent node, router to force_read, router to end
def route_after_tool(state: AgentState):
    if state.get("last_tool_name") == "submit_password":
        return "end" if state.get("success") else "continue" # if password correct, end else continue
    if state.get("last_tool_name") == "ask_merlin":
        return "force_read" # route to read tool right after ask
    return "continue" # if last_tool not submit_password, agent continues

## force_read descriptor function
def force_read_node(state: AgentState) -> dict:
    # agent to read_merlin tool call
    ai = AIMessage(
        content="",
        tool_calls=[{
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "name": "read_merlin",
            "args": {}
        }]
    )
    return {"messages": [ai]}


g = StateGraph(AgentState)

g.add_node("agent", model_call)

tool_node = ToolNode(tools=tools)
g.add_node("tools", tool_node)

g.add_node("post_tool_router", handle_tool_result)

g.add_node("force_read_node", force_read_node)

g.add_edge(START, "agent")
g.add_edge("agent", "tools")
g.add_edge("tools", "post_tool_router")
g.add_conditional_edges("post_tool_router", route_after_tool, 
                        {
                            "continue": "agent",
                            "force_read": "force_read_node", 
                            "end": END
                        })
g.add_edge("force_read_node", "tools")


# performance improvement: from conversation history, truncate earliest few from messages (eg: if messages length > 10)

# graph compile
graph = g.compile()

# run
state = {"messages": [], "level": 1, "last_reply": None, "success": None,
         "last_tool_name": None, "last_tool_result": None}
final_state = graph.invoke(state, config={"recursion_limit": 30})
print(final_state)




    