from typing import List, Dict, Any
from platform_api import get_existing_attributes, create_attribute_in_platform, notify_platform_completion
from ai_integration import query_ai_ollama
from xml_parser import parse_xml_fields, build_ai_prompt
from config import logger

def query_ai(prompt: str, template_id: str) -> List[Dict[str, Any]]:
    return query_ai_ollama(prompt, template_id)

def process_creation_request(user_text_request: str, xml_data: str, template_id: str, template_name: str):
    """
    Main function to orchestrate the attribute creation process.
    """
    logger.info("Starting attribute creation process...")
    try:
        logger.info("Step 1: Parsing XML data...")
        xml_fields = parse_xml_fields(xml_data)

        logger.info("Step 2: Fetching existing attributes from Platform API...")
        existing_attrs = get_existing_attributes(template_id)

        instruction_manual_content = """
Создание атрибутов
Для создания атрибута используется метод System Core API / Solution / ObjectAppService / CreateProperty
...
(Include the relevant parts of the instruction manual here, or load from a file)
...
"""  # Замените на реальное содержимое

        logger.info("Step 3: Building prompt for AI...")
        template_info = {"id": template_id, "name": template_name}
        ai_prompt = build_ai_prompt(
            user_request=user_text_request,
            xml_fields=xml_fields,
            template_info=template_info,
            existing_attributes=existing_attrs,
            instruction_manual_content=instruction_manual_content
        )

        iteration = 0
        max_iterations = 5
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"--- Iteration {iteration} ---")

            logger.info("Step 4 & 5: Querying AI for attribute definitions...")
            ai_generated_json_list = query_ai(ai_prompt, template_id)

            if not ai_generated_json_list:
                logger.info("AI returned empty list. Assuming all attributes are created or no new ones are needed.")
                break

            logger.info(f"AI generated {len(ai_generated_json_list)} attribute(s) to create.")

            creation_successes = 0
            for attr_json in ai_generated_json_list:
                if not isinstance(attr_json, dict) or 'alias' not in attr_json or 'type' not in attr_json:
                    logger.warning(f"Skipping invalid attribute JSON: {attr_json}")
                    continue

                if attr_json.get('containerId') != template_id:
                    logger.info(f"Setting containerId for attribute {attr_json.get('alias')} to {template_id}")
                    attr_json['containerId'] = template_id

                if 'attributes' in attr_json and isinstance(attr_json['attributes'], dict):
                    if attr_json['attributes'].get('ObjectApp') is None:
                        logger.info(f"Setting ObjectApp in attributes for {attr_json.get('alias')}")
                        attr_json['attributes']['ObjectApp'] = "sln.2"

                if create_attribute_in_platform(attr_json):
                    creation_successes += 1
                else:
                    logger.error(f"Failed to create attribute defined by: {attr_json}")

            logger.info(f"Iteration {iteration}: Successfully sent creation requests for {creation_successes}/{len(ai_generated_json_list)} attributes.")

            if creation_successes == 0:
                logger.warning("No attributes were successfully created in this iteration. Stopping to prevent infinite loop.")
                break

            logger.info("Re-fetching existing attributes after creation attempt...")
            updated_existing_attrs = get_existing_attributes(template_id)

            logger.info("Re-building AI prompt with updated existing attributes...")
            ai_prompt = build_ai_prompt(
                user_request=user_text_request,
                xml_fields=xml_fields,
                template_info=template_info,
                existing_attributes=updated_existing_attrs,
                instruction_manual_content=instruction_manual_content
            )

        if iteration >= max_iterations:
            logger.warning(f"Maximum iterations ({max_iterations}) reached. Process might be incomplete.")

        logger.info("Final step: Notifying Platform API of completion.")
        notify_platform_completion("Attribute creation process completed via proxy script.")
        logger.info("Attribute creation process finished successfully.")

    except Exception as e:
        logger.error(f"An error occurred during the process: {e}", exc_info=True)
        notify_platform_completion(f"Attribute creation process failed: {str(e)}")
        raise