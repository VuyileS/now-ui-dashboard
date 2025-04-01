from flask import Flask, jsonify, render_template, request
from flask_cors import CORS, cross_origin
import snowflake.connector
import pandas as pd
import os
import json
import numpy as np
import faiss
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__, template_folder="examples")  # ✅ Ensures Flask serves HTML from /examples
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# Function to connect to Snowflake
def get_snowflake_connection():
    return snowflake.connector.connect(
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA")
    )

# ✅ Route for fetching general data
@app.route('/get-data', methods=['GET'])
def fetch_data():
    try:
        conn = get_snowflake_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ANALYTICS.PROD.DIM_CLINIC__PATIENT_VISIT_REPORT LIMIT 10")
        data = cur.fetchall()

        columns = [desc[0] for desc in cur.description]
        df = pd.DataFrame(data, columns=columns)

        # Convert timestamps to string
        df["CREATED_AT"] = df["CREATED_AT"].astype(str)

        # Replace NaN and None with an empty string
        df = df.fillna("")

        cur.close()
        conn.close()

        return jsonify(df.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Route for fetching referrals data
@app.route('/get-referrals', methods=['GET'])
def get_referrals():
    try:
        conn = get_snowflake_connection()
        cur = conn.cursor()

        # Get optional date filters
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        query = """
        SELECT
            REF.CONSULTATION_ID,
            REF.CREATED_AT,
            REF.DATA:letter::STRING                 AS REFERRAL_LETTER,
            PVR.AGE_CATEGORY,
            PVR.GENDER,
            PVR.REPEAT_PATIENT,
            REF.REFERRAL_CATEGORY,
            REF.REFERRAL_SECTOR,
            REF.REFERRAL_TYPE,
            REF.REFERRAL_SUBTYPE
        FROM ANALYTICS.PROD.STG_CLINIC__REFERRALS   REF
            LEFT JOIN ANALYTICS.PROD.DIM_CLINIC__PATIENT_VISIT_REPORT   PVR
                ON REF.CONSULTATION_ID = PVR.CONSULTATION_ID
        WHERE STATUS = 1
        """

        if start_date and end_date:
            query += f" AND CREATED_AT BETWEEN '{start_date}' AND '{end_date}'"

        cur.execute(query)
        data = cur.fetchall()

        columns = [desc[0] for desc in cur.description]
        df = pd.DataFrame(data, columns=columns)

        # Convert timestamps to string
        df["CREATED_AT"] = df["CREATED_AT"].astype(str)

        cur.close()
        conn.close()

        return jsonify(df.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Route to render the referrals page
# @app.route('/referrals')
# def referrals_page():
#     return render_template('referrals.html')
@app.route('/get-medication-refills', methods=['GET'])
def get_medication_refills():
    try:
        conn = get_snowflake_connection()
        cur = conn.cursor()

        query = """
        SELECT TOP 100
            CONSULTATION_ID,
            CREATED_AT,
            PRODUCT_NAME AS MEDICATION,
            MEDICATION_APPLICATION AS APPLICATION_FORM,
            MEDICATION_DOSAGE AS DOSAGE,
            TIMES_PER_DAY AS DOSAGE_TIMES_PER_DAY,
            DURATION_DAYS AS DURATION_IN_DAYS,
            CAST(DATEADD(day, DURATION_IN_DAYS, CURRENT_DATE) AS TIMESTAMP) AS REFILL_DATE
        FROM (
            SELECT
                CCP.CONSULTATION_ID,
                CCP.CREATED_AT,
                CPP.PRESCRIPTION_ID,
                CM.PRODUCT_NAME,
                CPP.MEDICATION_DATA:application::STRING AS MEDICATION_APPLICATION,
                CPP.MEDICATION_DATA:dosage::FLOAT AS MEDICATION_DOSAGE,
                CASE
                    WHEN CPP.MEDICATION_DATA:duration_measurement::STRING = 'week' THEN 7
                    WHEN CPP.MEDICATION_DATA:duration_measurement::STRING = 'day' THEN 1
                    WHEN CPP.MEDICATION_DATA:duration_measurement::STRING = 'month' THEN 30
                    ELSE NULL
                END AS MEDICATION_DURATION_MEASUREMENT,
                CPP.MEDICATION_DATA:duration::FLOAT * COALESCE(MEDICATION_DURATION_MEASUREMENT, 1) AS DURATION_DAYS,
                CASE
                    WHEN CPP.MEDICATION_DATA:frequency = 'od' THEN 1 -- Once daily
                    WHEN CPP.MEDICATION_DATA:frequency = 'bid' THEN 2 -- Twice daily
                    WHEN CPP.MEDICATION_DATA:frequency = 'tds' THEN 3 -- Three times daily
                    WHEN CPP.MEDICATION_DATA:frequency = 'qid' THEN 4 -- Four times daily
                    ELSE NULL
                END AS TIMES_PER_DAY
            FROM ANALYTICS.PROD.STG_CLINIC__CONSULTATION_PRESCRIPTION CCP
            LEFT JOIN ANALYTICS.PROD.STG_CLINIC__PRESCRIPTION_MEDICATIONS CPP ON CCP.ID = CPP.PRESCRIPTION_ID
            LEFT JOIN ANALYTICS.PROD.STG_CLINIC__MEDICATIONS CM ON CPP.MEDICATION_ID = CM.MEDICATION_ID
            WHERE CCP.PRESCRIPTION_CLINICIAN_TYPE = 'Doctor'
        ) AS DATA
        WHERE DATEDIFF(day, CREATED_AT, CURRENT_DATE) = 1
        """
        # query += " LIMIT 100"  # ✅ TEMPORARY: Only return 100 records for debugging

        cur.execute(query)
        data = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        df = pd.DataFrame(data, columns=columns)

        # ✅ Convert timestamps
        df["CREATED_AT"] = pd.to_datetime(df["CREATED_AT"]).astype(str)
        df["REFILL_DATE"] = pd.to_datetime(df["REFILL_DATE"]).astype(str)

        # ✅ Handle NaN values
        df = df.fillna(0)  # Replace NaN with 0 (or you can use .fillna("null") if needed)

        cur.close()
        conn.close()

        return jsonify(df.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# ✅ Route for fetching active clinic locations
@app.route('/get-clinic-locations', methods=['GET'])
def get_clinic_locations():
    try:
        conn = get_snowflake_connection()
        cur = conn.cursor()

        query = """
        SELECT
            SITE_NAME       AS CLINIC_NAME,
            CITY,
            PROVINCES,
            LATITUDE,
            LONGITUDE
        FROM RAW.STATIC_DATA.DISCHEM_REGION_MANAGERS
        WHERE STATUS = 'Active' AND STORE_CODE IS NOT NULL
        """

        cur.execute(query)
        data = cur.fetchall()

        columns = [desc[0] for desc in cur.description]
        df = pd.DataFrame(data, columns=columns)

        df = df.fillna("")  # Replace nulls

        cur.close()
        conn.close()

        return jsonify(df.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-map-key', methods=['GET'])
def get_map_key():
    try:
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return jsonify({"error": "API key not found"}), 404
        return jsonify({"apiKey": api_key})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/ai-outbreak-news')
def get_ai_outbreak_news():
    province = request.args.get("province")

    try:
        with open("outbreak_data.json", "r") as f:
            data = json.load(f)

        province_data = data.get(province, {"summary": "No data available.", "links": []})
        return jsonify(province_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/get-province-icd10', methods=['GET'])
def get_province_icd10():
    try:
        conn = get_snowflake_connection()
        query = """
        WITH
        DATA AS (
            SELECT DISTINCT
                PVR.CONSULTATION_ID,
                PVR.CREATED_AT,
                SITE_NAME AS CLINIC_NAME,
                CITY,
                PROVINCES,
                LATITUDE,
                LONGITUDE,
                II.DESCRIPTION AS DOCTOR_ICD10_DESCRIPTION
            FROM ANALYTICS.PROD.DIM_CLINIC__PATIENT_VISIT_REPORT PVR
            LEFT JOIN RAW.STATIC_DATA.DISCHEM_REGION_MANAGERS DRM
                ON PVR.PRACTICE_NUMBER = DRM.PRACTICE_NUMBER
            LEFT JOIN ANALYTICS.PROD.STG_CLINIC__CONSULTATION_ICD10_CODES I
                ON PVR.CONSULTATION_ID = I.CONSULTATION_ID
            LEFT JOIN ANALYTICS.PROD.STG_CLINIC__ICD10_CODES II
                ON I.ICD10_CODE_ID = II.ICD10_CODE_ID
            WHERE DRM.STATUS = 'Active' AND STORE_CODE IS NOT NULL AND DOCTOR IS NOT NULL
              AND PVR.CREATED_AT >= DATEADD(month, -3, CURRENT_DATE)
        ),
        LAST_SEVEN_DAYS AS (
            SELECT
                PROVINCES,
                DOCTOR_ICD10_DESCRIPTION,
                COUNT(DISTINCT CONSULTATION_ID) AS CONSULTS
            FROM DATA
            WHERE CREATED_AT >= DATEADD(day, -7, CURRENT_DATE)
            GROUP BY 1, 2
        ),
        LAST_THIRTY_DAYS AS (
            SELECT
                PROVINCES,
                DOCTOR_ICD10_DESCRIPTION,
                COUNT(DISTINCT CONSULTATION_ID) AS CONSULTS
            FROM DATA
            WHERE CREATED_AT BETWEEN DATEADD(day, -37, CURRENT_DATE) AND DATEADD(day, -8, CURRENT_DATE)
            GROUP BY 1, 2
        ),
        FINAL AS (
            SELECT
                LSD.PROVINCES,
                LSD.DOCTOR_ICD10_DESCRIPTION,
                COALESCE(LSD.CONSULTS, 0) AS PAST_SEVEN_CONSULTS,
                COALESCE(LTD.CONSULTS, 0) AS PAST_THIRTY_CONSULTS,
                COALESCE(LSD.CONSULTS, 0) - COALESCE(LTD.CONSULTS, 0) AS INCREASE,
                CASE
                    WHEN COALESCE(LTD.CONSULTS, 0) = 0 THEN NULL
                    ELSE ROUND((COALESCE(LSD.CONSULTS, 0) - LTD.CONSULTS) / LTD.CONSULTS, 2) * 100
                END AS PERCENT_INCREASE
            FROM LAST_SEVEN_DAYS LSD
            LEFT JOIN LAST_THIRTY_DAYS LTD
              ON LSD.PROVINCES = LTD.PROVINCES
              AND LSD.DOCTOR_ICD10_DESCRIPTION = LTD.DOCTOR_ICD10_DESCRIPTION
            HAVING PERCENT_INCREASE > 0
        )
        SELECT
            F.*,
            AVG(D.LATITUDE) AS LATITUDE,
            AVG(D.LONGITUDE) AS LONGITUDE
        FROM FINAL F
        LEFT JOIN DATA D ON F.PROVINCES = D.PROVINCES
        GROUP BY 1, 2, 3, 4, 5, 6
        """

        df = pd.read_sql(query, conn)

        if df.empty:
            return jsonify([])
        
        df["PERCENT_INCREASE"] = pd.to_numeric(df["PERCENT_INCREASE"], errors="coerce").fillna(0).astype(float)

        result = []
        for province, group in df.groupby("PROVINCES"):
            lat = group["LATITUDE"].astype(float).mean()
            lng = group["LONGITUDE"].astype(float).mean()

            icd10_spikes = {
                row["DOCTOR_ICD10_DESCRIPTION"]: f"{row['PERCENT_INCREASE']}% ↑ ({row['PAST_SEVEN_CONSULTS']} in 7d)"
                for _, row in group.iterrows()
            }

            result.append({
                "province": province,
                "lat": lat,
                "lng": lng,
                "top_icd10_spikes": icd10_spikes
            })

        return jsonify(result)

    except Exception as e:
        print("Error in /get-province-icd10:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/get-clinics-by-province', methods=['GET'])
def get_clinics_by_province():
    province = request.args.get("province")
    if not province:
        return jsonify({"error": "Province parameter is required"}), 400

    try:
        conn = get_snowflake_connection()

        query = f"""
        WITH DATA AS (
            SELECT DISTINCT
                SITE_NAME AS CLINIC_NAME,
                CITY,
                PROVINCES,
                LATITUDE,
                LONGITUDE,
                PVR.CONSULTATION_ID,
                PVR.CREATED_AT,
                II.DESCRIPTION AS DOCTOR_ICD10_DESCRIPTION
            FROM ANALYTICS.PROD.DIM_CLINIC__PATIENT_VISIT_REPORT PVR
            LEFT JOIN RAW.STATIC_DATA.DISCHEM_REGION_MANAGERS DRM
                ON PVR.PRACTICE_NUMBER = DRM.PRACTICE_NUMBER
            LEFT JOIN ANALYTICS.PROD.STG_CLINIC__CONSULTATION_ICD10_CODES I
                ON PVR.CONSULTATION_ID = I.CONSULTATION_ID
            LEFT JOIN ANALYTICS.PROD.STG_CLINIC__ICD10_CODES II
                ON I.ICD10_CODE_ID = II.ICD10_CODE_ID
            WHERE DRM.STATUS = 'Active'
              AND STORE_CODE IS NOT NULL
              AND DOCTOR IS NOT NULL
              AND PROVINCES = %s
              AND PVR.CREATED_AT >= DATEADD(month, -3, CURRENT_DATE)
        ),
        LAST_SEVEN_DAYS AS (
            SELECT
                CLINIC_NAME,
                CITY,
                PROVINCES,
                DOCTOR_ICD10_DESCRIPTION,
                COUNT(DISTINCT CONSULTATION_ID) AS CONSULTS
            FROM DATA
            WHERE CREATED_AT >= DATEADD(day, -7, CURRENT_DATE)
            GROUP BY 1, 2, 3, 4
        ),
        LAST_THIRTY_DAYS AS (
            SELECT
                CLINIC_NAME,
                CITY,
                PROVINCES,
                DOCTOR_ICD10_DESCRIPTION,
                COUNT(DISTINCT CONSULTATION_ID) AS CONSULTS
            FROM DATA
            WHERE CREATED_AT BETWEEN DATEADD(day, -37, CURRENT_DATE) AND DATEADD(day, -8, CURRENT_DATE)
            GROUP BY 1, 2, 3, 4
        ),
        FINAL AS (
            SELECT
                LSD.CLINIC_NAME,
                LSD.CITY,
                LSD.PROVINCES,
                LSD.DOCTOR_ICD10_DESCRIPTION,
                COALESCE(LSD.CONSULTS, 0) AS PAST_SEVEN_CONSULTS,
                COALESCE(LTD.CONSULTS, 0) AS PAST_THIRTY_CONSULTS,
                COALESCE(LSD.CONSULTS, 0) - COALESCE(LTD.CONSULTS, 0) AS INCREASE,
                CASE
                    WHEN COALESCE(LTD.CONSULTS, 0) = 0 THEN NULL
                    ELSE ROUND((COALESCE(LSD.CONSULTS, 0) - LTD.CONSULTS) / LTD.CONSULTS, 2) * 100
                END AS PERCENT_INCREASE
            FROM LAST_SEVEN_DAYS LSD
            LEFT JOIN LAST_THIRTY_DAYS LTD
              ON LSD.CLINIC_NAME = LTD.CLINIC_NAME
             AND LSD.CITY = LTD.CITY
             AND LSD.PROVINCES = LTD.PROVINCES
             AND LSD.DOCTOR_ICD10_DESCRIPTION = LTD.DOCTOR_ICD10_DESCRIPTION
            HAVING PERCENT_INCREASE > 0
        )
        SELECT
            F.*,
            AVG(D.LATITUDE) AS LAT,
            AVG(D.LONGITUDE) AS LNG
        FROM FINAL F
        LEFT JOIN DATA D ON F.CLINIC_NAME = D.CLINIC_NAME AND F.CITY = D.CITY AND F.PROVINCES = D.PROVINCES
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        """

        df = pd.read_sql(query, conn, params=(province,))

        if df.empty:
            return jsonify([])

        df["PERCENT_INCREASE"] = pd.to_numeric(df["PERCENT_INCREASE"], errors="coerce").fillna(0).astype(float)

        result = []
        for (clinic, city, prov, lat, lng), group in df.groupby(["CLINIC_NAME", "CITY", "PROVINCES", "LAT", "LNG"]):
            icd10_spikes = {
                row["DOCTOR_ICD10_DESCRIPTION"]: f"{row['PERCENT_INCREASE']}% ↑ ({row['PAST_SEVEN_CONSULTS']} in 7d)"
                for _, row in group.iterrows()
            }
            result.append({
                "clinic_name": clinic,
                "city": city,
                "province": prov,
                "lat": float(lat),
                "lng": float(lng),
                "top_icd10": icd10_spikes
            })

        return jsonify(result)

    except Exception as e:
        print("Server error in /get-clinics-by-province:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/get-product-suggestions", methods=["POST"])
def get_product_suggestions():
    try:
        data = request.get_json()
        icd10_codes = data.get("icd10_codes", [])

        # Load product vector DB or JSON fallback
        with open("dischem_products.json") as f:
            products = json.load(f)

        # Naive keyword search (you'll replace with FAISS later)
        suggestions = []
        for icd in icd10_codes:
            for product in products:
                if icd.lower() in product["name"].lower():
                    suggestions.append(product)
            if len(suggestions) >= 5:
                break

        return jsonify({"products": suggestions})

    except Exception as e:
        print("Error in /get-product-suggestions:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
