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
CORS(app, resources={r"/*": {"origins": "https://server-service-956338125937.africa-south1.run.app"}}, supports_credentials=True)

@app.route('/get-product-suggestions', methods=['POST', 'OPTIONS'])
def get_product_suggestions():
    if request.method == 'OPTIONS':
        # Reply to preflight request directly
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'https://server-service-956338125937.africa-south1.run.app')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 200
    try:
        data = request.get_json()
        print("📥 Received payload:", data)

        icd10_list = data.get("icd10", [])
        if not icd10_list:
            return jsonify({"error": "Missing ICD10 list"}), 400

        query_text = "\n".join([f"Diagnosis: {code}" for code in icd10_list])

        embedding_response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=query_text
        )
        query_embedding = np.array(embedding_response.data[0].embedding).astype("float32")

        D, I = index.search(np.array([query_embedding]), k=10)
        top_matches = [metadata[i] for i in I[0]]

        grouped_products = []
        for product in top_matches:
            matched_icd = []
            pname = product["name"].lower()
            for icd in icd10_list:
                if any(word in pname for word in icd.lower().split()):
                    matched_icd.append(icd)
            grouped_products.append({**product, "icd10": ", ".join(matched_icd or ["Other"])})

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

    except Exception as e:
        print("🔥 Error in /get-product-suggestions:", str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/symptom-checker', methods=['POST'])
def symptom_checker():
    data = request.get_json()
    user_message = data.get("message")

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful and knowledgeable medical assistant. Provide accurate, clear, and safe advice based on the symptoms described by the user. Be friendly and professional. Be empathetic and humane in your replies."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=300
        )
        ai_reply = response.choices[0].message.content.strip()
        return jsonify({"response": ai_reply})
    except Exception as e:
        print("AI error in symptom-checker:", e)
        return jsonify({"response": "Sorry, something went wrong while trying to help."})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
