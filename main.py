from orchestrator import process_creation_request

if __name__ == "__main__":
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
    """

    template_id = "oa.35"
    template_name = "Тест ИИ 2"

    process_creation_request(user_request_text, sample_xml, template_id, template_name)