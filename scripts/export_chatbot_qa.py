import json
import ast
import os
import re

def extract_knowledge_base(file_path):
    print(f"Extracting knowledge base from {file_path}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find the samples list definition
        # Looking for "samples = [" until the matching closing bracket
        match = re.search(r'samples\s*=\s*(\[.*?\])\s*logger\.info', content, re.DOTALL)
        if match:
            samples_str = match.group(1)
            # Use ast.literal_eval is safer, but might fail with function calls or complex objects.
            # Here it looks like simple dicts and strings.
            # Clean up potential whitespace issues for ast.
            try:
                samples = ast.literal_eval(samples_str)
                print(f"Found {len(samples)} knowledge base items.")
                return samples
            except Exception as e:
                print(f"Error parsing samples list via AST: {e}")
                # Fallback: simpler regex extraction if needed or manual fix
                return []
        else:
            print("Could not find 'samples' list in file.")
            return []

    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []

def extract_test_cases(file_path):
    print(f"Extracting test cases from {file_path}...")
    extracted_tests = {
        "intent_classification": [],
        "response_generation": [],
        "full_conversation": []
    }
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == 'test_intent_classification':
                    for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Assign):
                            # Check if assigning to 'test_cases'
                            for target in subnode.targets:
                                if isinstance(target, ast.Name) and target.id == 'test_cases':
                                    # Extract value
                                    try:
                                        # ast.literal_eval might not work on the node itself easily without unparsing
                                        # but we can try to evaluate the value part if it's literals
                                        # A simpler way since we have the source is to grab the segment.
                                        # But let's try to reconstruct from AST nodes if they are constants.
                                         if isinstance(subnode.value, ast.List):
                                            for elt in subnode.value.elts:
                                                if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2:
                                                    query = elt.elts[0].value
                                                    intent = elt.elts[1].value
                                                    extracted_tests["intent_classification"].append({
                                                        "query": query,
                                                        "expected_intent": intent
                                                    })
                                    except Exception as e:
                                        print(f"Error extracting intent tests: {e}")

                elif node.name == 'test_response_generation':
                     for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Assign):
                            for target in subnode.targets:
                                if isinstance(target, ast.Name) and target.id == 'test_cases':
                                    try:
                                        if isinstance(subnode.value, ast.List):
                                            for elt in subnode.value.elts:
                                                if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2:
                                                    # ("product", "query", ...)
                                                    q_type = elt.elts[0].value
                                                    query = elt.elts[1].value
                                                    extracted_tests["response_generation"].append({
                                                        "type": q_type,
                                                        "query": query
                                                    })
                                    except Exception as e:
                                        print(f"Error extracting response tests: {e}")

                elif node.name == 'test_full_conversation':
                      for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Assign):
                            for target in subnode.targets:
                                if isinstance(target, ast.Name) and target.id == 'test_queries':
                                    try:
                                        if isinstance(subnode.value, ast.List):
                                            for elt in subnode.value.elts:
                                                if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2:
                                                    query = elt.elts[0].value
                                                    intent = elt.elts[1].value
                                                    extracted_tests["full_conversation"].append({
                                                        "query": query,
                                                        "expected_intent": intent
                                                    })
                                    except Exception as e:
                                        print(f"Error extracting conversation tests: {e}")

        print(f"Found {len(extracted_tests['intent_classification'])} intent tests.")
        print(f"Found {len(extracted_tests['response_generation'])} response tests.")
        print(f"Found {len(extracted_tests['full_conversation'])} conversation tests.")
        
        return extracted_tests

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return {}


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample_content_path = os.path.join(root_dir, "sample_content.py")
    test_chatbot_path = os.path.join(root_dir, "test_chatbot.py")
    output_path = os.path.join(root_dir, "chatbot_qa_export.json")

    kb_data = extract_knowledge_base(sample_content_path)
    test_data = extract_test_cases(test_chatbot_path)

    final_export = {
        "knowledge_base": kb_data,
        "test_cases": test_data
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_export, f, ensure_ascii=False, indent=2)
    
    print(f"Export completed successfully to {output_path}")

if __name__ == "__main__":
    main()
