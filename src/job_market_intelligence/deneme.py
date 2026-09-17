skills = ["python", "sql", "dbt", "airflow"]
SKILL_WEIGHTS = {
    "sql": 5,
    "dbt": 5,
    "snowflake": 5,
    "data modeling": 5,

    "etl": 4,
    "elt": 4,
    "airflow": 3,
    "python": 3,

    "azure": 2,
    "aws": 2,
    "gcp": 2,
    "databricks": 2,
    "spark": 2,

    "kafka": 1,
    "terraform": 1,
    "kubernetes": 1,
    }
text = "Requirements: python and sql but Preferred: dbt and airflow"

required_skills = []
preferred_skills = [] 
Required_keys = ["What we are looking for", "Requirements", "You bring", "Must have"]
Preferred_keys = ["Preferred", "Nice to have", "Bonus points", "Good to have", "Additional skills"]

for key in Required_keys:
    if key.lower() in text.lower():
        for skey in SKILL_WEIGHTS.keys(): #key = Requirements  and skey = sql  
            if key.lower() in text.lower():
                skill = text.split(key)[1].split("Preferred")[0].strip().lower() # skill = python and sql
                if skey in skill:
                    required_skills.append(skey)
                    print("Requirements", skey)
                    
                #print("Requirements", skill)
 

for key in Preferred_keys:  
    if key.lower() in text.lower():
        for skill in skills:
            if skill in text.split(key)[1]:
                preferred_skills.append(skill)
                print("Preferred", skill)

 