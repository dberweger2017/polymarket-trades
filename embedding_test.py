from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

response = client.embeddings.create(
    model="text-embedding-3",
    input=["What is the capital of France?"]
)
vector = response['data'][0]['embedding']