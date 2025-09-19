import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import json
import time
import logging
import random
import textwrap
import requests.cookies

# --- Configuration ---
# Replace with your actual API endpoints and credentials
PLATFORM_API_BASE_URL = "http://10.9.0.160:9076" # Placeholder
# AI_API_ENDPOINT = "https://your-ai-api.com/generate" # Удалено, так как мы используем Ollama

# Токен для Platform API остается, он используется для авторизации в Platform API
PLATFORM_API_TOKEN = "YW1vbDpDMG0xbmR3NHIzUGxAdGYwcm0=" # Placeholder

# URL для Ollama API
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Модель Ollama для использования
OLLAMA_MODEL = "qwen2.5-coder:32b"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
# --- Helper Functions for Platform API Interaction ---

def get_platform_headers():
    """Generates headers for Platform API requests."""
    return {
        "Authorization": f"Basic {PLATFORM_API_TOKEN}",
        "Content-Type": "application/json"
    }

def get_existing_attributes(template_id: str) -> List[Dict[str, Any]]:
    """
    Fetches the list of existing attributes for a given template from the Platform API.
    """
    url = f"{PLATFORM_API_BASE_URL}/api/public/system/TeamNetwork/ObjectAppService/ListAllProperties"
    
    # --- Используем те же заголовки и куки, что и в curl ---
    # Вам нужно заменить значения куки на актуальные для вашей сессии
    headers = get_platform_headers()

    try:
        # Отправляем POST запрос с template_id в теле запроса БЕЗ кавычек
        response = requests.post(
            url,
            headers=headers,
            data=template_id,  # Используем data= вместо json=, чтобы отправить "сырую" строку
            timeout=30
        )
        logger.info(f"template_id sent: {template_id}") # Логируем отправленный ID
        logger.info(f"Request URL: {response.url}")
        logger.info(f"Request Headers: {response.request.headers}")
        logger.info(f"Request Body: {response.request.body}")
        response.raise_for_status()
        
        existing_attrs_data = response.json()
        logger.info(f"Retrieved {len(existing_attrs_data)} existing attributes for template {template_id}.")
        return existing_attrs_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching existing attributes for template {template_id}: {e}")
        logger.error(f"Response Status Code: {getattr(e.response, 'status_code', 'N/A')}")
        logger.error(f"Response Text: {getattr(e.response, 'text', 'N/A')}")
        return []

