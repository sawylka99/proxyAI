import requests
import json
import time
import random
from typing import List, Dict, Any
from config import PLATFORM_API_BASE_URL, PLATFORM_API_TOKEN, logger

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
    headers = get_platform_headers()

    try:
        response = requests.post(
            url,
            headers=headers,
            data=template_id,
            timeout=30
        )
        logger.info(f"template_id sent: {template_id}")
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
    base_delay = 1
    
    logger.info(f"Creating attribute with alias: {alias}")
    logger.debug(f"Attribute JSON payload: {json.dumps(attribute_json, indent=2, ensure_ascii=False)}")

    headers = get_platform_headers()

    for attempt in range(max_retries):
        try:
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
            
            if response.status_code == 200:
                logger.info(f"Successfully created attribute: {alias}")
                return True
                
            elif response.status_code == 409:
                logger.warning(f"Attribute already exists or conflict for {alias}: {response.text}")
                return True
                
            elif response.status_code == 500:
                try:
                    error_data = response.json()
                    error_message = error_data.get('alias', '')
                except (json.JSONDecodeError, AttributeError):
                    error_message = response.text if response.text else 'No response body'

                if "уже существует" in error_message:
                    logger.warning(f"Attribute with alias '{alias}' already exists in container '{attribute_json.get('containerId')}'. Skipping creation.")
                    return True
                elif "слишком часто" in error_message or "rate limit" in error_message.lower():
                    logger.warning(f"Rate limit hit for {alias} (attempt {attempt + 1}/{max_retries}). Retrying...")
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        logger.debug(f"Waiting for {delay:.2f} seconds before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Max retries reached for {alias} due to rate limiting. Last error: {error_message}")
                        return False
                else:
                    logger.error(f"Server error (500) creating attribute {alias}: {error_message}")
                    return False
                        
            elif response.status_code == 404:
                logger.error(f"Endpoint not found (404) for {alias}. Check API URL configuration: {response.text}")
                logger.error("Request that caused 404:")
                logger.error(f"  URL: {url}")
                logger.error(f"  Headers: {headers}")
                return False
                
            else:
                logger.error(f"HTTP Error {response.status_code} creating attribute {alias}: {response.text}")
                return False
                
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
    
    logger.error(f"Failed to create attribute {alias} after {max_retries} attempts")
    return False

def notify_platform_completion(message: str):
    """
    Sends a final notification to the Platform API indicating the process is complete.
    """
    url = f"{PLATFORM_API_BASE_URL}/custom/creation_complete"
    payload = {"status": "completed", "details": message}
    try:
        logger.info("Sending completion notification to Platform API.")
        response = requests.post(url, headers=get_platform_headers(), json=payload, timeout=30)
        response.raise_for_status()
        logger.info("Completion notification sent successfully.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending completion notification: {e}")