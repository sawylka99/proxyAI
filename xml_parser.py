import xml.etree.ElementTree as ET
import json
from typing import Dict, List, Any
from config import logger

def parse_xml_fields(xml_data: str) -> Dict[str, str]:
    """Parses the XML string and extracts field names and example values."""
    try:
        root = ET.fromstring(xml_data)
        fields = {}
        for child in root:
            fields[child.tag] = child.text if child.text else ""
        logger.info(f"Parsed {len(fields)} fields from XML.")
        return fields
    except ET.ParseError as e:
        logger.error(f"Error parsing XML data: {e}")
        raise ValueError("Invalid XML format provided.")

def _create_json_section(data, title: str) -> str:
    """Создает отформатированную строку для секции с JSON данными."""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    lines = json_str.splitlines()
    if len(lines) > 1:
        indented_lines = [lines[0]] + [f"  {line}" for line in lines[1:]]
        formatted_json = "\n".join(indented_lines)
    else:
        formatted_json = json_str
    return f"<{title}>\n{formatted_json}\n</{title}>"

def build_ai_prompt(user_request: str, xml_fields: Dict[str, str], template_info: Dict[str, str], existing_attributes: List[Dict[str, Any]], instruction_manual_content: str) -> str:
    """Constructs the prompt to send to the AI using JSON for data sections."""

    target_template_data = {
        "id": template_info['id'],
        "name": template_info['name']
    }
    
    xml_fields_data = []
    for field_name, example_value in xml_fields.items():
        safe_example = repr(str(example_value))[1:-1]
        xml_fields_data.append({
            "name": field_name,
            "example": safe_example 
        })

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

    prompt_parts = []
    prompt_parts.append(f"<instruction>\n{instruction_manual_content}\n</instruction>")
    prompt_parts.append(f"<task_description>\n{user_request}\n</task_description>")
    prompt_parts.append(_create_json_section(target_template_data, "target_template_data"))
    prompt_parts.append(_create_json_section(xml_fields_data, "xml_fields_data"))
    prompt_parts.append(_create_json_section(existing_attributes_data, "existing_attributes_data"))
    prompt_parts.append(f"<requirements>\n{requirements_section}\n</requirements>")
    
    prompt = "\n\n".join(prompt_parts)

    logger.debug(f"Constructed AI prompt:\n{prompt}")
    return prompt