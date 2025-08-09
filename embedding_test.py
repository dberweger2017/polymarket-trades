import voyageai
import os
from dotenv import load_dotenv

load_dotenv()

vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

result = vo.embed(["hello world"], model="voyage-3.5")

print(result.embeddings)