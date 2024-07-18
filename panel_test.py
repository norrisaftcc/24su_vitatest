import panel as pn
import autogen
import io
import openai
import os
import time
import asyncio
from autogen import ConversableAgent
import param

pn.extension(design="material")

# Snippet below changes background color
'''
pn.config.raw_css.append("""
body {
    background-color: #f1b825;
}
""")
'''

class FileUploader(param.Parameterized):
    file_input = pn.widgets.FileInput(accept='.py')
    file_content = param.String(default="No file uploaded yet")
    uploaded_content = None  # Class-level variable to store content

    def __init__(self, **params):
        super().__init__(**params)
        self.file_input.param.watch(self.upload_file, 'value')

    @param.depends('file_content')
    def view(self):
        return pn.pane.Markdown(f"```python\n{self.file_content}\n```")

    def upload_file(self, event):
        if self.file_input.value is not None:
            content = self.file_input.value.decode('utf-8')
            self.file_content = content
            FileUploader.uploaded_content = content  # Update the class-level variable
            # Print the file content (for debugging purposes)
            print("Uploaded file content:\n", FileUploader.uploaded_content)

# Create an instance of the FileUploader class
uploader = FileUploader()

#Create a button to send a "Debug this code" message to the chat
debug_button = pn.widgets.Button(name='Debug the uploaded code', button_type='primary')

#Function that sends message to chat interface when button is clicked
def send_message(event):
    message = "Debugging the uploaded code..."
    # Assuming you have a function or method to send messages to the chat interface
    chat_interface.send(message, user="Student", respond=True)

# Watch for button click event
debug_button.param.watch(send_message, 'clicks')


#Create a button to send an "Explain a concept" message to the chat
explain_button = pn.widgets.Button(name='Explain a concept', button_type='primary')

#Function that sends message to chat interface when button is clicked
def send_concept_message(event):
    message = "Enter a programming concept to learn more about"
    # Assuming you have a function or method to send messages to the chat interface
    chat_interface.send(message, user="Student", respond=True)

# Watch for button click event
explain_button.param.watch(send_concept_message, 'clicks')

# Create a Panel layout
left_column = pn.Column(
    "### Upload a Python (.py) File",
    uploader.file_input,
    uploader.view,
    debug_button,
    explain_button,
)

# Print the content outside the class and event handlers
# Note: This will only print once when the script is run, and not update with uploads
print("Content of the uploaded file (initially):", FileUploader.uploaded_content)

# END FILE UPLOAD COLUMN



# CHAT COLUMN

os.environ["AUTOGEN_USE_DOCKER"] = "False"

config_list = [
    {
        'model': 'gpt-4o',
        'api_key': "sk-KEYGOESHERE",
    }
    ]
gpt4_config = {"config_list": config_list, "temperature":0, "seed": 53}

input_future = None


# Create a custom agent class that allows human input
class MyConversableAgent(autogen.ConversableAgent):

    async def a_get_human_input(self, prompt: str) -> str:
        global input_future
        print('<Student Input>')  # or however you wish to display the prompt
        chat_interface.send(prompt, user="System", respond=False)
        # Create a new Future object for this input operation if none exists
        if input_future is None or input_future.done():
            input_future = asyncio.Future()

        # Wait for the callback to set a result on the future
        await input_future

        # Once the result is set, extract the value and reset the future for the next input operation
        input_value = input_future.result()
        input_future = None
        return input_value




user_proxy = MyConversableAgent(
   name="Student",
   is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("Done"),
   system_message="""A human student that is learning to code in Python. Interact with the corrector to discuss the plan to fix any errors in the code. \
    The plan to fix the errors in the code needs to be approved by this admin. 
   """,
   #Only say APPROVED in most cases, and say exit when nothing to be done further. Do not say others.
   code_execution_config=False,
   #default_auto_reply="Approved", 
   human_input_mode="ALWAYS",
   #llm_config=gpt4_config,
)


debugger = autogen.AssistantAgent(
    name="Debugger",
    human_input_mode="NEVER",
    llm_config=gpt4_config,
    system_message='''Debugger. You inspect Python code. You find any syntax errors in the code. \
You explain each error as simply as possible in plain English and what line the error occurs on. \
You don't write code.You never show the corrected code. 
''',
)

corrector = autogen.AssistantAgent(
    name="Corrector",
    human_input_mode="NEVER",
    system_message='''Corrector. Suggest a plan on to fix each syntax error. \
    Explain how to correct the error as simply as possible using non-technical jargon. \
    You never show the corrected code. However, you may show an example of similar code. Any code that you \
    provide must not be the corrected code to the code you were given. It can only be examples of the same \
    concept, but must use different content as to not give the student the corrected version of their code.
    Revise the plan based on feedback from Student until Student agrees that the correction has \
    successfully fixed their code. If Student does not agree that the correction is sufficient,
    work with the Student to suggest a different solution.
    ''',
    llm_config=gpt4_config,
)


groupchat = autogen.GroupChat(agents=[user_proxy, debugger, corrector], messages=[], max_round=20)
manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=gpt4_config)

avatar = {user_proxy.name:"👨‍💼", debugger.name:"👩‍💻", corrector.name:"🛠"}

def print_messages(recipient, messages, sender, config):

    print(f"Messages from: {sender.name} sent to: {recipient.name} | num messages: {len(messages)} | message: {messages[-1]}")

    content = messages[-1]['content']

    if all(key in messages[-1] for key in ['name']):
        chat_interface.send(content, user=messages[-1]['name'], avatar=avatar[messages[-1]['name']], respond=False)
    else:
        chat_interface.send(content, user=recipient.name, avatar=avatar[recipient.name], respond=False)
    
    return False, None  # required to ensure the agent communication flow continues

user_proxy.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
)

debugger.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
) 
corrector.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
) 


initiate_chat_task_created = False

async def delayed_initiate_chat(agent, recipient, message):

    global initiate_chat_task_created
    # Indicate that the task has been created
    initiate_chat_task_created = True

    # Wait for 2 seconds
    await asyncio.sleep(2)

    # Now initiate the chat
    await agent.a_initiate_chat(recipient, message=message)

async def callback(contents: str, user: str, instance: pn.chat.ChatInterface):
    
    global initiate_chat_task_created
    global input_future

    if not initiate_chat_task_created:
        asyncio.create_task(delayed_initiate_chat(user_proxy, manager, f"```python\n{FileUploader.uploaded_content}\n```"))

    else:
        if input_future and not input_future.done():
            input_future.set_result(contents)
        else:
            print("There is currently no input being awaited.")

chat_interface = pn.chat.ChatInterface(callback=callback)
chat_interface.send("What would you like to ask VITA?", user="System", respond=False)

# Create a layout with two columns
layout = pn.Row(left_column, chat_interface)

# Serve the panel
layout.servable()
