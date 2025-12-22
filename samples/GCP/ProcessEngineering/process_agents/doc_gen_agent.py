# process_agents/doc_gen_agent.py
from google.adk.agents import LlmAgent
from typing import Dict, Any
import docx
from docx.shared import Inches
import graphviz
import os

def generate_process_diagram(process_name: str, dot_source: str) -> str:
    """
    Renders a Graphviz DOT string into a PNG diagram.
    """
    try:
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{process_name.lower().replace(' ', '_')}_diagram"
        
        # Create Graphviz object
        src = graphviz.Source(dot_source)
        output_path = src.render(filename=filename, directory=output_dir, format='png', cleanup=True)
        
        return f"Diagram generated successfully: {output_path}"
    except Exception as e:
        return f"Failed to generate diagram: {e}"

def create_word_document(process_name: str, content: Dict[str, str], diagram_path: str = None) -> str:
    """
    Generates a formatted Word document with the process description and diagram.
    """
    try:
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"{process_name.lower().replace(' ', '_')}_spec.docx")
        
        doc = docx.Document()
        doc.add_heading(f"Process Specification: {process_name}", 0)
        
        # Add Diagram if exists
        if diagram_path and os.path.exists(diagram_path):
            doc.add_heading('Process Flow Diagram', level=1)
            try:
                doc.add_picture(diagram_path, width=Inches(6.0))
            except Exception as e:
                doc.add_paragraph(f"[Error embedding image: {e}]")

        # Add Content Sections
        for section_title, section_text in content.items():
            doc.add_heading(section_title, level=1)
            doc.add_paragraph(section_text)
            
        doc.save(filename)
        return f"Document generated successfully: {filename}"
    except Exception as e:
        return f"Failed to generate document: {e}"

doc_gen_agent = LlmAgent(
    name='Documentation_Agent',
    model='gemini-2.5-flash',
    description='Generates physical artifacts: Word documents and PNG flow diagrams.',
    instruction=(
        "1. Create a DOT graph syntax for the process. Use 'generate_process_diagram' to render it. "
        "2. Compile the process details (Goal, Steps, Compliance Notes). "
        "3. Use 'create_word_document', passing the path of the generated image. "
        "4. Return the file paths to the root agent."
    ),
    tools=[generate_process_diagram, create_word_document]
)