def create_attribute_in_platform(attribute_json: Dict[str, Any]) -> bool:
    """
    Sends a request to the Platform API to create a single attribute using the provided JSON.
    Implements retry logic with exponential backoff for rate limiting (HTTP 500) and server errors.
    """
    url = f"{PLATFORM_API_BASE_URL}/api/public/system/TeamNetwork/ObjectAppService/CreateProperty"
    alias = attribute_json.get('alias', 'N/A')
    
    max_retries = 5
    base_delay = 1  # seconds
    
    logger.info(f"Creating attribute with alias: {alias}")
    logger.debug(f"Attribute JSON payload: {json.dumps(attribute_json, indent=2, ensure_ascii=False)}")

    # Получаем заголовки один раз перед циклом, предполагая, что они не меняются
    headers = get_platform_headers() 

    for attempt in range(max_retries):
        try:
            # --- Детальное логирование запроса ---
            logger.debug("---- OUTGOING REQUEST DETAILS ----")
            logger.debug(f"URL: {url}")
            logger.debug(f"Method: POST")
            logger.debug(f"Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
            logger.debug(f"Body (JSON): {json.dumps(attribute_json, indent=2, ensure_ascii=False)}")
            logger.debug("---- END REQUEST DETAILS ----")
            
            response = requests.post(
                url, 
                headers=headers, 
                json=attribute_json, 
                timeout=60
            )
            
            # Проверяем успешный ответ
            if response.status_code == 200:
                logger.info(f"Successfully created attribute: {alias}")
                # Опционально: залогировать ответ
                # logger.debug(f"Response: {response.text}")
                return True
                
            # Обрабатываем специфичные ошибки от Platform API
            elif response.status_code == 409:
                # Conflict - атрибут уже существует
                logger.warning(f"Attribute already exists or conflict for {alias}: {response.text}")
                return True  # Считаем успешным, так как атрибут уже есть
                
            elif response.status_code == 500:
                # Внутренняя ошибка сервера
                try:
                    error_data = response.json()
                    error_message = error_data.get('alias', '')
                except (json.JSONDecodeError, AttributeError):
                    error_message = response.text if response.text else 'No response body'

                # --- НАЧАЛО ИЗМЕНЕНИЙ ---
                # Проверяем сообщение об ошибке на предмет КОНФЛИКТА ИМЕН
                if "уже существует" in error_message: # <-- Добавлено
                    logger.warning(f"Attribute with alias '{alias}' already exists in container '{attribute_json.get('containerId')}'. Skipping creation.")
                    return True # Считаем успешным, так как атрибут уже есть
                # --- КОНЕЦ ИЗМЕНЕНИЙ ---

                # Проверяем сообщение об ошибке на предмет rate limiting
                elif "слишком часто" in error_message or "rate limit" in error_message.lower():
                    logger.warning(f"Rate limit hit for {alias} (attempt {attempt + 1}/{max_retries}). Retrying...")
                    if attempt < max_retries - 1:  # Не последняя попытка
                        # Экспоненциальная задержка с jitter
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.debug(f"Waiting for {delay:.2f} seconds before retry...")
                        time.sleep(delay)
                        continue  # Продолжаем цикл для повторной попытки
                    else:
                        logger.error(f"Max retries reached for {alias} due to rate limiting. Last error: {error_message}")
                        return False

                else:
                    # Другая внутренняя ошибка сервера (не конфликт имен, не rate limit)
                    logger.error(f"Server error (500) creating attribute {alias}: {error_message}")
                    return False # <-- Изменено: немедленно прекращаем попытки
                    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
                        
            elif response.status_code == 404:
                # Не найден endpoint - критическая ошибка конфигурации
                logger.error(f"Endpoint not found (404) for {alias}. Check API URL configuration: {response.text}")
                # Также залогируем детали запроса при критической ошибке
                logger.error("Request that caused 404:")
                logger.error(f"  URL: {url}")
                logger.error(f"  Headers: {headers}")
                return False  # Нет смысла повторять, если URL неправильный
                
            else:
                # Другие HTTP ошибки
                logger.error(f"HTTP Error {response.status_code} creating attribute {alias}: {response.text}")
                # response.raise_for_status() # Не бросаем исключение, а возвращаем False
                return False # Indicate failure
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout error creating attribute {alias} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                logger.debug(f"Waiting for {base_delay} seconds before retry...")
                time.sleep(base_delay)
                continue
            else:
                logger.error(f"Max retries reached for {alias} due to timeout")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error creating attribute {alias}: {e}")
            if attempt < max_retries - 1:
                logger.debug(f"Waiting for {base_delay} seconds before retry...")
                time.sleep(base_delay)
                continue
            else:
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error creating attribute {alias}: {e}", exc_info=True)
            return False
    
    # Если мы дошли до этой точки, значит исчерпаны все попытки
    logger.error(f"Failed to create attribute {alias} after {max_retries} attempts")
    return False

def notify_platform_completion(message: str):
    """
    Sends a final notification to the Platform API indicating the process is complete.
    This is a placeholder - replace with the actual required endpoint and data.
    """
    url = f"{PLATFORM_API_BASE_URL}/custom/creation_complete" # Placeholder endpoint
    payload = {"status": "completed", "details": message}
    try:
        logger.info("Sending completion notification to Platform API.")
        response = requests.post(url, headers=get_platform_headers(), json=payload, timeout=30)
        response.raise_for_status()
        logger.info("Completion notification sent successfully.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending completion notification: {e}")

# --- AI Interaction Logic using Ollama ---

def query_ai_ollama(prompt: str, template_id: str) -> List[Dict[str, Any]]:
    """
    Sends the prompt to the local Ollama model and retrieves the generated JSON list
    in the final Platform API format.
    Includes basic retry logic.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            # "num_predict": 2000 # Попробуйте увеличить или убрать, если JSON обрезается
            "num_predict": -1 # Попробуем без ограничения
        }
    }
    max_retries = 3

    for attempt in range(max_retries):
        try:
            logger.info(f"Sending request to local Ollama {OLLAMA_MODEL} (Attempt {attempt + 1}/{max_retries})...")
            
            # - Выводим промпт в консоль -
            print("\n" + "="*20 + " PROMPT TO OLLAMA " + "="*20)
            print(prompt)
            print("="*20 + " END PROMPT " + "="*20 + "\n")

            response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)
            response.raise_for_status()
            response_data = response.json()
            response_text = response_data.get('response', '').strip()

            # - Выводим ответ ИИ в консоль -
            print("\n" + "="*20 + " OLLAMA RAW RESPONSE " + "="*20)
            print(response_text)
            print("="*20 + " END RAW RESPONSE " + "="*20 + "\n")
            
            logger.debug(f"Raw Ollama response: {response_text}")

            if not response_text:
                logger.warning("Ollama returned empty response.")
                return []

            # --- НОВАЯ ЛОГИКА ИЗВЛЕЧЕНИЯ JSON ---
            # 1. Найти подстроку, похожую на JSON-массив
            # Обработка случаев, когда ИИ добавляет текст вокруг JSON
            # Пример: "... [ { ... }, { ... } ] ..."
            
            # Находим первую [ и последнюю ]
            # Этот метод может быть хрупким, если в тексте есть другие [ или ]
            # Более надежный способ - использовать регулярные выражения или попытаться найти
            # самую длинную подстроку, начинающуюся с [ и заканчивающуюся на ],
            # которую можно распарсить как JSON
            
            # Простой способ: найти первую [ и последнюю ]
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx+1]
                
                # 2. Попробовать распарсить JSON
                try:
                    temp_json_list = json.loads(json_str)
                    
                    if not isinstance(temp_json_list, list):
                        logger.error(f"Extracted JSON is not a list: {type(temp_json_list)}")
                        raise ValueError("Extracted JSON format is incorrect.")
                    
                    # 3. Валидация: проверить, что каждый элемент имеет базовую структуру Platform API
                    validated_json_list = []
                    for item in temp_json_list:
                        if isinstance(item, dict):
                            # Проверяем наличие обязательных ключей для Platform API
                            if all(key in item for key in ['containerId', 'alias', 'type', 'attributes']):
                                # Убеждаемся, что attributes - это словарь
                                if isinstance(item['attributes'], dict):
                                    validated_json_list.append(item)
                                else:
                                    logger.warning(f"Skipping item, 'attributes' is not a dict: {item}")
                            else:
                                logger.warning(f"Skipping item with missing Platform API keys: {item}")
                        else:
                            logger.warning(f"Skipping non-dict item in list: {item}")
                    
                    logger.info(f"Successfully processed {len(validated_json_list)} attribute definitions from Ollama (in Platform API format).")
                    
                    # - Выводим преобразованный (или скорее, валидированный) JSON в консоль -
                    print("\n" + "="*20 + " PROCESSED JSON FOR PLATFORM " + "="*20)
                    print(json.dumps(validated_json_list, indent=2, ensure_ascii=False))
                    print("="*20 + " END PROCESSED JSON " + "="*20 + "\n")
                    
                    return validated_json_list
                    
                except json.JSONDecodeError as je:
                    logger.error(f"Failed to decode extracted JSON string: {je}")
                    logger.error(f"Extracted JSON string was: {repr(json_str)}")
                    # Можем попробовать очистить строку от лишних символов
                    # json_str_cleaned = re.sub(r'[^\[\]{},:"\w\s\.\-_]', '', json_str)
                    # Но это рискованно. Лучше перезапросить.
                    
            else:
                logger.error("Could not find a valid JSON array structure (brackets) in Ollama response.")
                
            # --- КОНЕЦ НОВОЙ ЛОГИКИ ---
            
            raise ValueError("No valid JSON array found in Ollama response.")

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {response.status_code} from Ollama API: {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error calling Ollama API: {e}")
        except ValueError as ve:
            logger.error(f"Value error processing Ollama response: {ve}")
            # Не повторяем попытку при ошибке формата JSON, скорее всего ИИ ответил некорректно
            raise 
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama API: {e}")
        
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            logger.info(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            logger.error("Max retries reached for Ollama API call.")
            raise
    return [] # Этот return вряд ли будет достигнут из-за raise выше


def parse_xml_fields(xml_data: str) -> Dict[str, str]:
    """Parses the XML string and extracts field names and example values."""
    try:
        root = ET.fromstring(xml_data)
        fields = {}
        for child in root:
            # Use tag name as field identifier, text as example value
            fields[child.tag] = child.text if child.text else ""
        logger.info(f"Parsed {len(fields)} fields from XML.")
        return fields
    except ET.ParseError as e:
        logger.error(f"Error parsing XML data: {e}")
        raise ValueError("Invalid XML format provided.")

def build_ai_prompt(user_request: str, xml_fields: Dict[str, str], template_info: Dict[str, str], existing_attributes: List[Dict[str, Any]], instruction_manual_content: str) -> str:
    """Constructs the prompt to send to the AI using JSON for data sections."""

    def _create_json_section(data, title: str) -> str:
        """Создает отформатированную строку для секции с JSON данными."""
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        # Добавляем отступ ко всем строкам JSON, кроме первой и последней (если это многострочный объект/массив)
        lines = json_str.splitlines()
        if len(lines) > 1:
            indented_lines = [lines[0]] + [f"  {line}" for line in lines[1:]]
            formatted_json = "\n".join(indented_lines)
        else:
            formatted_json = json_str
        return f"<{title}>\n{formatted_json}\n</{title}>"

    # --- Подготовка данных для секций ---
    
    # Инструкция и описание задачи остаются текстовыми
    instruction_section = instruction_manual_content
    task_description_section = user_request
    
    # Шаблон как словарь
    target_template_data = {
        "id": template_info['id'],
        "name": template_info['name']
    }
    
    # Поля XML как список словарей
    xml_fields_data = []
    for field_name, example_value in xml_fields.items():
        # Простая обработка примеров, чтобы избежать проблем с кавычками в JSON
        # repr даст строку в кавычках, безопасную для JSON
        safe_example = repr(str(example_value))[1:-1] # Убираем внешние кавычки от repr для читаемости
        xml_fields_data.append({
            "name": field_name,
            "example": safe_example 
        })

    # Существующие атрибуты как список словарей
    existing_attributes_data = []
    if existing_attributes:
        for attr in existing_attributes:
            alias = attr.get('alias', attr.get('Alias', attr.get('name', 'Unknown')))
            name = attr.get('attributes', {}).get('Name', alias) 
            type_info = attr.get('type', attr.get('Type', 'Unknown'))
            existing_attributes_data.append({
                "alias": alias,
                "name": name,
                "type": type_info
            })
    else:
        # Можно передать пустой список или специальную заметку
        # existing_attributes_data = [{"note": "No existing attributes found."}]
        # Или просто оставить пустой список, что проще
        pass # existing_attributes_data остается пустым списком []

    # --- Формирование секции требований (остается текстовой) ---
    requirements_section = """\
1.  Analyze the task description, XML fields data, and existing attributes data.
2.  Using the provided instruction manual, generate JSON objects for the Platform API method `/Solution/ObjectAppService/CreateProperty` to create NEW attributes in the specified template that correspond to the XML fields NOT already covered by existing attributes.
3.  Ensure the generated JSONs are valid and conform to the Platform API schema described in the instruction manual.
4.  CRITICAL: Do not generate JSON for attributes that already exist (based on alias or name). Check the `<existing_attributes_data>` list carefully.
5.  Prioritize creating attributes that map directly to the provided XML fields.
6.  CRITICAL FORMAT INSTRUCTION: Respond ONLY with a JSON array containing objects in the EXACT format shown below. Do not include any other text, explanations, markdown, or JSON-RPC wrappers. The array should be valid JSON that can be parsed directly.
    **Expected Format Example for attributes:**
    [
      {
        "containerId": "oa.24",
        "alias": "AttributeName",
        "type": "AttributeType",
        "attributes": {
          "ObjectApp": "sln.2",
          "Name": "AttributeName"
        }
      },
      {
        "containerId": "oa.24",
        "alias": "AnotherAttribute",
        "type": "Decimal",
        "attributes": {
          "ObjectApp": "sln.2",
          "Name": "AnotherAttribute",
          "DecimalPlaces": 2
        }
      }
    ]
    **Map XML types to these Platform API types:**
    - Text/String -> String (Format: PlainText)
    - Date/DateTime -> DateTime (Format: DateISO)
    - Number (Integer) -> Decimal
    - Number (Decimal/Float) -> Decimal
7.  If all necessary attributes already exist, or no new attributes are needed based on the XML and existing list, return an empty JSON array: [].
8.  CRITICAL LIMIT: Generate a maximum of 5 attribute definitions in the JSON array, even if more are required by the XML and not present in the existing list. If more than 5 are needed, generate only the first 5 based on the order they appear in the XML or their priority."""

    # --- Сборка финального промпта ---
    prompt_parts = []
    prompt_parts.append(f"<instruction>\n{instruction_section}\n</instruction>")
    prompt_parts.append(f"<task_description>\n{task_description_section}\n</task_description>")
    
    # Добавляем секции с JSON данными
    prompt_parts.append(_create_json_section(target_template_data, "target_template_data"))
    prompt_parts.append(_create_json_section(xml_fields_data, "xml_fields_data"))
    prompt_parts.append(_create_json_section(existing_attributes_data, "existing_attributes_data"))
    
    prompt_parts.append(f"<requirements>\n{requirements_section}\n</requirements>")
    
    prompt = "\n\n".join(prompt_parts)

    logger.debug(f"Constructed AI prompt:\n{prompt}")
    return prompt

# --- Main Orchestration Logic ---
# Функция query_ai теперь указывает на нашу новую реализацию
def query_ai(prompt: str, template_id: str) -> List[Dict[str, Any]]: # <-- Добавлен аргумент template_id
    return query_ai_ollama(prompt, template_id)

def process_creation_request(user_text_request: str, xml_data: str, template_id: str, template_name: str):
    """
    Main function to orchestrate the attribute creation process.
    """
    logger.info("Starting attribute creation process...")
    try:
        # 1. Parse XML
        logger.info("Step 1: Parsing XML data...")
        xml_fields = parse_xml_fields(xml_data)
        # 2. Get existing attributes
        logger.info("Step 2: Fetching existing attributes from Platform API...")
        existing_attrs = get_existing_attributes(template_id)
        # 3. Load instruction manual content (assuming it's a string or loaded from a file)
        # For this example, we'll embed a simplified version or load it.
        # In practice, you might load it from a file or a constant.
        instruction_manual_content = """
Создание атрибутов
Для создания атрибута используется метод System Core API / Solution / ObjectAppService / CreateProperty
...
(Include the relevant parts of the instruction manual here, or load from a file)
...
""" # --- IMPORTANT: Replace this placeholder with the actual content of Пособие создания ШЗ и атрибутов.docx ---
        # Example of loading from file if needed:
        # with open("Пособие создания ШЗ и атрибутов.docx_content.txt", "r", encoding='utf-8') as f:
        #     instruction_manual_content = f.read()
        # 4. Build AI Prompt
        logger.info("Step 3: Building prompt for AI...")
        template_info = {"id": template_id, "name": template_name}
        ai_prompt = build_ai_prompt(
            user_request=user_text_request,
            xml_fields=xml_fields,
            template_info=template_info,
            existing_attributes=existing_attrs,
            instruction_manual_content=instruction_manual_content
        )
        # 5. Query AI and process results in a loop
        iteration = 0
        max_iterations = 5 # Prevent infinite loops
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"--- Iteration {iteration} ---")
            # Query AI
            logger.info("Step 4 & 5: Querying AI for attribute definitions...")
            ai_generated_json_list = query_ai(ai_prompt, template_id)
            # Check if AI thinks we're done
            if not ai_generated_json_list:
                logger.info("AI returned empty list. Assuming all attributes are created or no new ones are needed.")
                break
            logger.info(f"AI generated {len(ai_generated_json_list)} attribute(s) to create.")
            # 6. Create attributes in Platform
            creation_successes = 0
            for attr_json in ai_generated_json_list:
                # Basic validation before sending
                if not isinstance(attr_json, dict) or 'alias' not in attr_json or 'type' not in attr_json:
                    logger.warning(f"Skipping invalid attribute JSON: {attr_json}")
                    continue
                # Ensure containerId is set correctly
                if attr_json.get('containerId') != template_id:
                     logger.info(f"Setting containerId for attribute {attr_json.get('alias')} to {template_id}")
                     attr_json['containerId'] = template_id
                # Ensure ObjectApp is present in attributes (common requirement)
                # Adjust path 'attributes.ObjectApp' as per manual if different
                if 'attributes' in attr_json and isinstance(attr_json['attributes'], dict):
                    if attr_json['attributes'].get('ObjectApp') is None:
                         logger.info(f"Setting ObjectApp in attributes for {attr_json.get('alias')}")
                         attr_json['attributes']['ObjectApp'] = "sln.2" # --- IMPORTANT: Replace with correct solution ID ---
                         # Or extract from template_id if possible, or make it a parameter
                if create_attribute_in_platform(attr_json):
                    creation_successes += 1
                else:
                    # Consider if failure should stop the process or just log
                    logger.error(f"Failed to create attribute defined by: {attr_json}")
            logger.info(f"Iteration {iteration}: Successfully sent creation requests for {creation_successes}/{len(ai_generated_json_list)} attributes.")
            # --- IMPORTANT: Break condition ---
            # If all AI-suggested creations failed, we might be stuck in a loop.
            # A better approach is to fetch existing attributes again and compare.
            if creation_successes == 0:
                 logger.warning("No attributes were successfully created in this iteration. Stopping to prevent infinite loop.")
                 break
            # 7. Fetch existing attributes again to update the state
            logger.info("Re-fetching existing attributes after creation attempt...")
            # Optional: Add a small delay to allow platform to process creations
            # time.sleep(2)
            updated_existing_attrs = get_existing_attributes(template_id)
            # 8. Re-build prompt with *updated* existing attributes for next AI query
            logger.info("Re-building AI prompt with updated existing attributes...")
            ai_prompt = build_ai_prompt(
                user_request=user_text_request,
                xml_fields=xml_fields,
                template_info=template_info,
                existing_attributes=updated_existing_attrs, # Use updated list
                instruction_manual_content=instruction_manual_content
            )
            # The loop will continue, sending the new prompt to the AI
        if iteration >= max_iterations:
            logger.warning(f"Maximum iterations ({max_iterations}) reached. Process might be incomplete.")
        # 8. Notify Platform of completion
        logger.info("Final step: Notifying Platform API of completion.")
        notify_platform_completion("Attribute creation process completed via proxy script.")
        logger.info("Attribute creation process finished successfully.")
    except Exception as e:
        logger.error(f"An error occurred during the process: {e}", exc_info=True)
        # Optionally, notify the platform about the error
        notify_platform_completion(f"Attribute creation process failed: {str(e)}")
        raise # Re-raise the exception to signal failure to the caller

# --- Example Usage ---
if __name__ == "__main__":
    # Example inputs (replace with actual data from your system/platform request)
    user_request_text = "Создай в шаблоне oa.25 имя шаблона Тест ИИ 2 необходимые мне атрибуты по вот таким данным XML"
    sample_xml = """
        <root>
        <SAPCODE>0000000100000000000348008</SAPCODE>
        <NUMBER1>161118-23</NUMBER1>
        <STATUS>S2</STATUS>
        <ACCOUNT>1000085929</ACCOUNT>
        <OWNERGPR>00147889</OWNERGPR>
        <DATE1>2023-12-07 12:00:00.000000000</DATE1>
        <DATE3>2023-12-07 12:00:00.000000000</DATE3>
        <DATE4>2026-03-31 12:00:00.000000000</DATE4>
        <NDS>20</NDS>
        <SUMMAWITHNDS>1491840000.00</SUMMAWITHNDS>
        <SUMMAWITHOUTNDS>1243200000.00</SUMMAWITHOUTNDS>
        <CURRENCY>RUB</CURRENCY>
        <PROCESS>2 </PROCESS>
        <DOG_TYPE>01</DOG_TYPE>
        <BUKRS>1010</BUKRS>
        <VTWEG>02</VTWEG>
        <Name123412>Sasha</Name123412>
        <kot>syasya</kot>
        </root>
    """ # Wrapped in a root tag for parsing
    template_id = "oa.35"
    template_name = "Тест ИИ 2"
    # IMPORTANT: Update the configuration section at the top with real values!
    # Run the process
    process_creation_request(user_request_text, sample_xml, template_id, template_name)