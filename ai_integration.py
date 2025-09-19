import requests
import json
import time
from typing import List, Dict, Any
from .config import OLLAMA_API_URL, OLLAMA_MODEL, logger

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
            "num_predict": -1
        }
    }
    max_retries = 3

    for attempt in range(max_retries):
        try:
            logger.info(f"Sending request to local Ollama {OLLAMA_MODEL} (Attempt {attempt + 1}/{max_retries})...")
            
            print("\n" + "="*20 + " PROMPT TO OLLAMA " + "="*20)
            print(prompt)
            print("="*20 + " END PROMPT " + "="*20 + "\n")

            response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)
            response.raise_for_status()
            response_data = response.json()
            response_text = response_data.get('response', '').strip()

            print("\n" + "="*20 + " OLLAMA RAW RESPONSE " + "="*20)
            print(response_text)
            print("="*20 + " END RAW RESPONSE " + "="*20 + "\n")
            
            logger.debug(f"Raw Ollama response: {response_text}")

            if not response_text:
                logger.warning("Ollama returned empty response.")
                return []

            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx+1]
                
                try:
                    temp_json_list = json.loads(json_str)
                    
                    if not isinstance(temp_json_list, list):
                        logger.error(f"Extracted JSON is not a list: {type(temp_json_list)}")
                        raise ValueError("Extracted JSON format is incorrect.")
                    
                    validated_json_list = []
                    for item in temp_json_list:
                        if isinstance(item, dict):
                            if all(key in item for key in ['containerId', 'alias', 'type', 'attributes']):
                                if isinstance(item['attributes'], dict):
                                    validated_json_list.append(item)
                                else:
                                    logger.warning(f"Skipping item, 'attributes' is not a dict: {item}")
                            else:
                                logger.warning(f"Skipping item with missing Platform API keys: {item}")
                        else:
                            logger.warning(f"Skipping non-dict item in list: {item}")
                    
                    logger.info(f"Successfully processed {len(validated_json_list)} attribute definitions from Ollama.")

                    print("\n" + "="*20 + " PROCESSED JSON FOR PLATFORM " + "="*20)
                    print(json.dumps(validated_json_list, indent=2, ensure_ascii=False))
                    print("="*20 + " END PROCESSED JSON " + "="*20 + "\n")
                    
                    return validated_json_list
                    
                except json.JSONDecodeError as je:
                    logger.error(f"Failed to decode extracted JSON string: {je}")
                    logger.error(f"Extracted JSON string was: {repr(json_str)}")
                    
            else:
                logger.error("Could not find a valid JSON array structure (brackets) in Ollama response.")
                
            raise ValueError("No valid JSON array found in Ollama response.")

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {response.status_code} from Ollama API: {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error calling Ollama API: {e}")
        except ValueError as ve:
            logger.error(f"Value error processing Ollama response: {ve}")
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
    return []