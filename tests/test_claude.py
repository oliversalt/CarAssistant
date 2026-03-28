from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()

transcript = "Whats in the news today?" # Replace with actual transcript from Whisper 

print("Sending to Claude...")

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=256,
    system="You are a helpful car assistant. Keep responses concise and conversational. No markdown, no bullet points. Speak naturally as if talking to someone driving.",
    messages=[
        {"role": "user", "content": transcript}
    ]
)

print("Response:", response.content[0].text)