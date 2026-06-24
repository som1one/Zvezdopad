import requests
import os
import json

# Manual URL from environment or settings if I could read them easily, 
# but I know it's https://karkas.bitrix24.ru/rest/153/vqukf1eoovd3ba99/
WEBHOOK_URL = "https://karkas.bitrix24.ru/rest/153/vqukf1eoovd3ba99/"

def get_field_enums():
    r = requests.get(f"{WEBHOOK_URL}crm.deal.fields")
    data = r.json().get("result", {})
    
    field_id = "UF_CRM_1759329251984"
    field = data.get(field_id, {})
    items = field.get("items", [])
    
    mapping = {item["ID"]: item["VALUE"] for item in items}
    print(json.dumps(mapping, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    get_field_enums()

