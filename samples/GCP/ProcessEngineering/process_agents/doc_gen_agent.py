# process_agents/doc_gen_agent.py
from google.adk.agents import LlmAgent
import docx
from docx.shared import Inches
import graphviz
import os
import json

def generate_process_diagram(process_name: str, dot_source: str) -> str:
    try:
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{process_name.lower().replace(' ', '_')}_diagram"
        src = graphviz.Source(dot_source)
        output_path = src.render(filename=filename, directory=output_dir, format='png', cleanup=True)
        return output_path
    except Exception as e:
        return f"Error: {e}"

def create_word_document(process_name: str, content_json: str, diagram_path: str = "None") -> str:
    """
    content_json: A JSON string mapping Section Titles to Section Text.
    """
    try:
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"{process_name.lower().replace(' ', '_')}_spec.docx")
        
        # Parse the JSON string manually
        content = json.loads(content_json)
        
        doc = docx.Document()
        doc.add_heading(f"Process Specification: {process_name}", 0)
        
        if diagram_path and os.path.exists(diagram_path):
            doc.add_heading('Process Flow Diagram', level=1)
            doc.add_picture(diagram_path, width=Inches(6.0))

        for section_title, section_text in content.items():
            doc.add_heading(section_title, level=1)
            doc.add_paragraph(section_text)
            
        doc.save(filename)
        return f"Document saved: {filename}"
    except Exception as e:
        return f"Failed: {e}"

doc_gen_agent = LlmAgent(
    name='Documentation_Agent',
    model='gemini-2.0-flash-001',
    description='Generates Word documents and PNG flow diagrams.',
    instruction=(
        "1. Create a DOT graph. Use 'generate_process_diagram'. "
        "2. Prepare content as a JSON string (e.g., '{\"Overview\": \"...\"}'). "
        "3. Use 'create_word_document' with that JSON string and the diagram path."
    ),
    tools=[generate_process_diagram, create_word_document]
)