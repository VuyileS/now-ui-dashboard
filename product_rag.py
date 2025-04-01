from flask import Flask, request, jsonify
from flask_cors import CORS
import faiss
import json
import numpy as np
from collections import defaultdict
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load metadata
with open("dischem_metadata.json") as f:
    metadata = json.load(f)

# Load FAISS index
index = faiss.read_index("dischem_faiss.index")

app = Flask(__name__)
CORS(app)

@app.route('/get-product-suggestions', methods=['POST'])
def get_product_suggestions():
    data = request.get_json()
    icd10_list = data.get("icd10", [])

    if not icd10_list:
        return jsonify({"error": "Missing ICD10 list"}), 400

    query_text = "\n".join([f"Diagnosis: {code}" for code in icd10_list])

    # Embed query
    embedding_response = client.embeddings.create(
        model="text-embedding-ada-002",
        input=query_text
    )
    query_embedding = np.array(embedding_response.data[0].embedding).astype("float32")

    # Search FAISS
    D, I = index.search(np.array([query_embedding]), k=10)
    top_matches = [metadata[i] for i in I[0]]

    # Match to ICD10s (basic keyword match)
    grouped_products = []
    for product in top_matches:
        matched_icd = []
        pname = product["name"].lower()
        for icd in icd10_list:
            if any(word in pname for word in icd.lower().split()):
                matched_icd.append(icd)
        grouped_products.append({**product, "icd10": ", ".join(matched_icd or ["Other"])})

    # AI justification
    product_text = "\n".join([
        f"{p['name']} - {p['price']} ({p['url']})"
        for p in grouped_products
    ])
    prompt = f"""
    You are a pharmacy assistant. Recommend relevant Dis-Chem products for these diagnoses:

    Diagnoses:
    {query_text}

    Dis-Chem Products:
    {product_text}

    Return your reasoning and a few suggestions in a structured and readable way, do use bullets or numbering in your summaries while separating them with line spaces.
    Furthermore, should there be no products for the diagnoses, please use your medical knowledge to make suggestions but make them clear that they are your general suggestions.
    """

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=500
    )

    return jsonify({
        "recommendations": response.choices[0].message.content.strip(),
        "products": grouped_products
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
