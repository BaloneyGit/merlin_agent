# import playwright
import time
import re
from playwright.sync_api import sync_playwright, Playwright


class merlin_interact:
    def __init__(self):
        # chromium = playwright.chromium # chromium, firefox, other browsers
        # browser = chromium.launch()
        # page = browser.new_page()
        # page.goto("https://hackmerlin.io/")
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch() # for chrome browser
        self.page = self.browser.new_page()
        self.page.goto("https://hackmerlin.io/")

    def ask_merlin(self, question: str):
        """enter question text in the texbox and click the submit button"""
        ask_loc = self.page.get_by_placeholder('You can talk to merlin here...')
        print(f'question asked to merlin: {question}')
        ask_loc.fill(question)

        self.page.get_by_role("button", name=re.compile("ask", re.IGNORECASE)).click() 

    def read_merlin(self):
        """read merlin's response"""
        read_loc = self.page.locator("blockquote.mantine-Blockquote-root")
        merlin_reply = read_loc.inner_text().strip()
        print(f"{merlin_reply}") 

    def submit_password(self, password: str) -> bool:
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
            return False
        else:
            return True

agent = merlin_interact()

agent.read_merlin()
agent.ask_merlin('what is your name?') # need few secs after this before doing read_merlin()
time.sleep(2)

agent.read_merlin()

agent.submit_password('Merlin')
time.sleep(2)


    