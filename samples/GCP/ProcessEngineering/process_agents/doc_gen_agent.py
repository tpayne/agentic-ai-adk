# process_agents/doc_gen_agent.py
from google.adk.agents import LlmAgent
import docx
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

import os
import json
import re
import time
import networkx as nx
import matplotlib.pyplot as plt

def generate_clean_diagram(process_name: str, edge_list_json: str) -> str:
    """Generates a readable PNG diagram using NetworkX (No external exe needed)."""
    try:
        time.sleep(2) # Rate limit protection
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"{process_name.lower().replace(' ', '_')}_flow.png")
        
        # Robustly parse edge list
        clean_edges = re.sub(r'^```json\s*|```$', '', edge_list_json.strip(), flags=re.MULTILINE)
        edges = json.loads(clean_edges)
        
        G = nx.DiGraph()
        G.add_edges_from(edges)
        
        plt.figure(figsize=(10, 6))
        # kamada_kawai prevents node overlap for better readability
        pos = nx.kamada_kawai_layout(G) 
        
        nx.draw(G, pos, with_labels=True, node_color='#D6EAF8', 
                edge_color='#5D6D7E', node_size=2500, font_size=8, 
                font_weight='bold', arrows=True, arrowsize=15, 
                width=1.5, node_shape='s')
        
        plt.title(f"Process Architecture: {process_name}", fontsize=12)
        plt.savefig(filename, bbox_inches='tight', dpi=300)
        plt.close()
        return filename
    except Exception as e:
        print(f"Diagram Error: {e}")
        return "None"

def create_professional_word_doc(process_name: str, content_json: str, diagram_path: str) -> str:
    """Compiles a clean Word Specification from JSON content."""
    try:
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        doc_path = os.path.join(output_dir, f"{process_name.lower().replace(' ', '_')}_specification.docx")
        
        # Clean JSON from potential LLM markdown or filler
        clean_content = re.sub(r'^```json\s*|```$', '', content_json.strip(), flags=re.MULTILINE)
        
        try:
            sections = json.loads(clean_content)
        except json.JSONDecodeError:
            # Fallback if JSON is still malformed: treat as raw text
            sections = {"Process Detailed Narrative": content_json}
        
        doc = docx.Document()
        
        # Title
        title = doc.add_heading(process_name, 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 1. Insert Diagram
        if diagram_path != "None" and os.path.exists(diagram_path):
            doc.add_heading('1. Process Flow Visualization', level=1)
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = para.add_run()
            run.add_picture(diagram_path, width=Inches(5.5))
        
        # 2. Narrative Content
        doc.add_heading('2. Process Details', level=1)
        for section_title, section_body in sections.items():
            doc.add_heading(section_title, level=2)
            p = doc.add_paragraph(str(section_body))
            p.style.font.size = Pt(11)
            
        doc.save(doc_path)
        return f"SUCCESS: Professional document generated at {doc_path}"
    except Exception as e:
        return f"ERROR: {str(e)}"

doc_gen_agent = LlmAgent(
    name='Documentation_Agent',
    model='gemini-2.0-flash-001',
    description='Generates professional Word specifications and diagrams.',
    instruction=(
        "You are a Technical Writer. Convert the approved workflow into a final specification. "
        "1. Identify the flow steps and prepare them as a JSON edge list (e.g., '[[\"Step1\", \"Step2\"]]') "
        "for the 'generate_clean_diagram' tool. "
        "2. Structure the full text into a JSON object (Heading: Content) and use "
        "'create_professional_word_doc' to generate the .docx file. "
        "OUTPUT ONLY the tool calls. No conversational filler."
    ),
    tools=[generate_clean_diagram, create_professional_word_doc]
)