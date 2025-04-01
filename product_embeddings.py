import json
import os
from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI
import faiss
import numpy as np

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load products
with open("dischem_products.json", "r") as f:
    products = json.load(f)

# Extract product names to embed
product_names = [p["name"] for p in products]

# Embed using OpenAI
def get_embeddings(texts):
    embeddings = []
    for i in range(0, len(texts), 10):  # batch of 10
        batch = texts[i:i+10]
        response = client.embeddings.create(
            input=batch,
            model="text-embedding-ada-002"
        )
        for item in response.data:
            embeddings.append(item.embedding)
    return embeddings

print("🔄 Generating embeddings...")
vectors = get_embeddings(product_names)

# Convert to numpy array
vector_array = np.array(vectors).astype("float32")

# Create FAISS index
index = faiss.IndexFlatL2(vector_array.shape[1])
index.add(vector_array)

# Save the FAISS index
faiss.write_index(index, "dischem_faiss.index")

# Save metadata separately
with open("dischem_metadata.json", "w") as f:
    json.dump(products, f, indent=2)

print("✅ FAISS index and metadata saved.")
